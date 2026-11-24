# -*- coding: utf-8 -*-
"""
Exportación del JSON que consume la página: salidas/actual.json (y una copia fechada en
salidas/historial/). Un solo comando rehace TODO con lo jugado hasta el corte:

    cd /home/user/SA/ligamx && python3 -m produccion.exportar [--corte AAAA-MM-DDTHH:MM]

Pasos: ajusta el Pronosticador (el campeón si existe modelo/campeon.json; si no, el provisional),
sella los pronósticos de los partidos que no han empezado (sólo sin --corte), califica los sellos de
lo ya jugado, arma mercados y combinadas, corre el simulador y escribe el JSON (descrito campo por
campo en salidas/CONTRATO.md). Probabilidades con 4 decimales; el archivo debe pesar menos de 600 KB.

El campo "vivo" lleva incrustado el último documento en vivo (salidas/vivo.json, que escribe vivo.py) si
existe y tiene menos de 36 horas; `incrustar_vivo()` actualiza sólo ese campo sin rehacer lo demás.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from modelo import arnes, datos, metricas
from . import RUTA_CAMPEON, obtener_pronosticador, origen_pronosticador
from . import combinada as cb
from . import sellos, simulador
from .contexto import Contexto

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent

DIR_SALIDAS = datos.RAIZ / "salidas"
RUTA_ACTUAL = DIR_SALIDAS / "actual.json"
DIR_HISTORIAL = DIR_SALIDAS / "historial"
RUTA_CALIBRACION = DIR_SALIDAS / "calibracion_series.json"
RUTA_VIVO = DIR_SALIDAS / "vivo.json"
HORAS_VIVO = 36                                # un documento en vivo más viejo que esto ya no se incrusta
PESO_MAXIMO = 600 * 1024
VERSION_CONTRATO = "1.0"
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
NOMBRE_FASE = {"cuartos": "Cuartos de final", "semifinal": "Semifinal", "final": "Final", "repechaje": "Repechaje"}
PICKS = ("L", "E", "V")
MERCADOS_PRINCIPALES = ["1", "X", "2", "1X", "X2", "12", "SE_1", "SE_2", "H_L-1.5", "H_V-1.5", "O15", "O25", "U25", "O35",
                        "AA_SI", "AA_NO", "L_ANOTA", "V_ANOTA", "L_2MAS", "V_2MAS", "PC_L", "PC_V", "D_1", "D_X", "D_2",
                        "G1T_SI", "O15_1T", "GM_L", "GM_V"]
N_MATRIZ = 7                                   # la matriz de marcadores se exporta de 0 a 6 goles por lado
MAX_DETALLE = 20                               # partidos pendientes con ficha completa; el resto va en versión ligera
RONDAS_PENDIENTES = 2                          # «pendientes»: las 2 primeras etiquetas por fecha (dos jornadas, o la ida y la vuelta de una ronda)
DIAS_PENDIENTES = 6                            # ... y lo que se juegue en los 6 días siguientes al primer pendiente
DIAS_ANTES_DEL_SIGUIENTE = 7                   # tras la final, el torneo terminado se sigue mostrando hasta 7 días antes del siguiente
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
         "diciembre"]
SIN_REDONDEO = {"lat", "lon"}
ZONA_MX = ZoneInfo(datos.ZONA)                 # America/Mexico_City: horas de la prensa → UTC
DESCRIPCION_PROVISIONAL = (
    "Modelo provisional (Poisson simple): cada equipo tiene una fuerza de ataque y una de defensa, y hay una "
    "ventaja de local igual para todos; se estiman con los partidos de los últimos años dando más peso a los "
    "recientes. Los goles de cada equipo se suponen Poisson independientes. No usa lesiones, alineaciones ni momios.")


# ==================================================================================================
# Utilidades
# ==================================================================================================
def redondear(o, dec: int = 4, llave: str | None = None):
    """Copia serializable a JSON con los flotantes a `dec` decimales (NaN e infinito -> null)."""
    if isinstance(o, dict):
        return {str(k): redondear(v, dec, str(k)) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [redondear(v, dec, llave) for v in o]
    if isinstance(o, np.ndarray):
        return redondear(o.tolist(), dec, llave)
    if isinstance(o, (bool, np.bool_)):
        return bool(o)
    if isinstance(o, (int, np.integer)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        if not math.isfinite(o):
            return None
        return float(o) if llave in SIN_REDONDEO else round(float(o), dec)
    if isinstance(o, pd.Timestamp):
        return o.isoformat()
    if o is None or isinstance(o, str):
        return o
    if o is pd.NaT or (not isinstance(o, (dict, list)) and pd.isna(o)):
        return None
    return str(o)


def etiquetas_jornada(reg: pd.DataFrame, n_jornadas: int = 17, minimo: int = 5) -> dict[int, str]:
    """
    Etiqueta de jornada de cada partido de fase regular (partidos.csv no trae la jornada). Los partidos
    se agrupan por fechas contiguas (un hueco de 2 días o más separa grupos); los grupos de `minimo`
    partidos o más se numeran en orden. Un partido suelto se etiqueta "Jornada k (reprogramado)" con
    la jornada en la que faltan sus dos equipos. Si los grupos no suman `n_jornadas`, devuelve
    "Fase regular" (no se inventa un número).
    """
    reg = reg.sort_values(["fecha_utc", "id"])
    if reg.empty:
        return {}
    dia = reg["fecha_local"].dt.normalize()
    dias = np.sort(dia.unique())
    grupo = dict(zip(dias, np.r_[0, np.cumsum(np.diff(dias) >= np.timedelta64(2, "D"))]))
    g = dia.map(grupo).to_numpy()
    tam = pd.Series(g).value_counts()
    grandes = sorted(k for k, v in tam.items() if v >= minimo)
    if len(grandes) != n_jornadas:
        return {int(i): "Fase regular" for i in reg["id"]}
    num = {k: j + 1 for j, k in enumerate(grandes)}
    equipos_de = {num[k]: set(reg.loc[g == k, "local"]) | set(reg.loc[g == k, "visitante"]) for k in grandes}
    out = {}
    for pid, k, loc, vis in zip(reg["id"], g, reg["local"], reg["visitante"]):
        if k in num:
            out[int(pid)] = f"Jornada {num[k]}"
        else:
            falta = [j for j, eqs in equipos_de.items() if loc not in eqs and vis not in eqs]
            out[int(pid)] = f"Jornada {falta[0]} (reprogramado)" if len(falta) == 1 else "Reprogramado"
    return out


def etiqueta_partido(fila, jornadas: dict[int, str]) -> str:
    """'Jornada 17', 'Jornada 7 (reprogramado)', 'Cuartos de final, ida'..."""
    if fila["fase"] == "regular":
        return jornadas.get(int(fila["id"]), "Fase regular")
    base = NOMBRE_FASE.get(fila["fase"], str(fila["fase"]).capitalize())
    if pd.notna(fila["pierna"]):
        return f"{base}, {'ida' if int(fila['pierna']) == 1 else 'vuelta'}"
    return base


def _momios(fila) -> dict | None:
    """Momios de ESPN del partido (decimales) y la probabilidad implícita sin margen (reparto proporcional)."""
    ml = [fila.get("ml_l"), fila.get("ml_e"), fila.get("ml_v")]
    if any(pd.isna(x) or x <= 1.0 for x in ml):
        return None
    inv = np.array([1.0 / x for x in ml])
    out = {"proveedor": fila.get("proveedor") if isinstance(fila.get("proveedor"), str) else None,
           "ml_local": float(ml[0]), "ml_empate": float(ml[1]), "ml_visitante": float(ml[2]),
           "margen": float(inv.sum() - 1.0), "p_local": float(inv[0] / inv.sum()),
           "p_empate": float(inv[1] / inv.sum()), "p_visitante": float(inv[2] / inv.sum()),
           "total_linea": None, "over": None, "under": None}
    if pd.notna(fila.get("total_linea")) and pd.notna(fila.get("over")) and pd.notna(fila.get("under")):
        out.update({"total_linea": float(fila["total_linea"]), "over": float(fila["over"]), "under": float(fila["under"])})
    return out


def _es_campeon(pron) -> bool:
    """True si `pron` es el Pronosticador del modelo campeón (modelo.pronostico) y existe campeon.json."""
    return type(pron).__module__ == "modelo.pronostico" and RUTA_CAMPEON.exists()


def _modelo_meta(pron) -> dict:
    """Nombre, descripción llana y métricas de validación del modelo en uso."""
    if _es_campeon(pron):
        try:
            c = json.loads(RUTA_CAMPEON.read_text(encoding="utf-8"))
        except Exception as e:                                      # el JSON del campeón está roto: se dice
            c = {"error": f"modelo/campeon.json ilegible: {e}"}
        desc = c.get("descripcion") or c.get("descripcion_llana") or c.get("resumen")
        met = c.get("metricas") or c.get("validacion") or {k: v for k, v in c.items() if isinstance(v, (int, float))}
        return {"origen": "campeon", "nombre": c.get("nombre") or c.get("modelo") or getattr(pron, "nombre", "campeon"),
                "descripcion": desc, "metricas": met, "provisional": False,
                "contra_referencias": c.get("pareadas_campeon_menos_referencia"),
                "seleccion": {k: c.get(k) for k in ("fecha_seleccion", "regla", "motivo")},
                "avisos": c.get("avisos") or [], "incertidumbre_parametros": c.get("incertidumbre_parametros")}
    return {"origen": "provisional", "nombre": getattr(pron, "nombre", "provisional"),
            "descripcion": DESCRIPCION_PROVISIONAL, "provisional": True,
            "metricas": {"periodo": "DESARROLLO (Apertura 2016 a Clausura 2025), 2,981 partidos, walk-forward por bloques",
                         "logloss_1x2": 1.0309, "ee_logloss_1x2": 0.0071, "logloss_frecuencias": 1.0702,
                         "logloss_mercado_cierre_1671_partidos": 1.0028, "logloss_modelo_en_esos_1671": 1.0213,
                         "fuente": "modelo/ARNES.md (líneas base); son del modelo poisson_simple, el mismo que usa el provisional"}}


# ==================================================================================================
# Secciones del documento
# ==================================================================================================
def _partido_pendiente(fila, d: dict, ctx: Contexto, etiqueta: str, detalle: bool = True) -> dict:
    """
    Ficha de un partido por jugar (d = su entrada en combinada.paquete_partidos). Con `detalle` False
    sólo lleva lo básico (fecha, equipos, lambdas, 1X2, pick y marcador): así el JSON no crece sin
    límite al principio del torneo.
    """
    M = arnes.matriz_marcadores(d["lam_l"], d["lam_v"], d.get("rho", 0.0))
    p = np.asarray(arnes.p1x2(M), float).ravel()
    k = int(np.argmax(np.round(p, 10)))
    top = arnes.top_marcadores(M, 5)
    local_t = fila["fecha_utc"].tz_convert(datos.ZONA)
    basico = {
        "id": int(fila["id"]), "detalle": bool(detalle), "fecha_utc": fila["fecha_utc"].isoformat(),
        "fecha_local": local_t.strftime("%Y-%m-%d"), "hora_local": local_t.strftime("%H:%M"),
        "dia_semana": DIAS[local_t.dayofweek], "torneo": fila["torneo"], "fase": fila["fase"],
        "pierna": int(fila["pierna"]) if pd.notna(fila["pierna"]) else None, "etiqueta": etiqueta,
        "local": fila["local"], "visitante": fila["visitante"],
        "lam_l": d["lam_l"], "lam_v": d["lam_v"], "rho": d.get("rho", 0.0),
        "p_local": float(p[0]), "p_empate": float(p[1]), "p_visitante": float(p[2]),
        "pick": {"resultado": PICKS[k], "equipo": (fila["local"], "Empate", fila["visitante"])[k], "prob": float(p[k])},
        "marcador": {"gl": int(top[0][0]), "gv": int(top[0][1]), "prob": float(top[0][2])},
    }
    if not detalle:          # el estadio tal como lo da el calendario (sin slug: la ficha ligera no consulta el contexto)
        basico["estadio"] = {"nombre": fila["estadio"] if isinstance(fila["estadio"], str) else None,
                             "ciudad": fila["ciudad"] if isinstance(fila["ciudad"], str) else None, "slug": None, "altitud_m": None}
        return basico
    por_clave = {m["clave"]: m for m in d["mercados"]}
    mercados = [{kk: por_clave[c][kk] for kk in ("clave", "etiqueta", "familia", "prob", "momio_justo", "p_nula")}
                for c in MERCADOS_PRINCIPALES if c in por_clave]
    comb = {}
    for v, c in d["combinadas"].items():
        comb[v] = None if c is None else {
            "prob_conjunta": c["prob_conjunta"], "momio_justo": c["momio_justo"], "prob_ingenua": c["prob_ingenua"],
            "correlacion": c["correlacion"],
            "picks": [{kk: x[kk] for kk in ("clave", "etiqueta", "familia", "prob")} for x in c["picks"]]}
    contexto = ctx.partido(fila)
    sede = contexto.get("sede") or {}
    for kk in ("id", "fecha", "torneo", "fase", "local", "visitante", "a_la_fecha"):
        contexto.pop(kk, None)
    resto = float(1.0 - M[:N_MATRIZ, :N_MATRIZ].sum())
    return {
        **basico,
        "estadio": {"nombre": sede.get("nombre") or (fila["estadio"] if isinstance(fila["estadio"], str) else None),
                    "ciudad": sede.get("ciudad") or (fila["ciudad"] if isinstance(fila["ciudad"], str) else None),
                    "slug": sede.get("slug_medios"), "altitud_m": sede.get("altitud_m")},
        "top5": [{"gl": int(x), "gv": int(y), "prob": float(q)} for x, y, q in top],
        "matriz": M[:N_MATRIZ, :N_MATRIZ], "matriz_resto": resto,
        "mercados": mercados, "combinadas": comb, "explica": d.get("explica", []),
        "contexto": contexto, "momios": _momios(fila),
    }


def _pred_guardada(ids: list[int], nombre: str | None) -> dict[int, dict]:
    """
    Pronósticos walk-forward guardados en modelo/pred para esos partidos (sólo con el modelo campeón,
    es decir, después de la selección; la lectura de archivos de PRUEBA queda en su registro de accesos).
    """
    if not nombre or not ids:
        return {}
    out: dict[int, dict] = {}
    for periodo, gran in (("prueba", "bloque"), ("prueba", "dia"), ("desarrollo", "bloque")):
        try:
            if not arnes.ruta_pred(nombre, periodo, gran).exists():
                continue
            t = arnes.leer_pred(nombre, periodo, gran, quien="exportar.ultimos_resultados")   # en el registro: quién leyó la PRUEBA
        except Exception:
            continue
        for r in t[t["id"].isin(ids)].itertuples(index=False):
            d = {"p_l": float(r.p_l), "p_e": float(r.p_e), "p_v": float(r.p_v), "lam_l": float(r.lam_l), "lam_v": float(r.lam_v)}
            mp = str(getattr(r, "marcador_probable", ""))
            if "-" in mp and mp.replace("-", "").isdigit():      # el marcador que guardó el propio modelo (con su rho)
                x, y = mp.split("-")
                d["marcador"] = {"gl": int(x), "gv": int(y), "prob": float(getattr(r, "p_marcador_probable", float("nan")))}
            out.setdefault(int(r.id), d)
    return out


def _ultimos(df_t: pd.DataFrame, corte, jornadas: dict[int, str], oficiales: dict[int, dict], nombre_modelo: str | None,
             usar_pred: bool = False, minimo: int = 8) -> list[dict]:
    """
    Últimos resultados del torneo (los grupos de fechas más recientes hasta juntar `minimo` partidos)
    con lo que el modelo había pronosticado: del sello oficial o, si no hay, de modelo/pred.
    `pronostico.mercado`: los momios guardados en ESE sello y su 1X2 sin margen, calificados contra el
    resultado; None si el sello no los trae o el pronóstico no viene de un sello.
    """
    jug = df_t[(df_t["estado"] == "jugado") & (df_t["fecha_utc"] < corte) & df_t["gl"].notna()].sort_values(["fecha_utc", "id"])
    if jug.empty:
        return []
    dia = jug["fecha_local"].dt.normalize()
    dias = np.sort(dia.unique())
    grupo = dict(zip(dias, np.r_[0, np.cumsum(np.diff(dias) >= np.timedelta64(2, "D"))]))
    g = dia.map(grupo).to_numpy()
    elegidos, k = np.zeros(len(jug), dtype=bool), int(g.max())
    while k >= 0 and elegidos.sum() < minimo:
        elegidos |= g == k
        k -= 1
    ult = jug[elegidos]
    guardadas = _pred_guardada([int(i) for i in ult["id"] if int(i) not in oficiales], nombre_modelo if usar_pred else None)
    out = []
    for _, r in ult.iloc[::-1].iterrows():
        pid = int(r["id"])
        y = int(metricas.resultado_1x2([r["gl"]], [r["gv"]])[0])
        pron = None
        if pid in oficiales or pid in guardadas:
            s = oficiales.get(pid) or guardadas[pid]
            P = np.array([s["p_l"], s["p_e"], s["p_v"]], float)
            P = P / P.sum()
            kk = int(np.argmax(np.round(P, 10)))
            if "marcador" in s:
                mg = s["marcador"]
            else:
                x, yy, q = arnes.marcador_mas_probable(arnes.matriz_marcadores(s["lam_l"], s["lam_v"]))
                mg = {"gl": int(x), "gv": int(yy), "prob": float(q)}
            pron = {"origen": "sello" if pid in oficiales else "modelo/pred (walk-forward, no sellado)",
                    "sellado_utc": s.get("sellado_utc"), "modelo": s.get("modelo", nombre_modelo),
                    "p_local": float(P[0]), "p_empate": float(P[1]), "p_visitante": float(P[2]), "pick": PICKS[kk],
                    "marcador": mg, "acierto_1x2": bool(kk == y),
                    "marcador_exacto": bool(mg["gl"] == int(r["gl"]) and mg["gv"] == int(r["gv"])),
                    "prob_del_resultado": float(P[y]), "logloss": float(-math.log(max(P[y], 1e-12)))}
            mc = sellos.calificar_mercado(s, y, pron["logloss"]) if pid in oficiales else None
            pron["mercado"] = None if mc is None else {
                "proveedor": mc["proveedor"], "ml_local": mc["ml_l"], "ml_empate": mc["ml_e"], "ml_visitante": mc["ml_v"],
                "margen": mc["margen"], "p_local": mc["p_l"], "p_empate": mc["p_e"], "p_visitante": mc["p_v"],
                "pick": mc["pick"], "acierto_1x2": bool(mc["acierto_1x2"]), "prob_del_resultado": mc["prob_resultado"],
                "logloss": mc["logloss"], "dif_logloss": mc["dif_logloss"]}
        local_t = r["fecha_utc"].tz_convert(datos.ZONA)
        out.append({"id": pid, "fecha_local": local_t.strftime("%Y-%m-%d"), "hora_local": local_t.strftime("%H:%M"),
                    "fase": r["fase"], "etiqueta": etiqueta_partido(r, jornadas), "local": r["local"],
                    "visitante": r["visitante"], "gl": int(r["gl"]), "gv": int(r["gv"]),
                    "gl_ht": int(r["gl_ht"]) if pd.notna(r["gl_ht"]) else None,
                    "gv_ht": int(r["gv_ht"]) if pd.notna(r["gv_ht"]) else None, "resultado": PICKS[y], "pronostico": pron})
    return out


def _sedes_por_equipo() -> dict:
    """Equipo -> {slug, nombre} de su estadio según web/medios.json."""
    try:
        m = json.loads((RAIZ_PROYECTO / "web" / "medios.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {e: {"slug": est["slug"], "nombre": est["nombre"]} for est in m.get("estadios", []) for e in est.get("equipos", [])}


def _medios_estadios() -> list[dict]:
    try:
        return json.loads((RAIZ_PROYECTO / "web" / "medios.json").read_text(encoding="utf-8")).get("estadios", [])
    except Exception:
        return []


def _simple(t: str) -> str:
    """Minúsculas sin acentos ni signos: para comparar nombres de estadio de fuentes distintas."""
    import unicodedata
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return " ".join("".join(c if c.isalnum() else " " for c in t).split())


def _slug_por_nombre(nombre: str | None, estadios: list[dict]) -> str | None:
    """Slug de web/medios.json cuyo nombre (o nombre histórico) coincide con `nombre` o es su comienzo."""
    n = _simple(nombre)
    if not n:
        return None
    for e in estadios:
        for c in (e.get("nombre"), e.get("nombre_historico"), e.get("apodo")):
            c = _simple(c)
            if c and (n == c or n.startswith(c + " ") or c.startswith(n + " ")):
                return e.get("slug")
    return None


def _necesita(r: int) -> str:
    """Lo mínimo que necesita un equipo en la vuelta, como margen r de goles (equipo menos rival)."""
    if r >= 2:
        return f"necesita ganar por {r} o más"
    if r == 1:
        return "necesita ganar"
    if r == 0:
        return "le basta el empate"
    return f"avanza aun si pierde por {-r}"


def _frase(equipo: str, r: int, final: bool = False) -> str:
    if final:
        if r >= 2:
            return f"{equipo} necesita ganar por {r} o más para ser campeón en 90 minutos"
        if r == 1:
            return f"{equipo} necesita ganar para ser campeón"
        if r == 0:
            return f"a {equipo} le basta el empate para ser campeón"
        return f"{equipo} es campeón aun si pierde por {-r}"
    return f"a {equipo} le basta el empate" if r == 0 else f"{equipo} {_necesita(r)}"


def serie_del_partido(p: dict, lt: dict | None) -> dict | None:
    """
    La serie de liguilla de un partido por jugar (por su id o por fase y equipos en liguilla.torneo): llave,
    pierna, global antes del partido, la ida (en la vuelta), la probabilidad exacta de avanzar y qué necesita
    cada uno, ya redactado. None si el partido no es de liguilla o la serie no está en liguilla.torneo.
    """
    if not lt or p.get("fase") not in simulador.FASES_LIGUILLA:
        return None
    s, yo = None, None
    for r in lt.get("rondas") or []:
        for x in r.get("series") or []:
            for l in x.get("piernas") or []:
                if l.get("id") is not None and int(l["id"]) == int(p["id"]):
                    s, yo = x, l
    if s is None:
        for r in lt.get("rondas") or []:
            for x in r.get("series") or []:
                if x.get("fase") == p["fase"] and {x["mejor"]["equipo"], x["peor"]["equipo"]} == {p["local"], p["visitante"]}:
                    s = x
                    yo = next((l for l in x.get("piernas") or [] if l["local"] == p["local"]), None)
    if s is None:
        return None
    mj, pr = s["mejor"]["equipo"], s["peor"]["equipo"]
    pierna = int(p.get("pierna") or (yo or {}).get("pierna") or (2 if p["local"] == mj else 1))
    final = s["fase"] == "final"
    gm = gp = 0
    ida = None
    for l in s.get("piernas") or []:
        if l is yo or not l.get("jugado") or l.get("gl") is None:
            continue
        gm += l["gl"] if l["local"] == mj else l["gv"]
        gp += l["gv"] if l["local"] == mj else l["gl"]
        if l.get("pierna") == 1:
            ida = {"local": l["local"], "visitante": l["visitante"], "gl": int(l["gl"]), "gv": int(l["gv"])}
    nec = None                                    # en la ida, o en la vuelta sin la ida jugada, no aplica (CONTRATO: null)
    casa = next((l["local"] for l in s.get("piernas") or [] if l.get("pierna") == 2), mj)
    empate = "hay tiempos extra y penales" if final else f"avanza {mj}, mejor sembrado"
    ronda = {"cuartos": "los cuartos", "semifinal": "la semifinal", "final": "la final"}.get(s["fase"], "la serie")
    if pierna == 1:
        texto = f"Ida de {ronda} ({s['llave']}): la vuelta es en casa de {casa}. Si el global queda empatado, {empate}."
    elif ida is None:          # la ida todavía no se juega (o no está en los datos): lo que necesita cada uno depende de ella
        texto = (f"Vuelta de {ronda} ({s['llave']}), en casa de {casa}: lo que necesita cada uno depende de la ida, que "
                 f"todavía no tiene resultado. Si el global queda empatado, {empate}.")
    else:
        d = gm - gp
        ida_txt = f"ida: {ida['local']} {ida['gl']}-{ida['gv']} {ida['visitante']}"
        if final:
            nec = {"mejor": _frase(mj, 1 - d, True), "peor": _frase(pr, 1 + d, True)}
            if d == 0:
                texto = (f"Global empatado {gm}-{gp} ({ida_txt}): quien gane la vuelta es campeón; con empate hay "
                         "tiempos extra y penales.")
            else:
                lid, sig, k = (mj, pr, d) if d > 0 else (pr, mj, -d)
                texto = (f"Global {max(gm, gp)}-{min(gm, gp)} a favor de {lid} ({ida_txt}). "
                         f"{_frase(lid, 1 - k, True)[0].upper()}{_frase(lid, 1 - k, True)[1:]}; "
                         f"{_frase(sig, 1 + k, True)} (ganando por {k} hay tiempos extra y penales).")
        else:
            nec = {"mejor": _frase(mj, -d), "peor": _frase(pr, d + 1)}
            cab = (f"Global empatado {gm}-{gp}" if d == 0 else
                   f"Global {max(gm, gp)}-{min(gm, gp)} a favor de {mj if d > 0 else pr}")
            texto = f"{cab} ({ida_txt}). {nec['mejor'][0].upper()}{nec['mejor'][1:]}; {nec['peor']}."
    return {"llave": s["llave"], "fase": s["fase"], "pierna": pierna,
            "mejor": mj, "peor": pr, "siembra_mejor": s["mejor"]["siembra"], "siembra_peor": s["peor"]["siembra"],
            "global_antes": {"mejor": gm, "peor": gp}, "ida": ida,
            "p_avanza_mejor": s["p_avanza_mejor"], "p_avanza_peor": s["p_avanza_peor"],
            "regla_empate": s.get("regla_empate"), "necesita": nec, "texto": texto}


def torneo_liguilla(pron, sim: dict, reglas: dict, clasificados: list[str] | None, df: pd.DataFrame,
                    ctx: Contexto | None = None) -> dict:
    """
    La liguilla con estructura de torneo: siembra, y por ronda (cuartos, semifinal, final) cada serie con el
    pronóstico de su IDA y su VUELTA (goles esperados, 1X2, marcador más probable y los 5 primeros), el marcador
    global más probable y la probabilidad exacta de avanzar. Lo ya jugado es real; lo demás se pronostica con las
    lambdas de liguilla. Antes de que acabe la fase regular la siembra es la esperada (los 8 con más probabilidad
    de clasificar, por su lugar esperado). Las rondas siguientes siguen la ruta de los favoritos con resiembra.
    Cada serie dice si es `definida` (sus dos equipos ya se conocen con certeza, estén o no sus partidos en el
    calendario): los cuartos, en cuanto la fase regular termina; una semifinal, cuando los cuatro cuartos están
    decididos (por la resiembra el rival depende de todos); la final, cuando lo están las dos semifinales.
    El estadio de cada pierna es el del calendario (la misma regla que «pendientes», con `ctx`); sin calendario,
    el que da config/torneo.json → liguilla.sedes_<fase> (o, si ahí no está, horarios_<fase>; prensa) y, si no, la
    sede habitual del local. Día y hora: los del calendario de ESPN; una pierna que ESPN todavía no lista los toma de
    config/torneo.json → liguilla.horarios_<fase> (lo que anunció la liga, leído en la prensa), emparejando local y
    visitante y sólo si el corte es del torneo de esa configuración; `horario_origen` dice de dónde salieron
    («calendario», «prensa» o None si no hay). Las fechas de cada ronda salen de las piernas con día (del calendario
    o de la prensa); las ventanas de config/torneo.json sólo cubren lo que falta.
    """
    eq = list(pron.equipos); ix = {e: i for i, e in enumerate(eq)}
    pe = {d["equipo"]: d for d in sim["por_equipo"]}
    if clasificados:
        siembra, origen = list(clasificados), "tabla final"
    else:
        top = sorted(pe.values(), key=lambda d: -d["p_clasifica"])[:8]
        siembra = [d["equipo"] for d in sorted(top, key=lambda d: (d["pos_esperada"], -d["puntos_esperados"]))]
        origen = "lugar esperado"
    pos = {e: i + 1 for i, e in enumerate(siembra)}
    m = pron.malla(1, fase="liguilla")
    LL, LV, rho = np.asarray(m["lam_l"])[0], np.asarray(m["lam_v"])[0], float(m.get("rho", 0.0))
    sedes, estadios = _sedes_por_equipo(), _medios_estadios()
    reales = {(r["fase"], frozenset((r["mejor"], r["peor"]))): r for r in sim.get("series_reales", [])}
    fechas = (reglas.get("liguilla") or {}).get("fechas") or {}
    mismo_torneo = (sim.get("meta") or {}).get("torneo") in (None, reglas.get("torneo"))
    if not mismo_torneo:
        fechas = {}     # corte retrospectivo de otro torneo: las ventanas de config/torneo.json no son las suyas

    def sede_prensa(fase: str, local: str, visitante: str) -> dict | None:
        """
        Sede de una pierna sin calendario según config/torneo.json → liguilla.sedes_<fase> o, si ahí no está, el
        `estadio` de liguilla.horarios_<fase> (sólo de este torneo).
        """
        if not mismo_torneo:
            return None
        lig = reglas.get("liguilla") or {}
        for x in list(lig.get(f"sedes_{fase}") or []) + list(lig.get(f"horarios_{fase}") or []):
            if x.get("local") == local and x.get("visitante") == visitante and x.get("estadio"):
                return {"slug": _slug_por_nombre(x["estadio"], estadios) or (sedes.get(local) or {}).get("slug"),
                        "nombre": x["estadio"], "origen": "prensa"}
        return None

    def horario_prensa(fase: str, local: str, visitante: str) -> dict | None:
        """
        Día y hora de una pierna que ESPN todavía no lista, según config/torneo.json → liguilla.horarios_<fase>
        (`fecha_local` 'AAAA-MM-DD' y `hora_local` 'HH:MM' del centro de México), sólo de este torneo. La hora UTC
        sale de la zona America/Mexico_City (zoneinfo), no de sumar un desfase fijo.
        """
        if not mismo_torneo:
            return None
        for x in (reglas.get("liguilla") or {}).get(f"horarios_{fase}") or []:
            if x.get("local") != local or x.get("visitante") != visitante:
                continue
            try:
                ini = dt.datetime.strptime(f"{x.get('fecha_local')} {x.get('hora_local')}", "%Y-%m-%d %H:%M")
            except (TypeError, ValueError):
                continue                          # sin día u hora completos (o mal escritos): no se inventa nada
            ini = ini.replace(tzinfo=ZONA_MX)
            return {"fecha_utc": ini.astimezone(dt.timezone.utc).isoformat(), "fecha_local": ini.strftime("%Y-%m-%d"),
                    "hora_local": ini.strftime("%H:%M")}
        return None

    def sede_calendario(f, local: str) -> dict | None:
        """La sede de una pierna que ya está en partidos.csv, con la misma regla que «pendientes»."""
        if ctx is not None:
            try:
                sd, imputada = ctx.sede_de({"id": int(f.name), "estadio_id": f.get("estadio_id"), "local": local,
                                            "fecha_utc": f.get("fecha_utc")})
                info = ctx.info_sede(sd) or {}
            except Exception:
                info, imputada = {}, True
            nombre = info.get("nombre") or (f.get("estadio") if isinstance(f.get("estadio"), str) else None)
            if nombre:
                return {"slug": info.get("slug_medios"), "nombre": nombre, "origen": "habitual" if imputada else "calendario"}
        if isinstance(f.get("estadio"), str):
            return {"slug": _slug_por_nombre(f["estadio"], estadios), "nombre": f["estadio"], "origen": "calendario"}
        return None
    filas = df.set_index("id") if "id" in df.columns else df
    alternativas = {c["llave"]: c["opciones"] for c in sim.get("cruces_cuartos", [])}
    posibles = sim.get("series_posibles", {})

    def piernas(det: dict, fase: str) -> list[dict]:
        out = []
        for p in det["piernas"]:
            habitual = sedes.get(p["local"])
            d = {"pierna": p["pierna"], "nombre": "Ida" if p["pierna"] == 1 else "Vuelta", "id": p.get("id"),
                 "fecha_utc": p.get("fecha_utc"), "fecha_local": None, "hora_local": None, "horario_origen": None,
                 "local": p["local"], "visitante": p["visitante"],
                 "estadio": sede_prensa(fase, p["local"], p["visitante"]) or (dict(habitual, origen="habitual") if habitual else None),
                 "jugado": bool(p["jugado"])}
            if p.get("id") is not None and p["id"] in filas.index:
                f = filas.loc[p["id"]]
                fl = f.get("fecha_local")         # 'AAAA-MM-DD', como en «pendientes» (la columna puede venir como fecha con hora 00:00)
                d["fecha_local"] = pd.Timestamp(fl).strftime("%Y-%m-%d") if pd.notna(fl) else None
                d["hora_local"] = str(f.get("hora_local")) if pd.notna(f.get("hora_local")) else None
                d["estadio"] = sede_calendario(f, p["local"]) or d["estadio"]
                if d["fecha_utc"] is None and pd.notna(f.get("fecha_utc")):
                    d["fecha_utc"] = pd.Timestamp(f["fecha_utc"]).isoformat()
                d["horario_origen"] = "calendario" if d["fecha_local"] else None     # ESPN manda sobre la configuración
            else:                                 # ESPN todavía no la lista: el día y la hora que anunció la liga (prensa)
                hp = horario_prensa(fase, p["local"], p["visitante"])
                if hp:
                    d.update(hp, horario_origen="prensa")
            if p["jugado"]:
                d.update({"gl": p["gl"], "gv": p["gv"]})
            else:
                mm = p.get("marcadores") or []
                pr3 = (float(p["p_local"]), float(p["p_empate"]), float(p["p_visitante"]))
                k = int(np.argmax(np.round(pr3, 10)))
                d.update({"gl": None, "gv": None, "lam_l": p["lam_l"], "lam_v": p["lam_v"], "rho": p.get("rho", rho),
                          "p_local": p["p_local"], "p_empate": p["p_empate"], "p_visitante": p["p_visitante"],
                          "pick": {"resultado": PICKS[k], "equipo": (p["local"], "Empate", p["visitante"])[k], "prob": pr3[k]},
                          "marcador": mm[0] if mm else None, "marcadores": mm})
                if p.get("en_juego"):
                    d["en_juego"] = True
            out.append(d)
        return out

    def serie(llave: str, a: str, b: str, fase: str, viene_de=None, definida: bool = False) -> dict:
        mejor, peor = (a, b) if pos[a] < pos[b] else (b, a)
        real = reales.get((fase, frozenset((mejor, peor))))
        det = real or simulador.detalle_serie({"a": ix[mejor], "b": ix[peor], "fase": fase, "piernas": {}},
                                              eq, pos, LL, LV, rho)
        pm = float(det["p_avanza_mejor"])
        fav = det.get("ganador") or (mejor if pm >= 0.5 else peor)
        glob = [{"mejor": g["mejor"], "peor": g["peor"], "prob": g["prob"]} for g in det.get("globales", [])[:5]]
        if fase == "cuartos":
            alt = [{"mejor": o["mejor"], "peor": o["peor"], "prob": o["prob"], "p_avanza_mejor": o["p_avanza_mejor"]}
                   for o in alternativas.get(f"{pos[mejor]}-{pos[peor]}", [])[:4]]
        else:
            alt = [{"mejor": o["mejor"], "peor": o["peor"], "prob": o["prob"], "p_avanza_mejor": o["p_avanza_mejor"]}
                   for o in posibles.get(fase, [])[:4]]
        return {"llave": llave, "fase": fase, "real": bool(real), "definida": bool(real or definida), "viene_de": viene_de,
                "mejor": {"equipo": mejor, "siembra": pos[mejor]}, "peor": {"equipo": peor, "siembra": pos[peor]},
                "piernas": piernas(det, fase),
                "global": {"probable": glob[0] if glob else None, "top": glob, "p_gana_mejor": det.get("p_global_mejor"),
                           "p_empate": det.get("p_global_empate"), "p_gana_peor": det.get("p_global_peor")},
                "p_avanza_mejor": pm, "p_avanza_peor": float(det["p_avanza_peor"]), "favorito": fav,
                "p_favorito": float(pm if fav == mejor else 1 - pm), "decidida": bool(det.get("decidida")),
                "ganador": det.get("ganador"), "regla_empate": det.get("regla_empate"), "alternativas": alt}

    # definida = los dos equipos ya son seguros: cuartos con la tabla final; semifinales con los cuatro cuartos decididos
    # (hay resiembra: el rival de cada uno depende de quiénes avancen en TODAS las llaves); final con las dos semifinales
    cuartos = [serie(f"C{i + 1}", siembra[a - 1], siembra[b - 1], "cuartos", definida=bool(clasificados))
               for i, (a, b) in enumerate(((1, 8), (2, 7), (3, 6), (4, 5)))]
    de = {c["favorito"]: c["llave"] for c in cuartos}
    vivos = sorted(de, key=lambda e: pos[e])
    semis_definidas = all(c["decidida"] for c in cuartos)
    semis = [serie("S1", vivos[0], vivos[3], "semifinal", [de[vivos[0]], de[vivos[3]]], definida=semis_definidas),
             serie("S2", vivos[1], vivos[2], "semifinal", [de[vivos[1]], de[vivos[2]]], definida=semis_definidas)]
    final = serie("F", semis[0]["favorito"], semis[1]["favorito"], "final", ["S1", "S2"],
                  definida=all(s_["decidida"] for s_ in semis))
    todas = cuartos + semis + [final]
    # «en curso» sólo cuando ya se jugó (o se juega) alguna pierna: que ESPN publique los cuartos no basta
    jugada = any(l.get("jugado") or l.get("en_juego") for s_ in todas for l in s_["piernas"])
    if all(s_["decidida"] for s_ in todas):
        estado = "terminado"
    elif jugada:
        estado = "en_curso"
    else:
        estado = "definido" if clasificados else "proyectado"
    camp = final["favorito"]

    def fechas_ronda(series: list[dict], clave: str) -> dict:
        """Fechas de ida y vuelta de una ronda: las de sus piernas con día (calendario o prensa); lo que falte, las ventanas."""
        out = {}
        for n, nombre in ((1, "ida"), (2, "vuelta")):
            ls = [l for s_ in series for l in s_["piernas"] if l["pierna"] == n]
            con = sorted({l["fecha_local"] for l in ls if l.get("fecha_local")})
            cfg = list(fechas.get(f"{clave}_{nombre}") or [])
            out[nombre] = con if con and all(l.get("fecha_local") for l in ls) else (sorted(set(con) | set(cfg)) or None)
        return out
    return {"estado": estado, "origen_siembra": origen,
            "siembra": [{"pos": i + 1, "equipo": e, "p_clasifica": pe[e]["p_clasifica"], "p_semifinal": pe[e]["p_semifinal"],
                         "p_final": pe[e]["p_final"], "p_campeon": pe[e]["p_campeon"]} for i, e in enumerate(siembra)],
            "rondas": [{"fase": "cuartos", "nombre": "Cuartos de final", "fechas": fechas_ronda(cuartos, "cuartos"), "series": cuartos},
                       {"fase": "semifinal", "nombre": "Semifinales", "fechas": fechas_ronda(semis, "semis"), "series": semis},
                       {"fase": "final", "nombre": "Final", "fechas": fechas_ronda([final], "final"), "series": [final]}],
            "campeon_ruta": camp, "campeon_decidido": bool(final["decidida"]), "p_campeon_ruta": pe[camp]["p_campeon"],
            "subcampeon": (final["peor"]["equipo"] if final["ganador"] == final["mejor"]["equipo"] else final["mejor"]["equipo"])
                          if final["decidida"] else None,
            "nota": (f"Liguilla terminada: {camp} es campeón." if final["decidida"] else
                     "Ruta de los favoritos, serie por serie y con resiembra en semifinales. El porcentaje de cada serie es la "
                     "probabilidad de avanzar en esa serie; la probabilidad de campeón de cada equipo (simulación completa) "
                     "considera todos los caminos posibles.")}


def cuadro_proyectado(pron, sim: dict, liguilla_series: list[dict], clasificados: list[str] | None) -> dict:
    """
    Cuadro de liguilla "como va quedando": siembra (la real si la fase regular terminó; si no, los 8 con más
    probabilidad de clasificar ordenados por su lugar esperado), y en cada ronda el favorito de cada serie con
    su probabilidad EXACTA de avanzar (dos partidos con las lambdas de liguilla; empate global = mejor sembrado;
    final con tiempos extra y penales). Las series reales usan lo ya jugado. Con resiembra en semifinales.
    El camino es el de los favoritos: es la ruta más probable serie por serie, no una predicción segura.
    """
    eq = list(pron.equipos); ix = {e: i for i, e in enumerate(eq)}
    pe = {d["equipo"]: d for d in sim["por_equipo"]}
    if clasificados:
        siembra, origen = list(clasificados), "tabla final"
    else:
        top = sorted(pe.values(), key=lambda d: -d["p_clasifica"])[:8]
        siembra = [d["equipo"] for d in sorted(top, key=lambda d: (d["pos_esperada"], -d["puntos_esperados"]))]
        origen = "lugar esperado"
    pos = {e: i + 1 for i, e in enumerate(siembra)}
    m = pron.malla(1, fase="liguilla")
    LL, LV, rho = np.asarray(m["lam_l"])[0], np.asarray(m["lam_v"])[0], float(m.get("rho", 0.0))
    reales = {}
    for r in liguilla_series or []:
        reales[(r["fase"], frozenset((r["mejor"], r["peor"])))] = r

    def serie(a: str, b: str, fase: str) -> dict:
        mejor, peor = (a, b) if pos[a] < pos[b] else (b, a)
        real = reales.get((fase, frozenset((mejor, peor))))
        if real:
            pm, glob = real["p_avanza_mejor"], [p for p in real["piernas"] if p.get("jugado")]
            out = {"real": True, "decidida": real.get("decidida", False), "ganador_real": real.get("ganador"),
                   "piernas_jugadas": [{"local": p["local"], "visitante": p["visitante"], "gl": p["gl"], "gv": p["gv"]} for p in glob]}
        else:
            i, j = ix[mejor], ix[peor]
            M1 = arnes.matriz_marcadores(LL[j, i], LV[j, i], rho)      # ida en casa del peor sembrado
            M2 = arnes.matriz_marcadores(LL[i, j], LV[i, j], rho)      # vuelta en casa del mejor
            extra = (LL[i, j] * simulador.FRACCION_EXTRA, LV[i, j] * simulador.FRACCION_EXTRA) if fase == "final" else None
            pm = simulador.prob_serie(M1, M2, False, True, "final" if fase == "final" else "posicion", extra)["p_mejor"]
            out = {"real": False, "decidida": False, "ganador_real": None, "piernas_jugadas": []}
        fav = out["ganador_real"] or (mejor if pm >= 0.5 else peor)
        out.update({"fase": fase, "mejor": mejor, "peor": peor, "siembra_mejor": pos[mejor], "siembra_peor": pos[peor],
                    "p_avanza_mejor": float(pm), "p_avanza_peor": float(1 - pm), "favorito": fav,
                    "p_favorito": float(pm if fav == mejor else 1 - pm)})
        return out

    cuartos = [serie(siembra[a - 1], siembra[b - 1], "cuartos") for a, b in ((1, 8), (2, 7), (3, 6), (4, 5))]
    vivos = sorted((c["favorito"] for c in cuartos), key=lambda e: pos[e])
    semis = [serie(vivos[0], vivos[3], "semifinal"), serie(vivos[1], vivos[2], "semifinal")]
    final = serie(semis[0]["favorito"], semis[1]["favorito"], "final")
    return {"origen_siembra": origen, "siembra": siembra, "cuartos": cuartos, "semifinal": semis, "final": final,
            "campeon_ruta": final["favorito"],
            "equipos": {e: {k: pe[e][k] for k in ("p_clasifica", "p_semifinal", "p_final", "p_campeon")} for e in siembra},
            "nota": "Ruta de los favoritos serie por serie. Cada porcentaje es la probabilidad de avanzar en ESA serie; "
                    "la probabilidad de campeón de cada equipo (simulación completa) toma en cuenta todos los caminos."}


# ESPN pone mal la sede de alguna vuelta de final (ver modelo/variables.py)
CORRIGE_SEDE_FINAL = {"Clausura 2017": "Estadio Akron"}


def titulos(ctx: Contexto, df: pd.DataFrame) -> dict:
    """Por equipo: títulos de liga desde 2001 y el último (torneo, fecha, estadio de la vuelta y global)."""
    se = ctx.series()
    fin = se[(se["fase"] == "final") & se["ganador"].notna()].sort_values("fecha")
    out = {}
    for _, f in fin.iterrows():
        e = f["ganador"]
        vuelta = df[(df["torneo"] == f["torneo"]) & (df["fase"] == "final")].sort_values("fecha_utc").tail(1)
        estadio = str(vuelta["estadio"].iloc[0]) if len(vuelta) and pd.notna(vuelta["estadio"].iloc[0]) else None
        estadio = CORRIGE_SEDE_FINAL.get(f["torneo"], estadio)
        d = out.setdefault(e, {"n": 0})
        d["n"] += 1
        d["ultimo"] = {"torneo": f["torneo"], "fecha": str(pd.Timestamp(f["fecha"]).tz_convert("America/Mexico_City").date()),
                       "estadio": estadio, "global": f["global"],
                       "rival": f["b"] if f["a"] == e else f["a"]}
    return out


def _dias_mes(fechas: list[str]) -> str:
    """['2026-12-10', '2026-12-13'] → «10 y 13 de diciembre» (mismo mes) o «30 de noviembre y 3 de diciembre»."""
    ts = [pd.Timestamp(f) for f in fechas if f]
    if not ts:
        return ""
    if len({t.month for t in ts}) == 1:
        return " y ".join(str(t.day) for t in ts) + f" de {MESES[ts[0].month - 1]}"
    return " y ".join(f"{t.day} de {MESES[t.month - 1]}" for t in ts)


def _aviso_final_recorrida(reglas: dict) -> str:
    """
    Las fechas alternas de la final, redactadas desde config/torneo.json (V3-4 del workflow 10): en la práctica la final
    se recorre si Toluca es FINALISTA de liga (juega la Copa Intercontinental en Doha la víspera de la ida); la liga no
    lo ha precisado por escrito.
    """
    fe = (reglas.get("liguilla") or {}).get("fechas") or {}
    normal = _dias_mes(list(fe.get("final_ida") or []) + list(fe.get("final_vuelta") or []))
    alterna = _dias_mes(list(fe.get("final_ida_opcion2") or []) + list(fe.get("final_vuelta_opcion2") or []))
    doha = ((reglas.get("copa_intercontinental_toluca") or {}).get("partidos") or [None])[0]
    cuando = ""
    if doha and fe.get("final_ida"):
        dif = (pd.Timestamp(fe["final_ida"][0]) - pd.Timestamp(doha)).days
        cuando = f" (Toluca juega la Copa Intercontinental en Doha el {_dias_mes([doha])}" + (", víspera de la ida)" if dif == 1 else ")")
    return (f"Fechas de la final: {normal or 'por confirmar'}; si Toluca llega a la final de liga, se recorrería al {alterna}{cuando}. "
            "La liga no lo ha precisado por escrito.")


def _avisos(meta_modelo: dict, des: dict, reglas: dict, sim: dict, pendientes: list[dict], cal: dict | None) -> list[str]:
    """Límites honestos: lo que el sistema NO modela o no sabe."""
    a = [f"Modelo «{meta_modelo.get('nombre')}»: {x}" for x in (meta_modelo.get("avisos") or [])]
    if meta_modelo.get("provisional"):
        a.append("El modelo en uso es el PROVISIONAL (Poisson simple): todavía no existe modelo/campeon.json. "
                 "En validación histórica el mercado de cierre le gana por 0.0185 de log-loss (ee 0.0046).")
    rep_cfg = (reglas.get("pendientes_fase_regular") or {}).get("reprogramado") or {}
    for p in pendientes:                                  # partido reprogramado con nota en config/torneo.json
        if rep_cfg.get("nota") and p["local"] in rep_cfg.get("partido", "") and p["visitante"] in rep_cfg.get("partido", ""):
            a.append(f"{p['local']} vs {p['visitante']} ({p['fecha_local']}): {rep_cfg['nota']} El pronóstico no lo descuenta.")
    a += [
        "Lesiones, convocatorias y alineaciones del día no se modelan. Las bajas reportadas (config/actualidad.json) se muestran "
        "en la ficha completa de cada partido, que sale cuando ESPN ya publica ese partido.",
        "Los momios de ESPN son de referencia. En la historia el mercado de cierre ha sido mejor que cualquier modelo propio; "
        "una diferencia entre el modelo y el momio NO es por sí misma una apuesta con valor.",
        "«Ambos anotan» y «anota / no anota» salen por debajo de lo que ocurre: 2 puntos en 2016-2025 (0.524 pronosticado "
        "vs 0.543 observado) y casi 6 en los últimos tres torneos (0.535 vs 0.593); ganar por 2 o más sale 1 a 2 puntos "
        "de más. Los goles reales son más parejos de lo que supone el modelo. Se probaron cuatro correcciones el "
        "15-nov-2026 y ninguna pasó la regla fijada de antemano, así que no se aplicó ninguna. "
        "No se ofrecen picks de córners ni de tarjetas: no le ganan a la frecuencia de la liga.",
        "Las combinadas usan la probabilidad conjunta exacta del modelo de marcador (no el producto de las marginales); "
        "entre partidos distintos se suponen independientes.",
        "Simulación: " + f"{sim['meta']['n_sim']:,} torneos simulados repartidos en {sim['meta']['n_muestras']:,} muestras de los "
        "parámetros; cada probabilidad trae su error de Monte Carlo (ee_*). La incertidumbre del propio modelo "
        "(que la forma de los equipos cambie) no está en ese error.",
    ]
    regular_completa = bool(sim["meta"].get("regular_completa"))
    aj = reglas.get("ajustes_tabla") or {}
    if not regular_completa:                 # en liguilla la tabla ya no se mueve: estos dos avisos sobran
        a.append("Desempates de la tabla: los goles de visitante se cuentan sobre las primeras 8 visitas de cada equipo "
                 "(aproximación de la regla del mismo número de visitas); el Fair Play sale de las tarjetas registradas (sin "
                 "sanciones de escritorio ni cuerpo técnico) y los partidos simulados no suman tarjetas; el sorteo es al azar.")
        faltan = [k for k in aj if k.startswith("minutos_por_cumplir")]
        n_faltan = len(aj[faltan[-1]]) if faltan and isinstance(aj[faltan[-1]], dict) else None
        a.append("No se simula la resta de 3 puntos por la regla de menores (art. 49)" + (
            f": a los {n_faltan} clubes que les faltan minutos les alcanza con un partido." if n_faltan else "."))
    elif (aj.get("verificado") or {}).get("resultado") and sim["meta"].get("torneo") == reglas.get("torneo"):
        v = aj["verificado"]
        r0 = v["resultado"].split(". ")[0].rstrip(".")
        a.append(f"Regla de menores (art. 49), verificada el {v.get('fecha')}: {r0[:1].lower()}{r0[1:]}.")
    a.append("Liguilla: tiempos extra de la final con un tercio de los goles esperados de 90 minutos y penales a 50/50; los "
             "mercados y combinadas de un partido de liguilla cuentan sólo los 90 minutos. El día, la hora y la sede de cada pierna "
             "son los del calendario de ESPN; mientras ESPN no publica el partido, los que anunció la liga según la prensa y, si "
             "no hay sede anunciada, la habitual del local.")
    if sim["meta"].get("torneo") == reglas.get("torneo") and (reglas.get("liguilla") or {}).get("fechas", {}).get("final_ida_opcion2"):
        a.append(_aviso_final_recorrida(reglas))
    if cal:
        a.append(f"El cálculo de series, contrastado con {cal['n_series']} series de liguilla de 2016 a 2025, le gana con claridad al "
                 f"50/50 (Brier {cal['brier']['simulador']:.4f} contra 0.2500) pero NO de forma concluyente a la frecuencia histórica "
                 f"con que avanza el mejor sembrado (diferencia de Brier {cal['dif_brier_vs_frecuencia']['dif']:+.4f}, "
                 f"ee {cal['dif_brier_vs_frecuencia']['ee']:.4f}); además subestima al mejor sembrado "
                 f"({cal['avanza_mejor_pronosticado']:.3f} pronosticado contra {cal['avanza_mejor_observado']:.3f} observado). "
                 "Ver produccion/SIMULADOR.md.")
    n = (des.get("acumulado") or {}).get("n", 0)
    a.append(f"Desempeño sellado: {n} partidos calificados hasta ahora" + (
        "; todavía no hay historial real hacia adelante." if n == 0 else
        "; con tan pocos partidos ninguna cifra es concluyente." if n < 100 else "."))
    return a


def leer_vivo(ruta: str | Path | None = None, ahora: pd.Timestamp | None = None) -> dict | None:
    """
    Último documento en vivo (salidas/vivo.json, lo escribe vivo.py; contrato en salidas/CONTRATO.md) si
    existe, se puede leer, no es de prueba y su `generado_utc` tiene menos de HORAS_VIVO horas; si no, None.
    """
    try:
        d = json.loads(Path(ruta or RUTA_VIVO).read_text(encoding="utf-8"))
        t = pd.Timestamp(d["generado_utc"])
        t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    except Exception:
        return None
    ahora = pd.Timestamp.now(tz="UTC") if ahora is None else ahora
    if not isinstance(d, dict) or d.get("prueba") or d.get("ejemplo") or not (pd.Timedelta(0) <= ahora - t < pd.Timedelta(hours=HORAS_VIVO)):
        return None
    return d


def incrustar_vivo(ruta_actual: str | Path | None = None, ruta_vivo: str | Path | None = None) -> bool:
    """
    Pone en el campo "vivo" de salidas/actual.json el documento en vivo vigente (o null) sin rehacer nada
    más; escritura atómica y sin copia al historial. Devuelve True si el archivo cambió.
    """
    ruta = Path(ruta_actual or RUTA_ACTUAL)
    doc = json.loads(ruta.read_text(encoding="utf-8"))
    nuevo = leer_vivo(ruta_vivo)
    if doc.get("vivo", None) == nuevo and "vivo" in doc:
        return False
    doc["vivo"] = nuevo
    escribir(doc, ruta, historial=False)
    return True


# ==================================================================================================
# Documento completo
# ==================================================================================================
def sin_torneo_siguiente(df: pd.DataFrame, corte) -> tuple[pd.DataFrame, str | None]:
    """
    Con la vuelta de la final ya jugada, ESPN puede listar enseguida el calendario del torneo siguiente y el
    pronosticador lo toma como «en curso» (el del primer partido después del corte): la página dejaba de festejar al
    campeón de la víspera y llenaba «Próximos partidos» con el torneo nuevo entero (V2-7 del workflow 10). Mientras
    ese torneo no empiece (ningún partido jugado antes del corte y el primero a más de DIAS_ANTES_DEL_SIGUIENTE días)
    se quitan sus filas (y las de torneos posteriores): el documento sigue siendo el del torneo recién terminado.
    Devuelve (df, nombre del torneo quitado o None si no se quitó nada).
    """
    c = simulador.a_utc(corte)
    if "orden_torneo" not in df.columns:
        return df, None
    jug = df[(df["estado"] == "jugado") & (df["fecha_utc"] < c)]
    if jug.empty:
        return df, None
    ultimo = jug.sort_values(["fecha_utc", "id"]).iloc[-1]
    t0, o0 = ultimo["torneo"], int(ultimo["orden_torneo"])
    vuelta_final = ((df["torneo"] == t0) & (df["fase"] == "final") & (df["pierna"] == 2) & (df["estado"] == "jugado")
                    & (df["fecha_utc"] < c))
    sig = df[(df["orden_torneo"] > o0) & (df["estado"] != "cancelado")]
    if not vuelta_final.any() or sig.empty:
        return df, None
    primero = sig["fecha_utc"].min()
    if pd.isna(primero) or primero - c <= pd.Timedelta(days=DIAS_ANTES_DEL_SIGUIENTE):
        return df, None
    nombre = str(sig.sort_values(["fecha_utc", "id"])["torneo"].iloc[0])
    return df[df["orden_torneo"] <= o0], nombre


def acotar_pendientes(pend: pd.DataFrame, etiquetas: list[str]) -> pd.DataFrame:
    """
    «Próximos partidos» no es el torneo entero (al inicio de un torneo eran 153 partidos y 143,548 px de página a
    390 px; V2-7 del workflow 10): todo lo que se juega hasta el último partido de las RONDAS_PENDIENTES primeras
    etiquetas limpias (dos jornadas, o la ida y la vuelta de una ronda de liguilla), y como mínimo los DIAS_PENDIENTES
    días siguientes al primer pendiente. Los reprogramados no cuentan como ronda (un «Jornada 2 (reprogramado)» o un
    «Reprogramado» lejano no se come el lugar de la jornada que sigue), pero entran si caen antes de ese tope.
    `pend` viene ordenado por fecha y `etiquetas` es la etiqueta de cada fila.
    """
    if pend.empty:
        return pend
    limpias = [e for e in etiquetas if "eprogramado" not in e]
    primeras = list(dict.fromkeys(limpias))[:RONDAS_PENDIENTES]
    tope = pend["fecha_utc"].iloc[0] + pd.Timedelta(days=DIAS_PENDIENTES)
    en = np.array([e in primeras for e in etiquetas], dtype=bool)
    if en.any():
        tope = max(tope, pend["fecha_utc"][en].max())
    return pend[(pend["fecha_utc"] <= tope).to_numpy()]


def construir(corte=None, n_sim: int = simulador.N_SIM, sellar: bool | None = None, ruta_sellos=None,
              ruta_desempeno=None, df: pd.DataFrame | None = None, pron=None) -> dict:
    """
    Arma el documento completo. `sellar` (por omisión: sólo cuando no se da `corte`) agrega los sellos
    de los partidos por jugar con ficha completa (los próximos MAX_DETALLE) antes de calificar.
    Devuelve el dict ya redondeado y listo para JSON.
    """
    t0 = time.time()
    df = datos.cargar() if df is None else df
    retro = corte is not None
    corte_utc = simulador.a_utc(corte)
    df, siguiente = sin_torneo_siguiente(df, corte_utc)        # tras la final: el torneo recién terminado, no el que viene
    if pron is None:
        pron = obtener_pronosticador(corte_utc, df=df if siguiente else None)
    reglas = simulador.cargar_reglas()
    torneo = getattr(pron, "torneo", None) or reglas["torneo"]
    df_t = df[(df["torneo"] == torneo) & (df["estado"] != "cancelado")]
    reg = df_t[df_t["fase"] == "regular"]
    jornadas = etiquetas_jornada(reg, int(reglas.get("jornadas", 17)))
    ctx = Contexto(corte_utc, df)
    meta_modelo = _modelo_meta(pron)

    # ---- partidos pendientes: mercados, combinadas y contexto ----
    if retro:
        pend = df_t[(df_t["fecha_utc"] >= corte_utc) & df_t["estado"].isin(["programado", "jugado", "en_juego"])]
    else:
        pend = df_t[df_t["estado"].isin(["programado", "en_juego"]) & (df_t["fecha_utc"] >= corte_utc - pd.Timedelta(hours=3))]
    pend = pend.sort_values(["fecha_utc", "id"])
    pend = acotar_pendientes(pend, [etiqueta_partido(f, jornadas) for _, f in pend.iterrows()])
    # mercados y combinadas sólo para los partidos con ficha completa (los próximos MAX_DETALLE)
    con_ficha, sin_ficha = pend.iloc[:MAX_DETALLE], pend.iloc[MAX_DETALLE:]
    paquete = (cb.paquete_partidos(pron, con_ficha, con_jornada=False) if len(con_ficha)
               else {"partidos": [], "p1_l": None, "p1_v": None})
    por_id = {int(d["id"]): d for d in paquete["partidos"]}
    if len(sin_ficha):
        por_id.update({int(d["id"]): d for d in pron.partidos(sin_ficha)})
    pendientes = [_partido_pendiente(fila, por_id[int(fila["id"])], ctx, etiqueta_partido(fila, jornadas), n < MAX_DETALLE)
                  for n, (_, fila) in enumerate(pend.iterrows())]

    # combinada de jornada: un pick por partido de la ronda más próxima (la etiqueta del primer pendiente; si esa
    # ronda tiene un solo partido, la siguiente en orden de fecha). Antes era el grupo más numeroso, que saltaba a la
    # ronda siguiente con una a medio jugar (las vueltas con dos idas por jugar) o a una jornada lejana.
    comb_jornada = None
    for etq in dict.fromkeys(p["etiqueta"] for p in pendientes):
        grupo = [{"id": p["id"], "local": p["local"], "visitante": p["visitante"], "lam_l": p["lam_l"], "lam_v": p["lam_v"],
                  "rho": p["rho"], "p1_l": paquete["p1_l"], "p1_v": paquete["p1_v"]} for p in pendientes if p["etiqueta"] == etq]
        if len(grupo) >= 2:
            cj = cb.combinada_jornada(grupo)
            comb_jornada = {"etiqueta": etq, "n_partidos": len(grupo), **cj}
            break

    # ---- sellos y desempeño ----
    if sellar is None:
        sellar = not retro
    n_nuevos = 0
    if sellar and len(pend):
        n_nuevos = len(sellos.sellar(pron, df, ruta_sellos, paquete=paquete))
    des = sellos.calificar(df, ruta_sellos, ruta_desempeno, escribir=not retro or ruta_desempeno is not None)
    oficiales = sellos.sellos_oficiales(df, ruta_sellos)
    desempeno = {k: des[k] for k in ("generado_utc", "n_sellos", "n_partidos_sellados", "n_calificados", "primer_sello_utc",
                                     "acumulado", "por_modelo", "por_torneo", "nota", "contra_mercado")}
    desempeno["partidos"] = [{k: f[k] for k in ("id", "fecha_utc", "local", "visitante", "gl", "gv", "resultado", "pick",
                                                "acierto_1x2", "marcador_exacto", "logloss")} |
                             {"combinadas": {v: (None if c is None else {"aciertos": c["aciertos"], "completa": c["completa"]})
                                             for v, c in f["combinadas"].items()},
                              "logloss_mercado": f["mercado"]["logloss"] if f.get("mercado") else None}
                             for f in des["partidos"][-40:]]

    # ---- simulación ----
    sim = simulador.simular(pron, corte_utc, df, n_sim=n_sim, reglas=reglas, torneo=torneo)

    # ---- tabla con forma ----
    tabla = []
    for f in sim["tabla_actual"]:
        # con la fase regular terminada la tabla es la final de esa fase: su forma no mezcla partidos de liguilla
        forma = ctx.forma(f["equipo"], 5, fase="regular" if sim["meta"]["regular_completa"] else None)
        tabla.append({**f, "zona": "liguilla" if f["pos"] <= sim["meta"]["clasifican"] else "fuera",
                      "forma": [x["resultado"] for x in forma], "forma_detalle": forma})

    # ---- proyección ----
    campos_eq = ("equipo", "pos_actual", "pts_actual", "pj_actual", "puntos_esperados", "ee_puntos_esperados", "pts_min",
                 "pts_max", "pos_esperada", "pos_mas_probable", "posicion", "p_lider", "p_top4", "p_clasifica",
                 "ee_p_clasifica", "p_semifinal", "ee_p_semifinal", "p_final", "ee_p_final", "p_campeon", "ee_p_campeon")
    tabla_final = sorted(({k: d[k] for k in campos_eq} for d in sim["por_equipo"]),
                         key=lambda d: (d["pos_esperada"], -d["puntos_esperados"]))
    campeon = [{"equipo": d["equipo"], "prob": d["p_campeon"], "ee": d["ee_p_campeon"], "p_final": d["p_final"],
                "p_semifinal": d["p_semifinal"], "p_clasifica": d["p_clasifica"]} for d in sim["por_equipo"]]
    proyeccion = {"n_sim": sim["meta"]["n_sim"], "n_muestras": sim["meta"]["n_muestras"], "semilla": sim["meta"]["semilla"],
                  "partidos_pendientes_regular": sim["meta"]["partidos_pendientes_regular"],
                  "regular_completa": sim["meta"]["regular_completa"], "tabla_final": tabla_final,
                  "cruces_cuartos": sim["cruces_cuartos"], "cuadro_mas_probable": sim["cuadro_mas_probable"],
                  "series_posibles": sim["series_posibles"], "campeon": campeon}

    # ---- liguilla ----
    lig = reglas.get("liguilla", {})
    clasificados = [f["equipo"] for f in sim["tabla_actual"][: sim["meta"]["clasifican"]]] if sim["meta"]["regular_completa"] else None
    liguilla = {"en_curso": bool(sim["series_reales"]), "clasificados": clasificados, "series": sim["series_reales"],
                "formato": {"cruces_cuartos": lig.get("cruces_cuartos"), "resiembra_semifinal": lig.get("resiembra_semifinal"),
                            "empate_global_cuartos_semis": lig.get("empate_global_cuartos_semis"),
                            "final_empate": lig.get("final_empate"), "cierra_en_casa": lig.get("cierra_en_casa"),
                            "fechas": lig.get("fechas") if torneo == reglas.get("torneo") else None}}
    try:
        proyeccion["titulos"] = titulos(ctx, df)
    except Exception as e:
        print(f"aviso: titulos falló: {e}", file=sys.stderr)
        proyeccion["titulos"] = {}
    try:
        liguilla["torneo"] = torneo_liguilla(pron, sim, reglas, clasificados, df, ctx)
    except Exception as e:
        print(f"aviso: torneo_liguilla falló: {type(e).__name__}: {e}", file=sys.stderr)
        liguilla["torneo"] = None
    for p in pendientes:                                         # de qué serie es, cómo va el global y qué necesita cada uno
        try:
            p["serie"] = serie_del_partido(p, liguilla["torneo"])
        except Exception as e:
            print(f"aviso: serie de {p.get('id')} falló: {type(e).__name__}: {e}", file=sys.stderr)
            p["serie"] = None
    try:
        liguilla["cuadro_proyectado"] = cuadro_proyectado(pron, sim, sim["series_reales"], clasificados)
    except Exception as e:                                       # no tumba la exportación
        print(f"aviso: cuadro_proyectado falló: {e}", file=sys.stderr)
        liguilla["cuadro_proyectado"] = None

    # ---- fuerzas, estadios, dominios ----
    fz = pron.fuerzas()
    if "equipo" not in fz.columns:                               # el provisional trae el equipo en el índice
        fz = fz.reset_index().rename(columns={fz.index.name or "index": "equipo"})
    fuerzas = [{k: (str(v) if k == "equipo" else float(v)) for k, v in fila.items()} for fila in fz.to_dict("records")]
    fuerzas.sort(key=lambda d: -d.get("rating", 0.0))
    cal = None
    ruta_cal = DIR_SALIDAS / f"calibracion_series_{meta_modelo.get('nombre')}.json"
    ruta_cal = ruta_cal if ruta_cal.exists() else RUTA_CALIBRACION
    if ruta_cal.exists():
        c = json.loads(ruta_cal.read_text(encoding="utf-8"))
        cal = {"modelo": c["modelo"], "n_series": c["n_series"], "avanza_mejor_observado": c["avanza_mejor_observado"]["media"],
               "avanza_mejor_pronosticado": c["media_pronosticada"]["simulador"],
               "brier": {k: c["metricas"][k]["brier"]["media"] for k in ("simulador", "frecuencia_previa", "mitad")},
               "dif_brier_vs_frecuencia": {k: c["diferencias"]["simulador_vs_frecuencia_previa"]["brier"][k] for k in ("dif", "ee")},
               "dif_brier_vs_mitad": {k: c["diferencias"]["simulador_vs_mitad"]["brier"][k] for k in ("dif", "ee")}}

    doc = {
        "meta": {"version_contrato": VERSION_CONTRATO, "generado_utc": pd.Timestamp.now(tz="UTC").isoformat(),
                 "corte_utc": corte_utc.isoformat(), "corte_local": corte_utc.tz_convert(datos.ZONA).strftime("%Y-%m-%d %H:%M"),
                 "retrospectivo": retro, "torneo": torneo, "modelo": meta_modelo, "partidos_en_la_historia": int(len(ctx.hist)),
                 "sellos_nuevos": int(n_nuevos), "proporcion_goles_1t": {"local": paquete.get("p1_l"), "visitante": paquete.get("p1_v")},
                 "segundos": None},
        "tabla": tabla,
        "pendientes": pendientes,
        "combinada_jornada": comb_jornada,
        "ultimos_resultados": _ultimos(df_t, corte_utc, jornadas, oficiales, meta_modelo.get("nombre"), _es_campeon(pron)),
        "proyeccion": proyeccion,
        "liguilla": liguilla,
        "fuerzas": fuerzas,
        "estadios": ctx.balance_estadios(),
        "dominios": ctx.dominios_liguilla(),
        "desempeno": desempeno,
        "calibracion_series": cal,
        # primero los avisos de datos del propio Pronosticador (p. ej. caché de variables desactualizada)
        "avisos": [f"DATOS: {x}" for x in getattr(pron, "avisos", [])] + _avisos(meta_modelo, des, reglas, sim, pendientes, cal) + (
            [f"El {siguiente} ya tiene calendario, pero empieza en más de {DIAS_ANTES_DEL_SIGUIENTE} días: la página sigue con el "
             f"{torneo}, que acaba de terminar."] if siguiente else []),
        # último documento en vivo (vivo.py); en una corrida retrospectiva no aplica
        "vivo": None if retro else leer_vivo(),
    }
    doc["meta"]["segundos"] = round(time.time() - t0, 1)
    return redondear(doc)


# ==================================================================================================
# Validación del propio JSON
# ==================================================================================================
OBLIGATORIOS = ("meta", "tabla", "pendientes", "combinada_jornada", "ultimos_resultados", "proyeccion", "liguilla",
                "fuerzas", "estadios", "dominios", "desempeno", "avisos")
BASICOS_PARTIDO = ("id", "detalle", "fecha_utc", "fecha_local", "hora_local", "etiqueta", "local", "visitante",
                   "lam_l", "lam_v", "p_local", "p_empate", "p_visitante", "pick", "marcador")
OBLIGATORIOS_PARTIDO = BASICOS_PARTIDO + ("estadio", "top5", "matriz", "mercados", "combinadas", "explica", "contexto", "momios")


def _probabilidades(o, ruta=""):
    """Recorre el documento y entrega (ruta, valor) de todo campo que debe ser una probabilidad."""
    if isinstance(o, dict):
        for k, v in o.items():
            r = f"{ruta}.{k}"
            es_p = (k in ("prob", "prob_conjunta", "prob_ingenua", "p_nula", "frecuencia", "prob_anunciada") or k.startswith("p_")
                    or k.startswith("ee_p_")) and k not in ("p_min", "p_max")
            if es_p and isinstance(v, (int, float)) and not isinstance(v, bool):
                yield r, v
            elif k in ("posicion", "matriz") and isinstance(v, list):
                for x in np.asarray(v, float).ravel():
                    yield r, float(x)
            else:
                yield from _probabilidades(v, r)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _probabilidades(v, f"{ruta}[{i}]")


def _validar_mercado(doc: dict) -> list[str]:
    """Errores de `desempeno.contra_mercado` y del `mercado` sellado de cada resultado reciente."""
    err = []
    num = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)      # noqa: E731
    des = doc["desempeno"] if isinstance(doc["desempeno"], dict) else {}
    cm = des.get("contra_mercado")
    if not isinstance(cm, dict):
        return ["desempeno.contra_mercado falta"]
    n, falta = cm.get("n"), [k for k in ("n", "n_sin_mercado", "n_sellados_con_mercado", "primer_sello_con_mercado_utc", "desde_local",
                                         "n_minimo", "mercado", "modelo", "dif_logloss", "ee_dif_logloss", "lectura") if k not in cm]
    if falta:
        return [f"desempeno.contra_mercado: falta {falta}"]
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        return [f"desempeno.contra_mercado.n inválido: {n}"]
    if cm["lectura"] not in sellos.LECTURAS_MERCADO:
        err.append(f"desempeno.contra_mercado.lectura desconocida: {cm['lectura']}")
    if n + cm["n_sin_mercado"] != des.get("n_calificados"):
        err.append("desempeno.contra_mercado: n + n_sin_mercado no es n_calificados")
    # desde_local sale de TODOS los sellos y n_sellados_con_mercado sólo de los oficiales de partidos que siguen
    # en los datos: puede haber fecha sin partidos (si ESPN cambia un id), nunca partidos sin fecha
    if cm["n_sellados_con_mercado"] < n or (cm["n_sellados_con_mercado"] > 0 and not cm["desde_local"]):
        err.append("desempeno.contra_mercado: n_sellados_con_mercado y desde_local no cuadran")
    if n == 0:
        if any(cm[k] is not None for k in ("mercado", "modelo", "dif_logloss", "ee_dif_logloss")) or cm["lectura"] != "sin_partidos":
            err.append("desempeno.contra_mercado: sin partidos pareados no debe traer cifras")
    else:
        mo, me = cm["modelo"] or {}, cm["mercado"] or {}
        if not all(num(o.get(k)) and o[k] >= 0 for o in (mo, me) for k in ("logloss", "brier", "rps")) or not num(cm["dif_logloss"]):
            err.append("desempeno.contra_mercado: métricas ausentes o negativas")
        elif abs(mo["logloss"] - me["logloss"] - cm["dif_logloss"]) > 2e-4:
            err.append("desempeno.contra_mercado: dif_logloss no es modelo − mercado")
        if mo.get("n") != n or me.get("n") != n:
            err.append("desempeno.contra_mercado: modelo y mercado deben contar los mismos partidos")
        if (cm["ee_dif_logloss"] is None) != (n < 2) or (cm["ee_dif_logloss"] is not None and not (num(cm["ee_dif_logloss"]) and cm["ee_dif_logloss"] >= 0)):
            err.append("desempeno.contra_mercado: ee_dif_logloss debe ser null sólo con menos de 2 partidos")
        if (cm["lectura"] == "pocos_partidos") != (n < cm["n_minimo"]):
            err.append("desempeno.contra_mercado: lectura no corresponde a n")
    for u in doc["ultimos_resultados"]:
        m = (u.get("pronostico") or {}).get("mercado")
        if m is None:
            continue
        if u["pronostico"].get("origen") != "sello":
            err.append(f"resultado {u.get('id')}: mercado en un pronóstico que no viene de un sello")
        if not all(num(m.get(k)) for k in ("p_local", "p_empate", "p_visitante", "logloss", "dif_logloss")):
            err.append(f"resultado {u.get('id')}: mercado sellado incompleto")
        elif abs(m["p_local"] + m["p_empate"] + m["p_visitante"] - 1.0) > 2e-4 or m["logloss"] < 0 or m.get("pick") not in PICKS:
            err.append(f"resultado {u.get('id')}: mercado sellado inválido")
    return err


def validar(doc: dict, peso: int | None = None) -> list[str]:
    """Lista de errores del documento (vacía = válido): campos, rangos, sumas y peso."""
    err = []
    for k in OBLIGATORIOS:
        if k not in doc:
            err.append(f"falta el campo '{k}'")
    if err:
        return err
    for k in ("generado_utc", "corte_utc", "torneo", "modelo"):
        if not doc["meta"].get(k):
            err.append(f"meta.{k} vacío")
    for k in ("nombre", "descripcion", "metricas"):
        if k not in doc["meta"].get("modelo", {}):
            err.append(f"meta.modelo.{k} falta")
    for ruta, v in _probabilidades(doc):
        if not (0.0 <= v <= 1.0):
            err.append(f"probabilidad fuera de [0,1] en {ruta}: {v}")
    n_eq = len(doc["tabla"])
    if n_eq != 18:
        err.append(f"la tabla tiene {n_eq} equipos")
    if [f["pos"] for f in doc["tabla"]] != list(range(1, n_eq + 1)):
        err.append("posiciones de la tabla no consecutivas")
    for p in doc["pendientes"]:
        for k in (OBLIGATORIOS_PARTIDO if p.get("detalle", True) else BASICOS_PARTIDO):
            if k not in p:
                err.append(f"partido {p.get('id')}: falta '{k}'")
        if all(k in p for k in ("p_local", "p_empate", "p_visitante")):
            s = p["p_local"] + p["p_empate"] + p["p_visitante"]
            if abs(s - 1.0) > 2e-4:
                err.append(f"partido {p['id']}: 1X2 suma {s}")
            if p["pick"]["resultado"] not in PICKS:
                err.append(f"partido {p['id']}: pick inválido")
        if not (p.get("lam_l", 0) > 0 and p.get("lam_v", 0) > 0):
            err.append(f"partido {p.get('id')}: lambdas no positivas")
        for v, c in (p.get("combinadas") or {}).items():
            if c is not None and len(c["picks"]) != 4:
                err.append(f"partido {p['id']}: la combinada {v} no tiene 4 picks")
    tf = doc["proyeccion"]["tabla_final"]
    if len(tf) != n_eq:
        err.append("proyeccion.tabla_final incompleta")
    s = sum(d["prob"] for d in doc["proyeccion"]["campeon"])
    if abs(s - 1.0) > 2e-3:
        err.append(f"las probabilidades de campeón suman {s}")
    for d in tf:
        if abs(sum(d["posicion"]) - 1.0) > 2e-3:
            err.append(f"distribución de lugar de {d['equipo']} no suma 1")
    s = sum(d["p_clasifica"] for d in tf)
    if abs(s - 8.0) > 5e-3:
        err.append(f"las probabilidades de clasificar suman {s} (deben sumar 8)")
    if not isinstance(doc["avisos"], list) or not doc["avisos"]:
        err.append("avisos vacío")
    err += _validar_mercado(doc)
    if peso is None:
        peso = len(json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if peso >= PESO_MAXIMO:
        err.append(f"el JSON pesa {peso / 1024:.0f} KB (máximo 600)")
    return err


def escribir(doc: dict, ruta: str | Path | None = None, historial: bool = True) -> tuple[Path, int]:
    """Escribe el JSON compacto (y la copia fechada por corte); devuelve (ruta, bytes)."""
    ruta = Path(ruta or RUTA_ACTUAL)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(texto, encoding="utf-8")
    tmp.replace(ruta)                                           # la página nunca lee un archivo a medias
    if historial:
        d = ruta.parent / "historial"
        d.mkdir(exist_ok=True)
        sello = pd.Timestamp(doc["meta"]["corte_utc"]).strftime("%Y%m%dT%H%MZ")
        (d / f"actual_{sello}.json").write_text(texto, encoding="utf-8")
    return ruta, len(texto.encode("utf-8"))


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Arma salidas/actual.json para la página")
    ap.add_argument("--corte", default=None, help="AAAA-MM-DDTHH:MM (hora de CDMX); por omisión, ahora")
    ap.add_argument("--n-sim", type=int, default=simulador.N_SIM)
    ap.add_argument("--sin-sello", action="store_true", help="no agrega sellos nuevos")
    ap.add_argument("--salida", default=None, help="ruta del JSON (por omisión salidas/actual.json)")
    a = ap.parse_args(argv)
    retro = a.corte is not None
    doc = construir(a.corte, n_sim=a.n_sim, sellar=False if (a.sin_sello or retro) else None)
    err = validar(doc)
    if err:
        print("JSON INVÁLIDO, no se escribe:\n  " + "\n  ".join(err[:20]))
        return 1
    if retro and a.salida is None:
        ruta = DIR_HISTORIAL / f"retro_{pd.Timestamp(doc['meta']['corte_utc']).strftime('%Y%m%dT%H%MZ')}.json"
        ruta, peso = escribir(doc, ruta, historial=False)        # una corrida retrospectiva no pisa actual.json
    else:
        ruta, peso = escribir(doc, a.salida)
    top = ", ".join(f"{d['equipo']} {d['prob']:.3f}" for d in doc["proyeccion"]["campeon"][:5])
    print(f"{ruta}  {peso / 1024:.0f} KB  modelo={doc['meta']['modelo']['nombre']}  pendientes={len(doc['pendientes'])}  "
          f"sellos nuevos={doc['meta']['sellos_nuevos']}  {doc['meta']['segundos']} s")
    print("campeón: " + top)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
