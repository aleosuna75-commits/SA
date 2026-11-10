# -*- coding: utf-8 -*-
"""
Exportación del JSON que consume la página: salidas/actual.json (y una copia fechada en
salidas/historial/). Un solo comando rehace TODO con lo jugado hasta el corte:

    cd /home/user/SA/ligamx && python3 -m produccion.exportar [--corte AAAA-MM-DDTHH:MM]

Pasos: ajusta el Pronosticador (el campeón si existe modelo/campeon.json; si no, el provisional),
sella los pronósticos de los partidos que no han empezado (sólo sin --corte), califica los sellos de
lo ya jugado, arma mercados y combinadas, corre el simulador y escribe el JSON (descrito campo por
campo en salidas/CONTRATO.md). Probabilidades con 4 decimales; el archivo debe pesar menos de 600 KB.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

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
SIN_REDONDEO = {"lat", "lon"}
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
    if not detalle:
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
            t = arnes.leer_pred(nombre, periodo, gran)
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


def torneo_liguilla(pron, sim: dict, reglas: dict, clasificados: list[str] | None, df: pd.DataFrame) -> dict:
    """
    La liguilla con estructura de torneo: siembra, y por ronda (cuartos, semifinal, final) cada serie con el
    pronóstico de su IDA y su VUELTA (goles esperados, 1X2, marcador más probable y los 5 primeros), el marcador
    global más probable y la probabilidad exacta de avanzar. Lo ya jugado es real; lo demás se pronostica con las
    lambdas de liguilla. Antes de que acabe la fase regular la siembra es la esperada (los 8 con más probabilidad
    de clasificar, por su lugar esperado). Las rondas siguientes siguen la ruta de los favoritos con resiembra.
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
    sedes = _sedes_por_equipo()
    reales = {(r["fase"], frozenset((r["mejor"], r["peor"]))): r for r in sim.get("series_reales", [])}
    fechas = (reglas.get("liguilla") or {}).get("fechas") or {}
    filas = df.set_index("id") if "id" in df.columns else df
    alternativas = {c["llave"]: c["opciones"] for c in sim.get("cruces_cuartos", [])}
    posibles = sim.get("series_posibles", {})

    def piernas(det: dict) -> list[dict]:
        out = []
        for p in det["piernas"]:
            d = {"pierna": p["pierna"], "nombre": "Ida" if p["pierna"] == 1 else "Vuelta", "id": p.get("id"),
                 "fecha_utc": p.get("fecha_utc"), "fecha_local": None, "hora_local": None,
                 "local": p["local"], "visitante": p["visitante"], "estadio": sedes.get(p["local"]),
                 "jugado": bool(p["jugado"])}
            if p.get("id") is not None and p["id"] in filas.index:
                f = filas.loc[p["id"]]
                d["fecha_local"] = str(f.get("fecha_local")) if pd.notna(f.get("fecha_local")) else None
                d["hora_local"] = str(f.get("hora_local")) if pd.notna(f.get("hora_local")) else None
            if p["jugado"]:
                d.update({"gl": p["gl"], "gv": p["gv"]})
            else:
                mm = p.get("marcadores") or []
                d.update({"gl": None, "gv": None, "lam_l": p["lam_l"], "lam_v": p["lam_v"], "p_local": p["p_local"],
                          "p_empate": p["p_empate"], "p_visitante": p["p_visitante"],
                          "marcador": mm[0] if mm else None, "marcadores": mm})
            out.append(d)
        return out

    def serie(llave: str, a: str, b: str, fase: str, viene_de=None) -> dict:
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
        return {"llave": llave, "fase": fase, "real": bool(real), "viene_de": viene_de,
                "mejor": {"equipo": mejor, "siembra": pos[mejor]}, "peor": {"equipo": peor, "siembra": pos[peor]},
                "piernas": piernas(det),
                "global": {"probable": glob[0] if glob else None, "top": glob, "p_gana_mejor": det.get("p_global_mejor"),
                           "p_empate": det.get("p_global_empate"), "p_gana_peor": det.get("p_global_peor")},
                "p_avanza_mejor": pm, "p_avanza_peor": float(det["p_avanza_peor"]), "favorito": fav,
                "p_favorito": float(pm if fav == mejor else 1 - pm), "decidida": bool(det.get("decidida")),
                "ganador": det.get("ganador"), "regla_empate": det.get("regla_empate"), "alternativas": alt}

    cuartos = [serie(f"C{i + 1}", siembra[a - 1], siembra[b - 1], "cuartos") for i, (a, b) in enumerate(((1, 8), (2, 7), (3, 6), (4, 5)))]
    de = {c["favorito"]: c["llave"] for c in cuartos}
    vivos = sorted(de, key=lambda e: pos[e])
    semis = [serie("S1", vivos[0], vivos[3], "semifinal", [de[vivos[0]], de[vivos[3]]]),
             serie("S2", vivos[1], vivos[2], "semifinal", [de[vivos[1]], de[vivos[2]]])]
    final = serie("F", semis[0]["favorito"], semis[1]["favorito"], "final", ["S1", "S2"])
    todas = cuartos + semis + [final]
    if all(s_["decidida"] for s_ in todas):
        estado = "terminado"
    elif sim.get("series_reales"):
        estado = "en_curso"
    else:
        estado = "definido" if clasificados else "proyectado"
    camp = final["favorito"]
    return {"estado": estado, "origen_siembra": origen,
            "siembra": [{"pos": i + 1, "equipo": e, "p_clasifica": pe[e]["p_clasifica"], "p_semifinal": pe[e]["p_semifinal"],
                         "p_final": pe[e]["p_final"], "p_campeon": pe[e]["p_campeon"]} for i, e in enumerate(siembra)],
            "rondas": [{"fase": "cuartos", "nombre": "Cuartos de final", "fechas": {"ida": fechas.get("cuartos_ida"), "vuelta": fechas.get("cuartos_vuelta")}, "series": cuartos},
                       {"fase": "semifinal", "nombre": "Semifinales", "fechas": {"ida": fechas.get("semis_ida"), "vuelta": fechas.get("semis_vuelta")}, "series": semis},
                       {"fase": "final", "nombre": "Final", "fechas": {"ida": fechas.get("final_ida"), "vuelta": fechas.get("final_vuelta")}, "series": [final]}],
            "campeon_ruta": camp, "campeon_decidido": bool(final["decidida"]), "p_campeon_ruta": pe[camp]["p_campeon"],
            "nota": "Ruta de los favoritos, serie por serie y con resiembra en semifinales. El porcentaje de cada serie es la "
                    "probabilidad de avanzar en esa serie; la probabilidad de campeón de cada equipo (simulación completa) "
                    "considera todos los caminos posibles."}


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
        "Lesiones, convocatorias y alineaciones del día no se modelan (sólo se muestran si existen en config/actualidad.json).",
        "Los momios de ESPN son de referencia. En la historia el mercado de cierre ha sido mejor que cualquier modelo propio; "
        "una diferencia entre el modelo y el momio NO es por sí misma una apuesta con valor.",
        "Mercados de cantidad de goles (más/menos, ambos anotan, goles por mitad) discriminan poco: con Poisson, "
        "«ambos anotan» sale subestimado unos 3 puntos (0.509 pronosticado vs 0.543 observado en desarrollo). "
        "No se ofrecen picks de córners ni de tarjetas: no le ganan a la frecuencia de la liga.",
        "Las combinadas usan la probabilidad conjunta exacta del modelo de marcador (no el producto de las marginales); "
        "entre partidos distintos se suponen independientes.",
        "Simulación: " + f"{sim['meta']['n_sim']:,} torneos simulados repartidos en {sim['meta']['n_muestras']:,} muestras de los "
        "parámetros; cada probabilidad trae su error de Monte Carlo (ee_*). La incertidumbre del propio modelo "
        "(que la forma de los equipos cambie) no está en ese error.",
        "Desempates de la tabla: los goles de visitante se cuentan sobre las primeras 8 visitas de cada equipo (aproximación "
        "de la regla del mismo número de visitas); el Fair Play sale de tarjetas.csv (sin sanciones de escritorio ni cuerpo "
        "técnico) y los partidos simulados no suman tarjetas; el sorteo es al azar.",
        "No se simula la resta de 3 puntos por la regla de menores (art. 49): a los 7 clubes que les faltan minutos les "
        "alcanza con un partido, según config/torneo.json.",
        "Liguilla: tiempos extra de la final con un tercio de los goles esperados de 90 minutos y penales a 50/50. "
        "La localía se toma de la sede habitual de cada club (la sede de Cruz Azul en liguilla no está confirmada). "
        "Si Toluca avanza en la Copa Intercontinental la final se recorre al 24 y 27 de diciembre.",
    ]
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


# ==================================================================================================
# Documento completo
# ==================================================================================================
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
    if pron is None:
        pron = obtener_pronosticador(corte_utc)
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
    # mercados y combinadas sólo para los partidos con ficha completa (los próximos MAX_DETALLE)
    con_ficha, sin_ficha = pend.iloc[:MAX_DETALLE], pend.iloc[MAX_DETALLE:]
    paquete = (cb.paquete_partidos(pron, con_ficha, con_jornada=False) if len(con_ficha)
               else {"partidos": [], "p1_l": None, "p1_v": None})
    por_id = {int(d["id"]): d for d in paquete["partidos"]}
    if len(sin_ficha):
        por_id.update({int(d["id"]): d for d in pron.partidos(sin_ficha)})
    pendientes = [_partido_pendiente(fila, por_id[int(fila["id"])], ctx, etiqueta_partido(fila, jornadas), n < MAX_DETALLE)
                  for n, (_, fila) in enumerate(pend.iterrows())]

    # combinada de jornada: un pick por partido del grupo más numeroso de los próximos partidos
    comb_jornada = None
    if pendientes:
        cuenta = pd.Series([p["etiqueta"] for p in pendientes]).value_counts()
        etq = cuenta.index[0]
        grupo = [{"id": p["id"], "local": p["local"], "visitante": p["visitante"], "lam_l": p["lam_l"], "lam_v": p["lam_v"],
                  "rho": p["rho"], "p1_l": paquete["p1_l"], "p1_v": paquete["p1_v"]} for p in pendientes if p["etiqueta"] == etq]
        if len(grupo) >= 2:
            cj = cb.combinada_jornada(grupo)
            comb_jornada = {"etiqueta": etq, "n_partidos": len(grupo), **cj}

    # ---- sellos y desempeño ----
    if sellar is None:
        sellar = not retro
    n_nuevos = 0
    if sellar and len(pend):
        n_nuevos = len(sellos.sellar(pron, df, ruta_sellos, paquete=paquete))
    des = sellos.calificar(df, ruta_sellos, ruta_desempeno, escribir=not retro or ruta_desempeno is not None)
    oficiales = sellos.sellos_oficiales(df, ruta_sellos)
    desempeno = {k: des[k] for k in ("generado_utc", "n_sellos", "n_partidos_sellados", "n_calificados", "primer_sello_utc",
                                     "acumulado", "por_modelo", "por_torneo", "nota")}
    desempeno["partidos"] = [{k: f[k] for k in ("id", "fecha_utc", "local", "visitante", "gl", "gv", "resultado", "pick",
                                                "acierto_1x2", "marcador_exacto", "logloss")} |
                             {"combinadas": {v: (None if c is None else {"aciertos": c["aciertos"], "completa": c["completa"]})
                                             for v, c in f["combinadas"].items()}}
                             for f in des["partidos"][-40:]]

    # ---- simulación ----
    sim = simulador.simular(pron, corte_utc, df, n_sim=n_sim, reglas=reglas, torneo=torneo)

    # ---- tabla con forma ----
    tabla = []
    for f in sim["tabla_actual"]:
        forma = ctx.forma(f["equipo"], 5)
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
                            "fechas": lig.get("fechas")}}
    try:
        proyeccion["titulos"] = titulos(ctx, df)
    except Exception as e:
        print(f"aviso: titulos falló: {e}", file=sys.stderr)
        proyeccion["titulos"] = {}
    try:
        liguilla["torneo"] = torneo_liguilla(pron, sim, reglas, clasificados, df)
    except Exception as e:
        print(f"aviso: torneo_liguilla falló: {type(e).__name__}: {e}", file=sys.stderr)
        liguilla["torneo"] = None
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
        "avisos": [f"DATOS: {x}" for x in getattr(pron, "avisos", [])] + _avisos(meta_modelo, des, reglas, sim, pendientes, cal),
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
