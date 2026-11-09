"""Configuración de modelos en producción (la escribe mejora_modelos.py; la leen modelo_qualy_austin.py y
modelo_carrera_austin.py). Archivo: modelos/config_activa.json

  { actualizado, tareas: { qualy_fp1|qualy_fp2|qualy_fp3|carrera: {
        vigente: <variante>, historial: [ {variante, desde: ISO-UTC, config: {...}} ] } } }

La variante que usa un modelo es la del historial con 'desde' <= corte (F1_CORTE si está definido, si no ahora): así un
GP reproducido en retro usa el campeón que estaba vigente en ese momento (un campeón adoptado mirando el resultado de
un GP no se usa para "re-pronosticar" ese mismo GP: sería una fuga). Sin archivo o sin entrada aplicable -> la
configuración original ("base"), que es exactamente el comportamiento de los modelos antes de este archivo.

Claves de config (qualy):
  seleccion: "auto" (default: el walk-forward elige el mejor del catálogo) | "fijo" (usa 'fijo' sin elegir)
  fijo: nombre de modelo del catálogo o de ensamble     modelos: lista de modelos del catálogo a comparar (auto)
  ensambles: {nombre: [miembros]} (promedio de rankings) pesos: {"2026": w, "2025": w, "otros": w} por recencia
  quitar: variables a quitar (nombre exacto, o prefijo/sufijo con '*': "h_circ_*", "*_trap_delta")
  hiper: {modelo: {parámetro: valor}}                     debutantes: null | "equipo" (prior por la escudería)
Claves de config (carrera): mc_var: dict de variante de sim_carrera.Simulador (p. ej. {"is26": false, "gn_inter": true})
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
DIR = BASE / "modelos"
CONFIG = DIR / "config_activa.json"
TAREAS = ["qualy_fp1", "qualy_fp2", "qualy_fp3", "carrera"]
ORIGEN = "2000-01-01T00:00:00Z"
CONFIG_BASE = {
    "qualy_fp1": {"seleccion": "auto"},
    "qualy_fp2": {"seleccion": "auto"},
    "qualy_fp3": {"seleccion": "auto"},
    "carrera": {"mc_var": {"is26": False, "gn_inter": True}},
}


def _ts(s):
    return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc)


def corte_actual():
    c = os.environ.get("F1_CORTE")
    return _ts(c) if c else datetime.now(timezone.utc)


def leer_config():
    try:
        return json.loads(CONFIG.read_text())
    except Exception:
        return {}


def config_vigente(tarea, corte=None):
    """(nombre_variante, config) vigente en 'corte' (datetime o ISO; default F1_CORTE o ahora)."""
    corte = corte_actual() if corte is None else (_ts(corte) if isinstance(corte, str) else corte)
    t = (leer_config().get("tareas") or {}).get(tarea) or {}
    elegido = None
    for h in sorted(t.get("historial") or [], key=lambda h: h.get("desde") or ORIGEN):
        try:
            if _ts(h.get("desde") or ORIGEN) <= corte:
                elegido = h
        except Exception:
            continue
    if not elegido:
        return "base", json.loads(json.dumps(CONFIG_BASE.get(tarea, {})))
    return elegido.get("variante", "base"), dict(elegido.get("config") or {})
