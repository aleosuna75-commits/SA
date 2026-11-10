# -*- coding: utf-8 -*-
"""
Pronósticos SELLADOS: registro que sólo crece (salidas/sellos.jsonl) para medir el desempeño real
hacia adelante, sin posibilidad de corregir el pasado.

  sellar()     agrega un sello por cada partido que aún no empieza: id, sellado_utc (reloj del sistema),
               modelo, lambdas, 1X2, pick, marcador probable y las tres combinadas.
  calificar()  con los resultados ya jugados califica el sello OFICIAL de cada partido (el último
               anterior a su inicio) y escribe salidas/desempeno.json: por partido y acumulado, acierto
               1X2, marcador exacto, log-loss, Brier, RPS y cuántos picks de cada combinada pegaron
               (los de mitades con gl_ht / gv_ht).

Un sello con las mismas lambdas (a 4 decimales), modelo y combinadas que el último del mismo partido no
se repite.
Uso:  python3 -m produccion.sellos [sellar|calificar]
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from modelo import arnes, datos, metricas
from . import combinada as cb
from . import mercados as mk

DIR_SALIDAS = datos.RAIZ / "salidas"
RUTA_SELLOS = DIR_SALIDAS / "sellos.jsonl"
RUTA_DESEMPENO = DIR_SALIDAS / "desempeno.json"
VARIANTES = tuple(cb.BANDAS)                      # segura, equilibrada, atrevida
PICKS = ("L", "E", "V")


def _ahora() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def leer_sellos(ruta: str | Path | None = None) -> list[dict]:
    """Todos los sellos, en el orden en que se escribieron ([] si el archivo no existe)."""
    ruta = Path(ruta or RUTA_SELLOS)
    if not ruta.exists():
        return []
    with open(ruta, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def _huella(s: dict) -> tuple:
    """Lo que identifica el contenido de un sello (para no repetir uno idéntico)."""
    comb = tuple((v, tuple(p["clave"] for p in (s.get("combinadas", {}).get(v) or {}).get("picks", []))) for v in VARIANTES)
    return (s.get("modelo"), round(s["lam_l"], 4), round(s["lam_v"], 4), round(s.get("rho", 0.0), 4), comb)


def registro(d: dict, fila, modelo: str, sellado_utc: pd.Timestamp, corte_modelo, p1: tuple[float, float]) -> dict:
    """Sello de un partido a partir de su entrada en `combinada.paquete_partidos` y su fila de partidos.csv."""
    M = arnes.matriz_marcadores(float(d["lam_l"]), float(d["lam_v"]), float(d.get("rho", 0.0)))
    p = np.asarray(arnes.p1x2(M), float).ravel()
    top = arnes.top_marcadores(M, 5)
    comb = {}
    for v in VARIANTES:
        c = d["combinadas"].get(v)
        comb[v] = None if c is None else {
            "prob_conjunta": round(float(c["prob_conjunta"]), 6),
            "picks": [{"clave": x["clave"], "etiqueta": x["etiqueta"], "prob": round(float(x["prob"]), 6)} for x in c["picks"]]}
    return {"id": int(d["id"]), "sellado_utc": sellado_utc.isoformat(),
            "corte_modelo_utc": pd.Timestamp(corte_modelo).isoformat() if corte_modelo is not None else None,
            "modelo": modelo, "torneo": str(fila["torneo"]), "fase": str(fila["fase"]),
            "pierna": int(fila["pierna"]) if pd.notna(fila["pierna"]) else None,
            "fecha_utc": pd.Timestamp(fila["fecha_utc"]).isoformat(), "local": str(fila["local"]),
            "visitante": str(fila["visitante"]),
            "lam_l": round(float(d["lam_l"]), 6), "lam_v": round(float(d["lam_v"]), 6), "rho": round(float(d.get("rho", 0.0)), 6),
            "p1_l": round(float(p1[0]), 6), "p1_v": round(float(p1[1]), 6),
            "p_l": round(float(p[0]), 6), "p_e": round(float(p[1]), 6), "p_v": round(float(p[2]), 6),
            "pick": PICKS[int(np.argmax(np.round(p, 10)))],
            "marcador": {"gl": int(top[0][0]), "gv": int(top[0][1]), "prob": round(float(top[0][2]), 6)},
            "top5": [[int(x), int(y), round(float(q), 6)] for x, y, q in top],
            "combinadas": comb}


def sellar(pron=None, df: pd.DataFrame | None = None, ruta: str | Path | None = None, paquete: dict | None = None,
           ahora=None) -> list[dict]:
    """
    Agrega a `ruta` (salidas/sellos.jsonl) un sello por cada partido programado que aún no empieza.
    El sello lleva la hora del reloj (`ahora` sólo existe para las pruebas): no se puede sellar hacia
    atrás, y un pronosticador ajustado con un corte posterior a la hora del sello se rechaza.
    Devuelve los sellos NUEVOS que escribió (los idénticos al último de su partido se omiten).
    """
    ahora = _ahora() if ahora is None else pd.Timestamp(ahora).tz_convert("UTC")
    df = datos.cargar() if df is None else df
    if pron is None:
        from . import obtener_pronosticador
        pron = obtener_pronosticador()
    corte = getattr(pron, "corte", None)
    if corte is not None and pd.Timestamp(corte) > ahora + pd.Timedelta(seconds=5):
        raise ValueError("sellar: el corte del modelo es posterior a la hora del sello")
    pend = df[(df["estado"] == "programado") & (df["fecha_utc"] > ahora)].sort_values(["fecha_utc", "id"])
    if corte is not None:                              # sólo partidos que el modelo no pudo haber visto
        pend = pend[pend["fecha_utc"] >= pd.Timestamp(corte)]
    if pend.empty:
        return []
    if paquete is None:
        paquete = cb.paquete_partidos(pron, pend, con_jornada=False)
    por_id = {int(d["id"]): d for d in paquete["partidos"]}
    p1 = (paquete["p1_l"], paquete["p1_v"])
    ultimo = {}
    for s in leer_sellos(ruta):
        ultimo[s["id"]] = s
    modelo = getattr(pron, "nombre", type(pron).__name__)
    nuevos = []
    for _, fila in pend.iterrows():
        d = por_id.get(int(fila["id"]))
        if d is None:
            continue
        s = registro(d, fila, modelo, ahora, corte, p1)
        if int(fila["id"]) in ultimo and _huella(ultimo[int(fila["id"])]) == _huella(s):
            continue
        nuevos.append(s)
    if nuevos:
        ruta = Path(ruta or RUTA_SELLOS)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "a", encoding="utf-8") as f:           # sólo se agrega
            for s in nuevos:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
    return nuevos


def sellos_oficiales(df: pd.DataFrame, ruta: str | Path | None = None) -> dict[int, dict]:
    """El sello oficial de cada partido: el último con sellado_utc anterior al inicio del partido."""
    inicio = dict(zip(df["id"].astype(int), df["fecha_utc"]))
    of: dict[int, dict] = {}
    for s in leer_sellos(ruta):
        t0 = inicio.get(int(s["id"]))
        if t0 is None or pd.Timestamp(s["sellado_utc"]) >= t0:
            continue
        previo = of.get(int(s["id"]))
        if previo is None or pd.Timestamp(s["sellado_utc"]) >= pd.Timestamp(previo["sellado_utc"]):
            of[int(s["id"])] = s
    return of


def _depende_de_mitades() -> np.ndarray:
    """Por mercado del catálogo: True si su resultado cambia con el marcador del descanso."""
    G, Z = mk._matrices()
    base = np.flatnonzero((mk.H1 == 0) & (mk.A1 == 0))
    pos = {(int(mk.X[i]), int(mk.Y[i])): i for i in base}
    ref = np.array([pos[(int(x), int(y))] for x, y in zip(mk.X, mk.Y)])
    return ((G != G[:, ref]) | (Z != Z[:, ref])).any(axis=1)


def calificar_picks(claves: list[str], gl, gv, gl_ht, gv_ht) -> list[bool | None]:
    """
    Por pick: True si pegó, False si falló y None si no se puede calificar (mercado de mitades sin el
    marcador del descanso, o devolución). Usa las máscaras del catálogo de mercados.
    """
    G, Z = mk._matrices()
    pos = {c: i for i, c in enumerate(mk.claves())}
    cel = int(mk.resultado_en_celdas([gl], [gv], [gl_ht], [gv_ht])[0])
    sin_mitades = cel < 0
    if sin_mitades:
        cel = int(mk.resultado_en_celdas([gl], [gv], [0], [0])[0])
    dep = _depende_de_mitades()
    out = []
    for c in claves:
        if c.startswith("ME_"):
            x, y = c[3:].split("-")
            out.append(bool(int(x) == int(gl) and int(y) == int(gv)))
            continue
        i = pos.get(c)
        if i is None or cel < 0 or (sin_mitades and dep[i]) or Z[i, cel] > 0:
            out.append(None)
        else:
            out.append(bool(G[i, cel] > 0))
    return out


def _acumular(filas: list[dict]) -> dict:
    """Resumen de una lista de partidos calificados."""
    n = len(filas)
    if n == 0:
        return {"n": 0}
    ll = np.array([f["logloss"] for f in filas])
    out = {"n": n, "aciertos_1x2": int(sum(f["acierto_1x2"] for f in filas)),
           "acierto_1x2": float(np.mean([f["acierto_1x2"] for f in filas])),
           "marcadores_exactos": int(sum(f["marcador_exacto"] for f in filas)),
           "marcador_exacto": float(np.mean([f["marcador_exacto"] for f in filas])),
           "logloss": float(ll.mean()), "ee_logloss": float(ll.std(ddof=1) / math.sqrt(n)) if n > 1 else None,
           "brier": float(np.mean([f["brier"] for f in filas])), "rps": float(np.mean([f["rps"] for f in filas])),
           "prob_media_del_pick": float(np.mean([f["prob_pick"] for f in filas])),
           "logloss_referencia_tercios": float(math.log(3)), "combinadas": {}}
    for v in VARIANTES:
        cs = [f["combinadas"][v] for f in filas if f["combinadas"].get(v) and f["combinadas"][v]["completa"] is not None]
        if not cs:
            out["combinadas"][v] = {"n": 0}
            continue
        out["combinadas"][v] = {"n": len(cs), "completas": int(sum(c["completa"] for c in cs)),
                                "frecuencia": float(np.mean([c["completa"] for c in cs])),
                                "prob_anunciada": float(np.mean([c["prob_conjunta"] for c in cs])),
                                "picks_acertados_media": float(np.mean([c["aciertos"] for c in cs])),
                                "picks_por_combinada": int(np.max([c["n_picks"] for c in cs]))}
    return out


def calificar(df: pd.DataFrame | None = None, ruta: str | Path | None = None,
              ruta_salida: str | Path | None = None, escribir: bool = True) -> dict:
    """
    Califica el sello oficial de cada partido ya jugado y devuelve (y escribe en salidas/desempeno.json)
    {"generado_utc", "n_sellos", "n_partidos_sellados", "n_calificados", "acumulado", "por_modelo",
    "por_torneo", "partidos": [...]}. Con cero partidos calificados el acumulado es {"n": 0}.
    """
    df = datos.cargar() if df is None else df
    todos = leer_sellos(ruta)
    of = sellos_oficiales(df, ruta)
    jug = df[(df["estado"] == "jugado") & df["gl"].notna() & df["id"].isin(list(of))].sort_values(["fecha_utc", "id"])
    filas = []
    for r in jug.itertuples(index=False):
        s = of[int(r.id)]
        P = np.array([[s["p_l"], s["p_e"], s["p_v"]]], float)
        P = P / P.sum()
        y = metricas.resultado_1x2([r.gl], [r.gv])
        res = PICKS[int(y[0])]
        comb = {}
        for v in VARIANTES:
            c = (s.get("combinadas") or {}).get(v)
            if not c:
                comb[v] = None
                continue
            marcas = calificar_picks([p["clave"] for p in c["picks"]], r.gl, r.gv, r.gl_ht, r.gv_ht)
            completa = None if any(m is None for m in marcas) else bool(all(marcas))
            comb[v] = {"prob_conjunta": c["prob_conjunta"], "n_picks": len(marcas),
                       "aciertos": int(sum(bool(m) for m in marcas)), "completa": completa,
                       "picks": [{"clave": p["clave"], "etiqueta": p["etiqueta"], "prob": p["prob"], "acerto": m}
                                 for p, m in zip(c["picks"], marcas)]}
        filas.append({"id": int(r.id), "fecha_utc": r.fecha_utc.isoformat(), "torneo": r.torneo, "fase": r.fase,
                      "local": r.local, "visitante": r.visitante, "gl": int(r.gl), "gv": int(r.gv),
                      "gl_ht": int(r.gl_ht) if pd.notna(r.gl_ht) else None,
                      "gv_ht": int(r.gv_ht) if pd.notna(r.gv_ht) else None,
                      "resultado": res, "modelo": s.get("modelo"), "sellado_utc": s["sellado_utc"],
                      "lam_l": s["lam_l"], "lam_v": s["lam_v"], "p_l": s["p_l"], "p_e": s["p_e"], "p_v": s["p_v"],
                      "pick": s["pick"], "prob_pick": float(P[0, PICKS.index(s["pick"])]),
                      "acierto_1x2": int(s["pick"] == res),
                      "marcador_pronosticado": s["marcador"],
                      "marcador_exacto": int(s["marcador"]["gl"] == int(r.gl) and s["marcador"]["gv"] == int(r.gv)),
                      "logloss": float(metricas.logloss_1x2(P, y)[0]), "brier": float(metricas.brier_1x2(P, y)[0]),
                      "rps": float(metricas.rps_1x2(P, y)[0]), "combinadas": comb})
    out = {"generado_utc": _ahora().isoformat(), "n_sellos": len(todos),
           "n_partidos_sellados": len({int(s["id"]) for s in todos}), "n_calificados": len(filas),
           "primer_sello_utc": min((s["sellado_utc"] for s in todos), default=None),
           "acumulado": _acumular(filas),
           "por_modelo": {m: _acumular([f for f in filas if f["modelo"] == m]) for m in sorted({f["modelo"] for f in filas})},
           "por_torneo": {t: _acumular([f for f in filas if f["torneo"] == t]) for t in sorted({f["torneo"] for f in filas})},
           "nota": ("Sólo cuentan pronósticos sellados antes del inicio de cada partido; con pocos partidos el "
                    "error estándar es grande y ninguna cifra es concluyente."),
           "partidos": filas}
    if escribir:
        ruta_salida = Path(ruta_salida or RUTA_DESEMPENO)
        ruta_salida.parent.mkdir(parents=True, exist_ok=True)
        ruta_salida.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def _main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    que = argv[0] if argv else "calificar"
    if que == "sellar":
        print(f"sellos nuevos: {len(sellar())}")
    elif que == "calificar":
        r = calificar()
        print(json.dumps({k: r[k] for k in ("n_sellos", "n_partidos_sellados", "n_calificados", "acumulado")}, ensure_ascii=False))
    else:
        print("uso: python3 -m produccion.sellos [sellar|calificar]")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(_main())
