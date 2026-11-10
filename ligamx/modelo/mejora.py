"""Mejora continua: quién es el modelo de producción y cómo se cambia (campeón / retadores).

Uso:
    python3 -m modelo.mejora estado                      # campeón, retadores y sus métricas guardadas
    python3 -m modelo.mejora adoptar ensamble --motivo "..."   # cambia el modelo de producción

`adoptar` reescribe modelo/campeon.json (lo que lee modelo.pronostico.Pronosticador) y mueve al campeón
anterior a la lista de retadores de modelo/registro.json, dejando constancia en el historial. Las métricas
salen de los archivos de predicciones walk-forward ya guardados en modelo/pred/ (no se reajusta nada).

Regla vigente (registro.json): un retador sólo se adopta en automático si mejora al campeón por más de 2
errores estándar pareados y no empeora en los últimos 8 bloques. Una adopción manual (como la del 10-nov-2026,
tras la auditoría) debe decir su motivo y queda marcada como decisión, no como resultado de la regla.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from modelo import arnes, metricas
from modelo.familias import candidatos

DIR = Path(__file__).resolve().parent
RUTA_CAMPEON = DIR / "campeon.json"
RUTA_REGISTRO = DIR / "registro.json"
REFERENCIAS = ["dc", "poisson_simple", "cerebro_original_limpio", "mercado_cierre_shin", "mercado_abre_shin"]
PERIODOS = {"desarrollo": "{n}.parquet", "prueba": "{n}__prueba__dia.parquet"}


def _leer(nombre: str, periodo: str) -> pd.DataFrame | None:
    ruta = arnes.DIR_PRED / PERIODOS[periodo].format(n=nombre)
    return pd.read_parquet(ruta) if ruta.exists() else None


def _ll(d: pd.DataFrame) -> np.ndarray:
    return metricas.logloss_1x2(d[["p_l", "p_e", "p_v"]].to_numpy(float), d["resultado"].to_numpy(int))


def pareadas(nombre: str) -> dict:
    """Diferencias pareadas (modelo menos referencia) en desarrollo y prueba, sobre los mismos partidos."""
    salida = {}
    for periodo in PERIODOS:
        a = _leer(nombre, periodo)
        if a is None:
            continue
        if periodo == "prueba":
            arnes._acceso_prueba(None, "lectura_pareadas", nombre, quien="mejora.adoptar")
        salida[periodo] = {}
        for ref in REFERENCIAS:
            b = _leer(ref, periodo)
            if b is None or ref == nombre:
                continue
            j = a.merge(b, on="id", suffixes=("", "_r"))
            j = j[j["p_l_r"].notna() & j["p_l"].notna()]
            if len(j) < 30:
                continue
            ref_df = j[["p_l_r", "p_e_r", "p_v_r"]].rename(columns=lambda c: c[:-2]).assign(resultado=j["resultado"])
            r = metricas.diferencia_pareada(_ll(j), _ll(ref_df), j["bloque"])
            fila = {"n": int(r["n"]), "d_logloss": round(r["dif"], 4), "ee": round(r["ee"], 4),
                    "ic95": [round(r["ic_inf"], 4), round(r["ic_sup"], 4)], "z": round(r["z"], 1),
                    "d_logv_marcador": None, "ee_logv_marcador": None}
            if "logp_marcador" in j and "logp_marcador_r" in j and j["logp_marcador_r"].notna().any():
                k = j[j["logp_marcador"].notna() & j["logp_marcador_r"].notna()]
                rv = metricas.diferencia_pareada(k["logp_marcador"], k["logp_marcador_r"], k["bloque"])
                fila["d_logv_marcador"], fila["ee_logv_marcador"] = round(rv["dif"], 4), round(rv["ee"], 4)
            salida[periodo][ref] = fila
    return salida


def _entrada(reg: dict, nombre: str) -> dict:
    if reg["campeon"]["nombre"] == nombre:
        return reg["campeon"]
    for r in reg["retadores"]:
        if r["nombre"] == nombre:
            return r
    raise SystemExit(f"'{nombre}' no está en registro.json (retadores: {[r['nombre'] for r in reg['retadores']]})")


def adoptar(nombre: str, motivo: str, evento: str = "adopción manual") -> dict:
    """Hace de `nombre` el modelo de producción. Devuelve el nuevo campeon.json."""
    if nombre not in candidatos.finalistas():
        raise SystemExit(f"'{nombre}' no es un finalista de modelo/familias/candidatos.py")
    reg = json.loads(RUTA_REGISTRO.read_text(encoding="utf-8"))
    viejo = json.loads(RUTA_CAMPEON.read_text(encoding="utf-8"))
    anterior = reg["campeon"]["nombre"]
    if anterior == nombre:
        print(f"'{nombre}' ya es el modelo de producción"); return viejo
    ent = _entrada(reg, nombre)
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    nuevo = dict(viejo)
    nuevo.update({
        "modelo": nombre,
        "clase": ent["clase"],
        "como_instanciar": f"modelo.familias.candidatos.finalistas()['{nombre}']  (o modelo.pronostico.crear_modelo('{nombre}'))",
        "descripcion": candidatos.DESCRIPCION.get(nombre, ""),
        "hiperparametros": ent["hiperparametros"],
        "fecha_seleccion": hoy,
        "regla": evento + ". " + reg["regla_adopcion"]["texto"],
        "motivo": motivo,
        "metricas": ent["metricas"],
        "pareadas_campeon_menos_referencia": pareadas(nombre),
        "modelo_anterior": anterior,
    })
    RUTA_CAMPEON.write_text(json.dumps(nuevo, ensure_ascii=False, indent=1), encoding="utf-8")
    # registro: el campeón anterior pasa a retador y el adoptado sale de la lista
    previo = dict(reg["campeon"]); previo["estado"] = f"retador: fue el modelo de producción hasta {hoy}"
    reg["retadores"] = [previo] + [r for r in reg["retadores"] if r["nombre"] != nombre]
    reg["campeon"] = {"nombre": nombre, "desde": hoy, "clase": ent["clase"],
                      "hiperparametros": ent["hiperparametros"], "metricas": ent["metricas"]}
    reg["actualizado"] = hoy
    reg["historial"].append({"fecha": hoy, "evento": evento, "campeon": nombre, "anterior": anterior, "nota": motivo})
    RUTA_REGISTRO.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"modelo de producción: {anterior} -> {nombre}")
    return nuevo


def estado() -> None:
    reg = json.loads(RUTA_REGISTRO.read_text(encoding="utf-8"))
    filas = [dict(rol="producción", **{"nombre": reg["campeon"]["nombre"]}, **_met(reg["campeon"]))]
    filas += [dict(rol="retador", nombre=r["nombre"], **_met(r)) for r in reg["retadores"]]
    print(pd.DataFrame(filas).to_string(index=False))
    for h in reg["historial"]:
        print(f"  {h['fecha']}  {h['evento']}: {h['campeon']}  ({h.get('nota', '')[:110]})")


def _met(e: dict) -> dict:
    m = e.get("metricas", {})
    return {"ll_desarrollo": m.get("desarrollo_bloque", {}).get("logloss"), "ll_prueba": m.get("prueba_dia", {}).get("logloss"),
            "logv_desarrollo": m.get("desarrollo_bloque", {}).get("logv_marcador"), "logv_prueba": m.get("prueba_dia", {}).get("logv_marcador")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("estado")
    a = sub.add_parser("adoptar"); a.add_argument("nombre"); a.add_argument("--motivo", required=True)
    a.add_argument("--evento", default="adopción manual")
    args = ap.parse_args(argv)
    if args.cmd == "estado":
        estado()
    else:
        adoptar(args.nombre, args.motivo, args.evento)
    return 0


if __name__ == "__main__":
    sys.exit(main())
