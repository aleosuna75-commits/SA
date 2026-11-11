"""Cerebro Liga MX · corrida automática.

    python3 pipeline.py auto            # todo: datos → variables → mejora (si hubo partidos) → pronósticos → página
    python3 pipeline.py auto --forzar-mejora
    python3 pipeline.py publicado       # anotar que la página ya se republicó (tras `auto` con publicar = true)
    python3 pipeline.py estado          # qué hay pendiente y cuándo
    python3 pipeline.py vivo-plan [--horas 48]   # próximos inicios (UTC y hora de México) para montar `vivo.py observar`

Pasos de `auto` (cada uno aislado: si uno falla se anota y los demás siguen cuando tiene sentido):
  1. datos       datos/espn_descarga.py actualizar  (resultados nuevos, reprogramaciones, momios)
  2. variables   modelo.variables.actualizar (por bloque y por partido)
  3. mejora      modelo.mejora.ciclo si hay partidos nuevos jugados: reevalúa al modelo de producción y a los
                 retadores con lo recién jugado y adopta a uno sólo si cumple la regla (registro.json)
  4. pronóstico  produccion.exportar: recalibra, sella los pronósticos de lo que viene, califica lo ya jugado,
                 vuelve a simular tabla, liguilla y campeón  → salidas/actual.json
  5. vivo        vivo.py una-vez: estado del día según ESPN → salidas/vivo.json, incrustado en actual.json
                 (campo "vivo"). Si ESPN no responde se anota como aviso: NO cuenta como error de la corrida
  6. página      web/construir.py → web/index.html y web/archivos_publicados.json
Escribe salidas/ultimo_auto.json con lo que pasó y con `publicar` = true si la página cambió (quien corre la
tarea programada republica el Artifact y hace commit y push).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SALIDAS = RAIZ / "salidas"
INDEX = RAIZ / "web" / "index.html"


def _md5(ruta: Path) -> str | None:
    return hashlib.md5(ruta.read_bytes()).hexdigest() if ruta.exists() else None


def _correr(cmd: list[str], limite: int = 900) -> tuple[int, str]:
    r = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, timeout=limite)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _json_final(texto: str) -> dict:
    """El JSON que imprime espn_descarga.py actualizar (puede traer avisos antes)."""
    i = texto.find("{")
    return json.JSONDecoder().raw_decode(texto[i:])[0] if i >= 0 else {}


def paso_vivo() -> dict:
    """
    `vivo.py una-vez` (estado del día según ESPN → salidas/vivo.json) y el campo "vivo" de actual.json al día.
    Nunca lanza: el motor en vivo es auxiliar, así que si ESPN no responde (o algo falla) queda un aviso y
    la corrida sigue; en ese caso se conserva el vivo.json anterior (exportar lo descarta si pasa de 36 h).
    """
    try:
        import vivo as V
        doc = V.una_vez(V.Motor())
        out = {"estado": doc["estado"], "partidos": len(doc["partidos"]), "siguiente": doc.get("siguiente")}
    except Exception as e:
        out = {"aviso": f"vivo una-vez no se pudo correr: {type(e).__name__}: {e}"}
    try:
        from produccion import exportar
        out["incrustado"] = bool(exportar.incrustar_vivo())
    except Exception as e:
        out["aviso_incrustar"] = f"{type(e).__name__}: {e}"
    return out


def auto(forzar_mejora: bool = False) -> dict:
    t0 = time.monotonic()
    rep: dict = {"corrida_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "pasos": {}, "errores": []}
    previo = {}
    try:
        previo = json.loads((SALIDAS / "ultimo_auto.json").read_text(encoding="utf-8"))
    except Exception:
        pass

    def paso(nombre, fn):
        t = time.monotonic()
        try:
            rep["pasos"][nombre] = {"ok": True, **(fn() or {})}
        except Exception as e:                                   # se anota y se sigue
            rep["pasos"][nombre] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            rep["errores"].append(f"{nombre}: {type(e).__name__}: {e}")
            traceback.print_exc()
        rep["pasos"][nombre]["segundos"] = round(time.monotonic() - t, 1)
        return rep["pasos"][nombre]["ok"]

    def datos():
        cod, out = _correr([sys.executable, "datos/espn_descarga.py", "actualizar"])
        d = _json_final(out)
        if not d:
            raise RuntimeError(f"espn_descarga actualizar no devolvió JSON (código {cod}): {out[-300:]}")
        rep["nuevos_jugados"] = d.get("partidos_nuevos_jugados", [])
        rep["reprogramados"] = d.get("partidos_reprogramados", [])
        rep["nuevos_en_calendario"] = d.get("partidos_nuevos_en_calendario", [])
        rep["proximo_partido"] = d.get("proximo_partido")
        return {"codigo": cod, "nuevos_jugados": len(rep["nuevos_jugados"]), "reprogramados": len(rep["reprogramados"]),
                "nuevos_en_calendario": len(rep["nuevos_en_calendario"]), "momios_actualizados": len(d.get("momios_actualizados", [])),
                "tabla_coincide_con_espn": (d.get("tabla") or {}).get("coincide_con_espn")}

    def variables():
        from modelo import variables as V
        V.actualizar("bloque"); V.actualizar()
        return {}

    def mejora():
        if not (rep.get("nuevos_jugados") or forzar_mejora):
            return {"omitido": "sin partidos nuevos"}
        from modelo import mejora as M
        d = M.ciclo(reevaluar=True, adoptar_si_gana=True)
        rep["mejora"] = {"produccion": d["produccion"], "adoptado": d["adoptado"], "tabla": d["tabla"]}
        return {"adoptado": d["adoptado"]}

    def pronostico():
        cod, out = _correr([sys.executable, "-m", "produccion.exportar"])
        if cod != 0:
            raise RuntimeError(out[-400:])
        return {"salida": out.strip().splitlines()[-2:]}

    def vivo():
        rep["vivo"] = paso_vivo()
        return rep["vivo"]

    def pagina():
        cod, out = _correr([sys.executable, "web/construir.py"])
        if cod != 0:
            raise RuntimeError(out[-400:])
        return {"salida": out.strip().splitlines()[-1:]}

    ok_datos = paso("datos", datos)
    paso("variables", variables)
    if ok_datos:
        paso("mejora", mejora)
    if paso("pronostico", pronostico):
        paso("vivo", vivo)                  # antes de la página, para que ésta lleve incrustado el estado del día
        paso("pagina", pagina)
    else:
        paso("vivo", vivo)

    try:
        a = json.loads((SALIDAS / "actual.json").read_text(encoding="utf-8"))
        rep["modelo"] = a["meta"]["modelo"]["nombre"]
        rep["corte_local"] = a["meta"]["corte_local"]
        rep["campeon_top"] = [(c["equipo"], c.get("prob")) for c in a["proyeccion"]["campeon"][:5]]
        rep["liguilla_en_curso"] = a["liguilla"]["en_curso"]
        rep["pendientes"] = len(a["pendientes"])
        rep["desempeno"] = {k: a["desempeno"].get(k) for k in ("n_calificados", "acumulado")}
        # huella de lo que la gente ve: si no cambió, no hace falta republicar la página
        rep["huella"] = hashlib.md5(json.dumps([a["tabla"], a["pendientes"], a["proyeccion"], a["liguilla"],
                                                a["ultimos_resultados"], a["meta"]["modelo"]["nombre"]],
                                               sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    except Exception as e:
        rep["errores"].append(f"huella: {e}")
    falla = any(x.startswith(("pagina", "pronostico")) for x in rep["errores"])
    rep["publicar"] = bool(rep.get("huella")) and rep.get("huella") != previo.get("huella_publicada") and not falla
    rep["huella_publicada"] = previo.get("huella_publicada")      # la actualiza `publicado` tras republicar
    rep["segundos"] = round(time.monotonic() - t0, 1)
    SALIDAS.mkdir(exist_ok=True)
    (SALIDAS / "ultimo_auto.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return rep


def publicado() -> dict:
    """Se llama después de republicar la página: anota la huella publicada para no repetir sin cambios."""
    r = json.loads((SALIDAS / "ultimo_auto.json").read_text(encoding="utf-8"))
    r["huella_publicada"], r["publicar"] = r.get("huella"), False
    r["publicado_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (SALIDAS / "ultimo_auto.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"huella_publicada": r["huella_publicada"], "publicado_utc": r["publicado_utc"]}


def estado() -> dict:
    a = json.loads((SALIDAS / "actual.json").read_text(encoding="utf-8"))
    return {"corte_local": a["meta"]["corte_local"], "modelo": a["meta"]["modelo"]["nombre"],
            "pendientes": [(p["fecha_local"], p["hora_local"], p["local"], p["visitante"]) for p in a["pendientes"]],
            "liguilla_en_curso": a["liguilla"]["en_curso"], "sellados_calificados": a["desempeno"].get("n_calificados")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("auto"); a.add_argument("--forzar-mejora", action="store_true")
    sub.add_parser("estado"); sub.add_parser("publicado")
    v = sub.add_parser("vivo-plan"); v.add_argument("--horas", type=float, default=48.0)
    args = ap.parse_args(argv)
    if args.cmd == "vivo-plan":
        import vivo as V
        print(json.dumps(V.plan(args.horas), ensure_ascii=False, indent=1))
        return 0
    rep = auto(args.forzar_mejora) if args.cmd == "auto" else publicado() if args.cmd == "publicado" else estado()
    print(json.dumps({k: v for k, v in rep.items() if k not in ("mejora",)}, ensure_ascii=False, indent=1))
    return 1 if rep.get("errores") else 0


if __name__ == "__main__":
    sys.exit(main())
