# -*- coding: utf-8 -*-
"""
Variables "a la fecha" (sin fuga) para cada partido de la Liga MX.

Idea central: el historial se RECORRE en orden cronológico. Un partido jugado entra al estado
(`Estado.ingerir`) cuando ya es conocido, y las variables de un partido se calculan leyendo el estado
tal como está en su corte (`Estado.variables`), sin modificarlo. Así cada valor depende sólo del pasado
y recalcular con un historial truncado da exactamente lo mismo (ver pruebas/test_variables.py).

Qué se conoce y cuándo (parámetro `corte`):
  * 'partido' (por omisión): un partido jugado se da por conocido 3 horas después de su inicio; el corte
    de cada partido es su propia hora de inicio. Para los pendientes equivale a "todo lo jugado".
  * 'bloque': el corte es el lunes o viernes 00:00 (hora de la Ciudad de México) anterior al partido; sólo
    se usan partidos que EMPEZARON antes de ese corte (protocolo walk-forward por bloque).
  * 'dia': igual, con corte a las 00:00 locales del día del partido.
El calendario (fechas de partidos jugados o programados) se considera público de antemano: descanso,
partidos en 14 días y hora local salen del calendario, no de resultados.

API:
  construir(partidos_todos=None, hasta=None, corte='partido', ...) -> DataFrame (una fila por partido
      jugado desde 2010 y por cada PROGRAMADO). Sufijos: _l local, _v visitante, _dif = local - visitante.
  actualizar(corte='partido')  -> reconstruye sólo las filas afectadas por lo nuevo y guarda la caché.
  cargar(corte='partido')      -> lee modelo/cache/variables[_<corte>].parquet.
  catalogo()                   -> tabla de variables (grupo, definición, disponible al pronosticar).
  columnas(df, ...)            -> nombres de variables filtrando las "_real" y las de mercado.

Línea de comandos:
  python3 variables.py              actualización incremental de las cachés 'partido' y 'bloque'
  python3 variables.py --completo   reconstrucción completa
  python3 variables.py --catalogo   tabla de variables con cobertura (Markdown)
  python3 variables.py --analisis   análisis exploratorio en DESARROLLO (Markdown)

Todos los hiperparámetros de este módulo son constantes fijadas de antemano (convenciones), no se
ajustaron mirando resultados. Lo que sí se estima (media de liga, credibilidad de la ventaja de local
por estadio, regresión de goles esperados) se estima sólo con partidos anteriores al corte.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import math
import sys
import time
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent            # .../ligamx
DIR_DATOS = RAIZ / "datos"
RUTA_PARTIDOS = DIR_DATOS / "partidos.csv"
RUTA_TARJETAS = DIR_DATOS / "tarjetas.csv"
RUTA_ALINEACIONES = DIR_DATOS / "alineaciones.csv"
RUTA_SEDES = DIR_DATOS / "estadios_sedes.csv"
RUTA_TORNEO = RAIZ / "config" / "torneo.json"
DIR_CACHE = RAIZ / "modelo" / "cache"
ZONA = "America/Mexico_City"

VERSION = "1.0"                 # cambiarla invalida las cachés
DESDE = "2010-01-01"            # primera fecha con fila de variables (el historial arranca en 2001)
NAN = float("nan")
DIA = 86400

# --- Convenciones fijadas de antemano (no ajustadas con resultados) -------------------------------
RETRASO_INFO_S = 3 * 3600       # corte='partido': un partido se conoce 3 h después de empezar
VIDA_MEDIA_FORMA = 5.0          # partidos; peso exponencial 0.5**(k / 5) del k-ésimo más reciente
MAX_FORMA_EXP = 30              # partidos que entran a la forma exponencial
K_ELO, ELO_LOCAL = 20.0, 70.0   # Elo simple de referencia (fuerza base)
ELO_INICIAL, ELO_NUEVO = 1500.0, 1450.0
K_H2H = 6.0                     # credibilidad del historial directo: Z = n / (n + 6)
K_ARBITRO = 10.0                # credibilidad del árbitro: Z = n / (n + 10)
UMBRAL_HABITUAL = 0.6           # titular habitual: titular en >= 60% de los últimos 10 partidos
MIN_ONCES = 5                   # partidos con once válido para hablar de titulares habituales
ALTURA_M = 1800                 # "altura": sede a 1,800 m o más (León, 1,800 ± 10 m, queda dentro)
VENTANA_LIGA = 1530             # partidos de fase regular (10 torneos) para medias de liga
VENTANA_LIGA_GOLES = 612        # partidos de fase regular (4 torneos) para la media de goles
VENTANA_XG = 1224               # observaciones equipo-partido (4 torneos) de la regresión de goles esperados
VENTANA_SEDE = 85               # partidos de local en la sede (~5 años) para la ventaja de local
MAX_DESCANSO = 30.0             # tope de los días de descanso
TOPE_DIF_DESCANSO = 10.0        # la diferencia de descanso se calcula con tope de 10 días
CADUCA_SUSPENSION_DIAS = 90     # una suspensión no se arrastra más de 90 días

# Series que los datos no alcanzan a decidir (ESPN no trae la tanda de penales): hecho histórico.
GANADOR_MANUAL = {("Clausura 2004", "final", "Chivas", "Pumas"): "Pumas"}

# Errores conocidos de ESPN en la sede (la sede se conoce antes del partido: corregirla no fuga nada).
SEDE_CORREGIDA_PARTIDO = {"479308": "akron"}             # vuelta de la final del Clausura 2017: fue en el Estadio Chivas
SEDE_CORREGIDA_LOCAL = {("3150", "Necaxa"): "victoria"}  # Necaxa 2010-11 aparece en el Nemesio Díez; jugó en el Victoria
SEDE_NO_ANTES = {"akron": "2010-07-30"}                  # ESPN lo usa antes de su apertura: se imputa la sede habitual
VENTANA_HABITUAL = 6                                     # partidos de local (del último año) para la sede habitual

FASES_RONDA = {"regular": 0, "repechaje": 1, "cuartos": 2, "semifinal": 3, "final": 4}
PRIMER_TORNEO_DESARROLLO = "Apertura 2016"
ULTIMO_TORNEO_DESARROLLO = "Clausura 2025"

_COLS_NUM = [
    "gl", "gv", "gl_et", "gv_et", "pen_l", "pen_v", "pierna", "asistencia",
    "tiros_l", "tiros_v", "tiros_puerta_l", "tiros_puerta_v", "corners_l", "corners_v", "faltas_l", "faltas_v",
    "amarillas_l", "amarillas_v", "rojas_l", "rojas_v", "posesion_l", "posesion_v",
    "penales_tirados_l", "penales_tirados_v", "tiene_stats",
    "ml_l", "ml_e", "ml_v", "total_linea", "over", "under", "ml_l_abre", "ml_e_abre", "ml_v_abre",
    "over_abre", "under_abre",
]
_COLS_TXT = ["id", "torneo", "fase", "estado", "local", "visitante", "estadio_id", "arbitro", "serie"]


# ==================================================================================================
# Reglas del torneo conocidas de antemano (formato de competencia por torneo)
# ==================================================================================================
def orden_torneo(torneo: str) -> int:
    """Ordinal cronológico: año * 2 + (1 si Apertura); torneos consecutivos difieren en 1."""
    tipo, anio = torneo.rsplit(" ", 1)
    return int(anio) * 2 + (1 if tipo.startswith("Apertura") else 0)


def periodo_de(torneo: str) -> str:
    """calentamiento (hasta Clausura 2016) | desarrollo (Apertura 2016 a Clausura 2025) | prueba."""
    k = orden_torneo(torneo)
    if k < orden_torneo(PRIMER_TORNEO_DESARROLLO):
        return "calentamiento"
    return "desarrollo" if k <= orden_torneo(ULTIMO_TORNEO_DESARROLLO) else "prueba"


_OT = orden_torneo
# La suspensión por acumular 5 amarillas existe desde el Apertura 2021 (antes era multa). Comprobado con
# los datos: de los "suspendidos" que la regla habría dado entre 2013 y 2020, ~78% jugó el partido
# siguiente; desde el Apertura 2021, menos de 3%.
OT_AMARILLAS_SUSPENDEN = orden_torneo("Apertura 2021")
_CONFIG_TORNEO: dict | None = None


def _config_torneo() -> dict:
    """Lee config/torneo.json una vez (reglas del torneo en curso); {} si no existe."""
    global _CONFIG_TORNEO
    if _CONFIG_TORNEO is None:
        try:
            _CONFIG_TORNEO = json.loads(RUTA_TORNEO.read_text(encoding="utf-8"))
        except Exception:
            _CONFIG_TORNEO = {}
    return _CONFIG_TORNEO


def formato_torneo(torneo: str) -> dict:
    """
    Formato de competencia del torneo (reglamento, conocido antes de que empiece):
      partidos = partidos de fase regular por equipo; zona = último lugar con postemporada (liguilla
      directa o repechaje/play-in); directo = lugares con pase directo a cuartos;
      gol_visitante = si el gol de visitante desempataba cuartos y semifinales.
    Verificado con los datos: equipos en repechaje y cuartos por torneo, y quién avanzó en las series
    empatadas (gol de visitante del Apertura 2012 al Clausura 2021; después, sólo la tabla).
    """
    ot = _OT(torneo)
    if ot <= _OT("Clausura 2002"):
        partidos = 18
    elif ot <= _OT("Clausura 2004"):
        partidos = 19
    else:
        partidos = 18 if torneo == "Apertura 2019" else 17
    if ot <= _OT("Clausura 2020"):
        zona, directo = 8, 8
    elif ot <= _OT("Clausura 2023"):
        zona, directo = 12, 4
    elif ot <= _OT("Apertura 2025"):
        zona, directo = 10, 6
    else:
        zona, directo = 8, 8
    cfg = _config_torneo()
    if cfg.get("torneo") == torneo:                      # el torneo en curso manda desde la configuración
        try:
            partidos = int(cfg.get("jornadas", partidos))
            directo = int(cfg.get("clasifican_directo", directo))
            zona = directo if not cfg.get("play_in", {}).get("existe", False) else max(zona, directo)
        except Exception:
            pass
    gol_visitante = _OT("Apertura 2012") <= ot <= _OT("Clausura 2021")
    return {"partidos": partidos, "zona": zona, "directo": directo, "gol_visitante": gol_visitante}


# ==================================================================================================
# Catálogo de variables: (base, lados, grupo, disponible, desde, definición)
#   lados: '' una sola columna; 'lv' -> base_l y base_v; 'lvd' -> además base_dif (= local - visitante);
#          'l' o 'v' -> sólo ese lado.
#   disponible: 'si' al pronosticar; 'no' (variables _real: requieren el once que jugó);
#               'mercado' (sólo si ya hay momios; no existen para rondas futuras);
#               'si*' (árbitro: sólo cuando ya hay designación).
# ==================================================================================================
def _cat_forma():
    filas = []
    stats = (("ppp", "puntos por partido"), ("gf", "goles a favor por partido"),
             ("gc", "goles en contra por partido"), ("dg", "diferencia de goles por partido"))
    for n, mn in ((5, 3), (10, 5)):
        for k, txt in stats:
            filas.append((f"forma{n}_{k}", "lvd" if k in ("ppp", "dg") else "lv", "a) forma", "si",
                          f"{txt}, últimos {n} partidos de liga del equipo (cualquier fase y torneo; mínimo {mn})"))
            filas.append((f"forma{n}_cond_{k}", "lvd" if (n == 10 and k in ("ppp", "dg")) else "lv", "a) forma", "si",
                          f"{txt}, últimos {n} partidos EN SU CONDICIÓN (el local sólo de local, el visitante sólo "
                          f"de visita; mínimo {mn})"))
    for k, txt in stats:
        filas.append((f"formaexp_{k}", "lvd" if k in ("ppp", "dg") else "lv", "a) forma", "si",
                      f"{txt} con peso exponencial (vida media {VIDA_MEDIA_FORMA:g} partidos, últimos {MAX_FORMA_EXP}; mínimo 3)"))
        filas.append((f"formaexp_cond_{k}", "lv", "a) forma", "si",
                      f"{txt} con peso exponencial, sólo partidos en su condición (mínimo 3)"))
    filas.append(("torneo_pj", "lv", "a) forma", "si", "partidos jugados en el torneo en curso (todas las fases)"))
    for k, txt in stats:
        filas.append((f"torneo_{k}", "lvd" if k in ("ppp", "dg") else "lv", "a) forma", "si",
                      f"{txt} en el torneo en curso (todas las fases; vacío sin partidos)"))
    return filas


def _cat_rachas():
    nombres = (("vict", "victorias consecutivas"), ("inv", "partidos sin perder"), ("singanar", "partidos sin ganar"),
               ("derr", "derrotas consecutivas"), ("anot", "partidos anotando"), ("sinanot", "partidos sin anotar"),
               ("cero", "partidos con portería en cero"))
    filas = []
    for k, txt in nombres:
        filas.append((f"racha_{k}", "lv", "b) rachas", "si",
                      f"racha vigente: {txt} (todos los partidos de liga, cruza torneos; tope 60)"))
        filas.append((f"racha_cond_{k}", "lv", "b) rachas", "si",
                      f"racha vigente en su condición (local en casa / visitante fuera): {txt}"))
    return filas


def _cat_juego():
    filas = []
    campos = (("tiros", "tiros totales"), ("tp", "tiros a puerta"), ("corners", "tiros de esquina"),
              ("faltas", "faltas cometidas"), ("xg", "goles esperados aproximados"))
    for k, txt in campos:
        for lado, quien in (("f", "a favor"), ("c", "en contra")):
            dif = "lvd" if k == "xg" else "lv"
            extra = (" (regresión lineal de goles sobre tiros fuera de puerta y tiros a puerta, ajustada al inicio de "
                     f"cada torneo con las {VENTANA_XG} observaciones equipo-partido anteriores)") if k == "xg" else ""
            filas.append((f"juego10_{k}_{lado}", dif, "g) juego", "si",
                          f"media de {txt} {quien} en los últimos 10 partidos con estadísticas (mínimo 5){extra}"))
    for k, txt in (("tiros", "tiros totales"), ("tp", "tiros a puerta"), ("xg", "goles esperados aproximados")):
        for lado, quien in (("f", "a favor"), ("c", "en contra")):
            filas.append((f"juego5_{k}_{lado}", "lv", "g) juego", "si",
                          f"media de {txt} {quien} en los últimos 5 partidos con estadísticas (mínimo 3)"))
    filas += [
        ("juego10_posesion", "lvd", "g) juego", "si", "posesión media (%) en los últimos 10 partidos con estadísticas (mínimo 3 con dato)"),
        ("juego10_amarillas", "lv", "g) juego", "si", "amarillas propias por partido, últimos 10 con estadísticas"),
        ("juego10_xgdif", "lvd", "g) juego", "si", "goles esperados a favor menos en contra, últimos 10 con estadísticas"),
        ("juego10_suerte_f", "lv", "g) juego", "si", "goles reales menos esperados A FAVOR por partido, últimos 10 (definición/suerte)"),
        ("juego10_suerte_c", "lv", "g) juego", "si", "goles reales menos esperados EN CONTRA por partido, últimos 10 (portero/suerte)"),
        ("juego_n", "lv", "g) juego", "si", "partidos con estadísticas disponibles entre los últimos 20 (máximo 10)"),
    ]
    return filas


CATALOGO = (
    [
        # ---- fuerza base ------------------------------------------------------------------------
        ("elo", "lvd", "0) fuerza base", "si",
         f"Elo simple previo al partido (K={K_ELO:g}, multiplicador por diferencia de goles, ventaja de local "
         f"{ELO_LOCAL:g} sólo al actualizar; equipos de 2001 en {ELO_INICIAL:g}, nuevos en {ELO_NUEVO:g}). "
         "Sólo referencia: las familias de modelos tienen mejores fuerzas"),
        ("liga_goles", "", "0) fuerza base", "si", f"goles por partido de la liga, últimos {VENTANA_LIGA_GOLES} partidos de fase regular"),
        ("liga_vl", "", "0) fuerza base", "si", f"ventaja de local de la liga en goles (local - visita por partido), últimos {VENTANA_LIGA} de fase regular"),
        ("liga_p_local", "", "0) fuerza base", "si", f"frecuencia de victoria local, últimos {VENTANA_LIGA} de fase regular"),
        ("liga_p_empate", "", "0) fuerza base", "si", f"frecuencia de empate, últimos {VENTANA_LIGA} de fase regular"),
    ]
    + _cat_forma()
    + _cat_rachas()
    + [
        # ---- c) tabla -----------------------------------------------------------------------------
        ("tabla_pos", "lvd", "c) tabla", "si", "posición en la tabla general del torneo antes del partido (puntos, DG, GF, nombre; vacío sin partidos). En liguilla es la tabla final (= sembrado)"),
        ("tabla_pj", "lv", "c) tabla", "si", "partidos de fase regular jugados en el torneo"),
        ("tabla_pts", "lv", "c) tabla", "si", "puntos en la fase regular del torneo"),
        ("tabla_ppp", "lvd", "c) tabla", "si", "puntos por partido en la fase regular del torneo"),
        ("tabla_dgpp", "lv", "c) tabla", "si", "diferencia de goles por partido en la fase regular del torneo"),
        ("tabla_dist8", "lv", "c) tabla", "si", "puntos propios menos puntos del 8.º lugar (positivo = arriba del 8.º)"),
        ("tabla_dist_zona", "lv", "c) tabla", "si", "puntos propios menos puntos del último lugar con postemporada según el formato del torneo (8, 12 o 10)"),
        ("tabla_rest", "lv", "c) tabla", "si", "partidos de fase regular que le faltan al equipo (según reglamento)"),
        ("tabla_clasificado", "lv", "c) tabla", "si", "1 si ya tiene asegurada la postemporada: menos equipos que lugares pueden igualarlo o pasarlo (conservador: los empates cuentan en contra)"),
        ("tabla_eliminado", "lv", "c) tabla", "si", "1 si ya no alcanza la zona: tantos equipos como lugares ya tienen más puntos que su máximo posible (conservador)"),
        ("jornada_est", "", "c) tabla", "si", "jornada estimada: promedio de partidos jugados de ambos + 1 (vacío en liguilla)"),
        ("avance_torneo", "", "c) tabla", "si", "fracción de la fase regular ya jugada por ambos (1 en liguilla)"),
        # ---- d) calendario ------------------------------------------------------------------------
        ("descanso", "lv", "d) calendario", "si", f"días desde el partido de liga anterior del equipo (calendario; tope {MAX_DESCANSO:g}). No ve copas ni torneos internacionales"),
        ("descanso_dif", "", "d) calendario", "si", f"diferencia de descanso local - visitante, cada uno con tope de {TOPE_DIF_DESCANSO:g} días"),
        ("pj14", "lvd", "d) calendario", "si", "partidos de liga del equipo en los 14 días previos (calendario)"),
        ("pausa_larga", "lv", "d) calendario", "si", "1 si descansó más de 10 días dentro del mismo torneo"),
        ("regreso_pausa", "", "d) calendario", "si", "1 si AMBOS vienen de más de 10 días sin jugar dentro del torneo (regreso de fecha FIFA u otra pausa)"),
        ("primer_partido_torneo", "lv", "d) calendario", "si", "1 si es el primer partido del equipo en el torneo"),
        ("pendientes_previos", "lv", "d) calendario", "si", "partidos del equipo anteriores a éste que aún no se conocen en el corte (programados o del mismo bloque): si > 0 la fila cambiará"),
        ("media_semana", "", "d) calendario", "si", "1 si se juega martes, miércoles o jueves (hora local)"),
        ("dia_semana", "", "d) calendario", "si", "día de la semana local (0 = lunes ... 6 = domingo)"),
        ("hora_local", "", "d) calendario", "si", "hora local de inicio en decimal (19.5 = 19:30)"),
        ("mes", "", "d) calendario", "si", "mes local del partido"),
        # ---- e) sede ------------------------------------------------------------------------------
        ("sede_altitud", "", "e) sede", "si", "altitud de la sede en metros (datos/estadios_sedes.csv)"),
        ("sede_altura", "", "e) sede", "si", f"1 si la sede está a {ALTURA_M} m o más"),
        ("sede_sintetico", "", "e) sede", "si", "1 si la cancha era de pasto sintético en esa fecha"),
        ("sede_imputada", "", "e) sede", "si", "1 si ESPN no trae estadio y se supuso la sede habitual del local"),
        ("sede_habitual_l", "", "e) sede", "si", "1 si el local juega en su sede habitual (la más frecuente en sus últimos 6 partidos de local del último año); 0 en mudanzas y sedes prestadas"),
        ("sede_compartida", "", "e) sede", "si", "1 si la sede es también la habitual de otro equipo activo (inmueble compartido)"),
        ("sede_tambien_v", "", "e) sede", "si", "1 si la sede es también la habitual del visitante (clásico en casa compartida)"),
        ("sede_alt_dif_v", "", "e) sede", "si", "altitud de la sede menos altitud de la sede habitual del visitante (m)"),
        ("sede_viaje_km_v", "", "e) sede", "si", "kilómetros (haversine) entre la sede habitual del visitante y esta sede"),
        ("sede_viaje_km_l", "", "e) sede", "si", "kilómetros entre la sede habitual del local y esta sede (0 si juega en casa)"),
        ("sede_n_l", "", "e) sede", "si", "partidos previos del local, como local, en esta sede (desde 2001)"),
        ("sede_vl_l", "", "e) sede", "si",
         f"ventaja de local del equipo EN ESTA SEDE en goles, con credibilidad: liga_vl + Z*(D - 2*liga_vl), donde D = "
         f"DG por partido de local aquí (últimos {VENTANA_SEDE}) menos su DG por partido de visita en el mismo lapso y "
         "Z = m/(m+K), m = n_l*n_v/(n_l+n_v); K es de Bühlmann-Straub y se reestima al inicio de cada torneo sólo con el pasado"),
        ("sede_vl_rel_l", "", "e) sede", "si", "exceso de esa ventaja sobre la media de la liga: Z*(D - 2*liga_vl)"),
        ("sede_vl_z_l", "", "e) sede", "si", "credibilidad Z usada en sede_vl_l (0 = sin historia o sin varianza entre sedes)"),
        ("visita_altura_n_v", "", "e) sede", "si", f"visitas previas del visitante a sedes de {ALTURA_M} m o más (últimas 20)"),
        ("visita_altura_dg_v", "", "e) sede", "si", "DG por partido del visitante en esas visitas a la altura (mínimo 3)"),
        ("visita_altura_rel_v", "", "e) sede", "si", "esa DG menos su DG por partido en sus últimas 40 visitas a sedes bajas (mínimo 3 y 3)"),
        ("visita_sint_n_v", "", "e) sede", "si", "visitas previas del visitante a canchas sintéticas (últimas 10)"),
        ("visita_sint_dg_v", "", "e) sede", "si", "DG por partido del visitante en canchas sintéticas (mínimo 3)"),
        ("visita_sint_rel_v", "", "e) sede", "si", "esa DG menos su DG por partido en sus últimas 40 visitas a pasto natural"),
        # ---- f) historial directo -------------------------------------------------------------------
        ("h2h_n", "", "f) h2h", "si", "enfrentamientos previos entre los dos equipos en la base (desde 2001)"),
        ("h2h6_pts_l", "", "f) h2h", "si",
         f"últimos 6 enfrentamientos: puntos por partido del local actual MENOS lo esperado por jugar en casa o fuera "
         f"(medias de la liga), encogido por credibilidad Z = n/(n+{K_H2H:g}) hacia 0"),
        ("h2h6_dg_l", "", "f) h2h", "si", "últimos 6: diferencia de goles por partido del local actual menos la ventaja de local de la liga (con su signo), encogida igual"),
        ("h2h10_pts_l", "", "f) h2h", "si", "igual que h2h6_pts_l con los últimos 10"),
        ("h2h10_dg_l", "", "f) h2h", "si", "igual que h2h6_dg_l con los últimos 10"),
        ("h2h_sede_n", "", "f) h2h", "si", "enfrentamientos previos con el local actual de local EN ESTA SEDE (se usan los últimos 6)"),
        ("h2h_sede_pts_l", "", "f) h2h", "si", "esos partidos: puntos por partido del local menos lo esperado en casa, encogido por credibilidad"),
        ("h2h_sede_dg_l", "", "f) h2h", "si", "esos partidos: DG por partido del local menos la ventaja de local de la liga, encogida"),
        ("h2h_lig_n", "", "f) h2h", "si", "partidos de liguilla previos entre ambos (se usan los últimos 10)"),
        ("h2h_lig_pts_l", "", "f) h2h", "si", "liguilla: puntos por partido del local actual menos lo esperado, encogido"),
        ("h2h_lig_dg_l", "", "f) h2h", "si", "liguilla: DG por partido del local actual ajustada por localía, encogida"),
        ("h2h_lig_series_n", "", "f) h2h", "si", "series de liguilla previas entre ambos (desde 2001)"),
        ("h2h_lig_series_bal_l", "", "f) h2h", "si", "series de liguilla ganadas por el local actual menos las ganadas por el visitante"),
        ("h2h_final_n", "", "f) h2h", "si", "partidos de FINAL previos entre ambos"),
        ("h2h_final_dg_l", "", "f) h2h", "si", "finales: DG por partido del local actual ajustada por localía, encogida"),
        ("h2h_final_series_n", "", "f) h2h", "si", "finales previas entre ambos"),
        ("h2h_final_series_bal_l", "", "f) h2h", "si", "finales ganadas por el local actual menos las ganadas por el visitante (dominio en finales)"),
    ]
    + _cat_juego()
    + [
        # ---- h) disciplina y ausencias --------------------------------------------------------------
        ("rojas_prev", "lv", "h) disciplina", "si", f"expulsados del equipo en su partido anterior (tarjetas.csv; 0 si fue hace más de {CADUCA_SUSPENSION_DIAS} días; vacío si ese partido aún no se conoce, pendientes_previos > 0)"),
        ("susp_n", "lvd", "h) disciplina", "si", "jugadores SUSPENDIDOS para este partido deducidos de tarjetas: expulsado en el partido anterior o, desde el Apertura 2021 (cuando empezó esa regla), amarilla múltiplo de 5 acumulada en el torneo (cuenta aparte en liguilla). Vacío si el partido anterior aún no se conoce"),
        ("susp_imp", "lvd", "h) disciplina", "si", "importancia de los suspendidos: suma de su proporción de titularidades en los últimos 10 partidos del equipo con once válido"),
        ("susp_titulares", "lv", "h) disciplina", "si", f"suspendidos que son titulares habituales (>= {UMBRAL_HABITUAL:.0%} de titularidades)"),
        ("aus_conv_n", "lv", "h) disciplina", "si", "titulares habituales que NO estuvieron en la lista (once + banca) del partido anterior: indicio de lesión, salida o castigo"),
        ("aus_conv_imp", "lv", "h) disciplina", "si", "suma de la proporción de titularidades de esos ausentes"),
        ("aus_tit_previa", "lvd", "h) disciplina", "si", "titulares habituales ausentes previsibles: suspendidos o fuera de la lista anterior (unión). Vacío si el partido anterior aún no se conoce"),
        # ---- i) alineación ----------------------------------------------------------------------------
        ("once_previa_hab", "lvd", "i) alineación", "si", "continuidad del once PREVISTO (once del último partido conocido menos suspendidos): suma de sus proporciones de titularidad en los últimos 10 partidos, entre 11 (1 = repite el once de siempre)"),
        ("once_previa_cambios", "lv", "i) alineación", "si", "cambios entre los dos últimos onces del equipo (0 a 11)"),
        ("once_previa_rot5", "lv", "i) alineación", "si", "rotación reciente: jugadores distintos usados como titulares en los últimos 5 partidos (11 a 55)"),
        ("once_real_hab", "lvd", "i) alineación", "no", "NO DISPONIBLE AL PRONOSTICAR: proporción media de titularidades (últimos 10) del once que SÍ jugó este partido"),
        ("once_real_cambios", "lv", "i) alineación", "no", "NO DISPONIBLE: cambios del once que jugó respecto del once anterior"),
        ("once_real_aus", "lvd", "i) alineación", "no", "NO DISPONIBLE: titulares habituales que no salieron de inicio en este partido"),
        ("once_real_acierto_previa", "lv", "i) alineación", "no", "NO DISPONIBLE: fracción del once previsto que efectivamente fue titular (mide la calidad de la versión previa)"),
        # ---- j) fase ---------------------------------------------------------------------------------
        ("es_liguilla", "", "j) fase", "si", "1 si no es fase regular (repechaje, cuartos, semifinal o final)"),
        ("ronda", "", "j) fase", "si", "0 regular, 1 repechaje/play-in, 2 cuartos, 3 semifinal, 4 final"),
        ("pierna", "", "j) fase", "si", "1 ida, 2 vuelta (vacío en fase regular y partido único)"),
        ("es_vuelta", "", "j) fase", "si", "1 si es el partido de vuelta de una serie"),
        ("global_gf_l", "", "j) fase", "si", "goles del local actual en la ida (sólo en la vuelta)"),
        ("global_gc_l", "", "j) fase", "si", "goles del visitante actual en la ida (sólo en la vuelta)"),
        ("global_dif_l", "", "j) fase", "si", "marcador global antes de la vuelta, visto por el local actual"),
        ("sembrado", "lvd", "j) fase", "si", "posición final en la tabla del torneo (sólo liguilla)"),
        ("empate_favorece_l", "", "j) fase", "si", "1 si en cuartos o semifinal el empate global favorece al local (mejor sembrado)"),
        ("empate_favorece_v", "", "j) fase", "si", "1 si favorece al visitante"),
        ("regla_gol_visitante", "", "j) fase", "si", "1 si en ese torneo el gol de visitante desempataba antes que la tabla (Apertura 2012 a Clausura 2021, cuartos y semifinal)"),
        ("ventaja_serie_l", "", "j) fase", "si", "ventaja efectiva del local al empezar la vuelta: global_dif_l + 0.5 si el empate lo favorece, - 0.5 si favorece al visitante"),
        ("lig_series6", "lvd", "j) fase", "si", "series de liguilla jugadas (terminadas) en los últimos 6 torneos y el actual"),
        ("lig_ganadas6", "lvd", "j) fase", "si", "series de liguilla ganadas en ese lapso"),
        ("finales10", "lvd", "j) fase", "si", "finales jugadas en los últimos 10 torneos"),
        ("titulos10", "lv", "j) fase", "si", "títulos ganados en los últimos 10 torneos"),
        # ---- k) mercado --------------------------------------------------------------------------------
        ("mercado_p_l", "", "k) mercado", "mercado", "probabilidad implícita de victoria local al CIERRE, sin margen (normalización proporcional). El cierre se conoce al silbatazo, no al corte del bloque"),
        ("mercado_p_e", "", "k) mercado", "mercado", "probabilidad implícita de empate al cierre, sin margen"),
        ("mercado_p_v", "", "k) mercado", "mercado", "probabilidad implícita de victoria visitante al cierre, sin margen"),
        ("mercado_margen", "", "k) mercado", "mercado", "margen del 1X2 de cierre (suma de inversos - 1)"),
        ("mercado_abre_p_l", "", "k) mercado", "mercado", "probabilidad implícita local con momios de APERTURA, sin margen"),
        ("mercado_abre_p_e", "", "k) mercado", "mercado", "empate con momios de apertura"),
        ("mercado_abre_p_v", "", "k) mercado", "mercado", "visitante con momios de apertura"),
        ("mercado_linea", "", "k) mercado", "mercado", "línea de goles totales"),
        ("mercado_p_over", "", "k) mercado", "mercado", "probabilidad implícita del 'más de' al cierre, sin margen"),
        ("mercado_abre_p_over", "", "k) mercado", "mercado", "probabilidad implícita del 'más de' en la apertura"),
        ("mercado_dudoso", "", "k) mercado", "mercado", "1 si los momios parecen capturados EN VIVO (misma regla que datos.momios_en_vivo); en ese caso las demás mercado_* quedan vacías"),
        # ---- l) otros ----------------------------------------------------------------------------------
        ("n_prev", "lv", "l) otros", "si", "partidos previos del equipo en la base (desde 2001)"),
        ("poca_historia", "lv", "l) otros", "si", "1 si tiene menos de 34 partidos previos"),
        ("recien_ascendido", "lv", "l) otros", "si", "1 si no jugó alguno de los dos torneos anteriores (ascendido o franquicia nueva)"),
        ("arb_n", "", "l) otros", "si*", "partidos previos del árbitro en la base (vacío si aún no hay árbitro designado)"),
        ("arb_tarjetas", "", "l) otros", "si*", f"tarjetas (amarillas + rojas) por partido del árbitro, encogidas a la media de la liga con K={K_ARBITRO:g}"),
        ("arb_penales", "", "l) otros", "si*", f"penales marcados por partido del árbitro, encogidos a la media de la liga con K={K_ARBITRO:g}"),
        ("asistencia5_l", "", "l) otros", "si", "asistencia media de los últimos 5 partidos de local con dato (> 0; mínimo 3)"),
    ]
)

_IDENT = ["id", "fecha_utc", "corte_utc", "torneo", "periodo", "fase", "estado", "local", "visitante"]


def catalogo() -> pd.DataFrame:
    """Tabla de variables: una fila por columna con grupo, disponibilidad y definición."""
    filas = []
    for base, lados, grupo, disp, defin in CATALOGO:
        if lados == "":
            nombres = [(base, "partido")]
        elif lados in ("l", "v"):
            nombres = [(f"{base}_{lados}", "local" if lados == "l" else "visitante")]
        else:
            nombres = [(f"{base}_l", "local"), (f"{base}_v", "visitante")]
            if lados == "lvd":
                nombres.append((f"{base}_dif", "local - visitante"))
        for nombre, lado in nombres:
            filas.append({"variable": nombre, "base": base, "lado": lado, "grupo": grupo, "disponible": disp,
                          "definicion": defin})
    return pd.DataFrame(filas)


def columnas(df: pd.DataFrame | None = None, disponibles: bool = True, mercado: bool = False) -> list[str]:
    """
    Nombres de las variables. Con disponibles=True quita las "_real" (no existen al pronosticar);
    con mercado=False quita las "mercado_*" (no existen para rondas futuras).
    """
    cat = catalogo()
    if disponibles:
        cat = cat[cat["disponible"] != "no"]
    if not mercado:
        cat = cat[cat["disponible"] != "mercado"]
    cols = list(cat["variable"])
    return cols if df is None else [c for c in cols if c in df.columns]


# ==================================================================================================
# Lectura y preparación de insumos
# ==================================================================================================
def leer_partidos(ruta: str | Path | None = None) -> pd.DataFrame:
    """partidos.csv como texto (los vacíos quedan como cadena vacía)."""
    return pd.read_csv(ruta or RUTA_PARTIDOS, dtype=str, keep_default_na=False, encoding="utf-8")


def leer_tarjetas(ruta: str | Path | None = None) -> pd.DataFrame:
    return pd.read_csv(ruta or RUTA_TARJETAS, dtype=str, keep_default_na=False, encoding="utf-8",
                       usecols=["partido_id", "equipo", "jugador_id", "tipo"])


def leer_alineaciones(ruta: str | Path | None = None) -> pd.DataFrame:
    return pd.read_csv(ruta or RUTA_ALINEACIONES, dtype=str, keep_default_na=False, encoding="utf-8",
                       usecols=["partido_id", "equipo", "jugador_id", "titular"])


def leer_sedes(ruta: str | Path | None = None) -> pd.DataFrame:
    return pd.read_csv(ruta or RUTA_SEDES, dtype=str, keep_default_na=False, encoding="utf-8")


def _txt(s: pd.Series) -> pd.Series:
    """Columna a texto: NaN -> '', enteros guardados como flotante -> sin decimales."""
    if pd.api.types.is_numeric_dtype(s):
        return s.map(lambda x: "" if x != x else (str(int(x)) if float(x).is_integer() else str(x)))
    return s.map(lambda x: "" if x is None or x != x else str(x))


def _a_epoca(valor) -> int:
    """Instante (texto ISO, Timestamp o segundos) a segundos UTC desde 1970."""
    if isinstance(valor, (int, np.integer)):
        return int(valor)
    ts = pd.Timestamp(valor)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return int((ts - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1))


def _preparar(partidos: pd.DataFrame, hasta, corte: str) -> pd.DataFrame:
    """
    Normaliza la tabla de partidos: tipos, instantes en segundos UTC, hora local, corte de información
    de cada partido (`_corte`) e instante en que su resultado se da por conocido (`_tinfo`).
    Con `hasta`, los partidos que empiezan en ese instante o después se tratan como PROGRAMADOS.
    """
    if corte not in ("partido", "bloque", "dia"):
        raise ValueError("corte debe ser 'partido', 'bloque' o 'dia'")
    df = pd.DataFrame(index=partidos.index)
    for c in _COLS_TXT:
        df[c] = _txt(partidos[c]) if c in partidos.columns else ""
    for c in _COLS_NUM:
        if c in partidos.columns:
            col = partidos[c]
            if not pd.api.types.is_numeric_dtype(col):
                col = pd.to_numeric(col.astype(str).where(col.astype(str) != "", None), errors="coerce")
            df[c] = col.astype("float64")
        else:
            df[c] = np.nan
    f = pd.to_datetime(partidos["fecha_utc"], utc=True)
    df["fecha_utc"] = f
    epoca = pd.Timestamp("1970-01-01", tz="UTC")
    df["_t"] = ((f - epoca) // pd.Timedelta(seconds=1)).astype("int64")

    df["estado"] = df["estado"].replace({"en_juego": "programado"})
    if hasta is not None:
        tope = _a_epoca(hasta)
        df.loc[(df["_t"] >= tope) & (df["estado"] == "jugado"), "estado"] = "programado"
    df = df[df["estado"].isin(["jugado", "programado"])].copy()
    sin_marcador = (df["estado"] == "jugado") & (df["gl"].isna() | df["gv"].isna())
    df.loc[sin_marcador, "estado"] = "programado"       # defensa: jugado sin marcador no entra al historial

    local = pd.DatetimeIndex(df["fecha_utc"]).tz_convert(ZONA)
    ingenuo = local.tz_localize(None)
    df["_hora"] = np.asarray(ingenuo.hour + ingenuo.minute / 60.0, dtype="float64")
    df["_ds"] = np.asarray(ingenuo.dayofweek, dtype="int64")
    df["_mes"] = np.asarray(ingenuo.month, dtype="int64")
    dia = ingenuo.normalize()

    def a_seg(ix):
        u = ix.tz_localize(ZONA, ambiguous=True, nonexistent="shift_forward").tz_convert("UTC")
        return np.asarray((u - epoca) // pd.Timedelta(seconds=1), dtype="int64")

    if corte == "partido":
        df["_corte"] = df["_t"]
        df["_tinfo"] = df["_t"] + RETRASO_INFO_S
    else:
        if corte == "bloque":
            atras = np.where(df["_ds"].to_numpy() <= 3, df["_ds"].to_numpy(), df["_ds"].to_numpy() - 4)
            inicio = dia - pd.to_timedelta(atras, unit="D")
        else:
            inicio = dia
        df["_corte"] = a_seg(inicio)
        df["_tinfo"] = df["_t"] + 1                      # conocido si EMPEZÓ antes del corte
    df["_ot"] = df["torneo"].map(orden_torneo).astype("int64")
    df["_idn"] = pd.to_numeric(df["id"], errors="coerce").fillna(-1).astype("int64")
    return df.sort_values(["_t", "_idn"], kind="mergesort").reset_index(drop=True)


def _preparar_aux(tab: pd.DataFrame, tarjetas: pd.DataFrame, alineaciones: pd.DataFrame, hasta):
    """
    Diccionarios por (partido, equipo): once titular (11 ids distintos o nada), lista completa de
    convocados y tarjetas [(jugador_id, tipo)]. Con `hasta` se descartan los partidos no jugados.
    """
    ids_ok = set(tab["id"]) if hasta is None else set(tab.loc[tab["estado"] == "jugado", "id"])
    tit_d, todos_d = {}, {}
    for pid, eq, jug, tit in zip(alineaciones["partido_id"].tolist(), alineaciones["equipo"].tolist(),
                                 alineaciones["jugador_id"].tolist(), alineaciones["titular"].tolist()):
        if jug and pid in ids_ok:
            llave = (pid, eq)
            todos_d.setdefault(llave, []).append(jug)
            if tit == "1":
                tit_d.setdefault(llave, []).append(jug)
    onces, conv = {}, {}
    for llave, lista in tit_d.items():
        s = frozenset(lista)
        if len(lista) == 11 and len(s) == 11:            # once válido: exactamente 11 titulares distintos
            onces[llave] = s
            todos = frozenset(todos_d[llave])
            if len(todos) >= 14:                         # la lista incluye banca
                conv[llave] = todos
    cartas = {}
    for pid, eq, jug, tipo in zip(tarjetas["partido_id"].tolist(), tarjetas["equipo"].tolist(),
                                  tarjetas["jugador_id"].tolist(), tarjetas["tipo"].tolist()):
        if pid in ids_ok:
            cartas.setdefault((pid, eq), []).append((jug, tipo))
    return onces, conv, cartas


def _firmas(tab: pd.DataFrame, tarjetas: pd.DataFrame, alineaciones: pd.DataFrame) -> pd.Series:
    """Firma por partido de todo lo que entra al cálculo (fila del partido + alineaciones + tarjetas)."""
    usadas = _COLS_TXT + _COLS_NUM + ["_t"]
    h = pd.util.hash_pandas_object(tab[usadas], index=False).to_numpy(dtype="uint64")
    firma = pd.Series(h, index=tab["id"].to_numpy())
    for extra, cols, mult in ((alineaciones, ["partido_id", "equipo", "jugador_id", "titular"], 3),
                              (tarjetas, ["partido_id", "equipo", "jugador_id", "tipo"], 7)):
        if len(extra):
            hx = pd.util.hash_pandas_object(extra[cols], index=False).to_numpy(dtype="uint64")
            suma = pd.Series(hx).groupby(extra["partido_id"].to_numpy()).sum()       # uint64 con desborde
            mapa = dict(zip(suma.index, suma.to_numpy()))
            add = np.array([mapa.get(i, 0) for i in firma.index], dtype="uint64")
            with np.errstate(over="ignore"):
                firma = pd.Series(firma.to_numpy(dtype="uint64") + add * np.uint64(mult), index=firma.index)
    return firma.astype(str)


def _firma_global(corte: str, sedes: pd.DataFrame) -> str:
    """Firma de lo que afecta a TODAS las filas: versión, corte, sedes, formato del torneo en curso."""
    cfg = _config_torneo()
    partes = [VERSION, corte, DESDE, repr((SEDE_CORREGIDA_PARTIDO, SEDE_CORREGIDA_LOCAL, SEDE_NO_ANTES, GANADOR_MANUAL)), str(int(pd.util.hash_pandas_object(sedes, index=False).to_numpy(dtype="uint64").sum())),
              json.dumps({k: cfg.get(k) for k in ("torneo", "jornadas", "clasifican_directo", "play_in")},
                         sort_keys=True, ensure_ascii=False, default=str)]
    return hashlib.md5("|".join(partes).encode("utf-8")).hexdigest()


# ==================================================================================================
# Estado: todo lo que se sabe en un instante dado
# ==================================================================================================
class Reg:
    """Un partido ya conocido, visto por uno de los dos equipos."""
    __slots__ = ("t", "id", "ot", "torneo", "fase", "loc", "rival", "gf", "gc", "pts", "sede", "alt", "sint",
                 "st", "xi", "conv", "n_rojas", "susp", "asis")

    def __init__(self, t, pid, ot, torneo, fase, loc, rival, gf, gc, sede, alt, sint, st, xi, conv, n_rojas,
                 susp, asis):
        self.t, self.id, self.ot, self.torneo, self.fase, self.loc, self.rival = t, pid, ot, torneo, fase, loc, rival
        self.gf, self.gc = gf, gc
        self.pts = 3 if gf > gc else (1 if gf == gc else 0)
        self.sede, self.alt, self.sint = sede, alt, sint
        self.st, self.xi, self.conv, self.n_rojas, self.susp, self.asis = st, xi, conv, n_rojas, susp, asis


class Hist:
    """Historial de un equipo: todos sus partidos (p), los de local (L) y los de visita (V)."""
    __slots__ = ("p", "L", "V", "cache_xi")

    def __init__(self):
        self.p, self.L, self.V = [], [], []
        self.cache_xi = None


_VACIO = Hist()                 # historial vacío compartido; nunca se modifica
_PESOS_EXP = [0.5 ** (k / VIDA_MEDIA_FORMA) for k in range(MAX_FORMA_EXP)]


def _haversine(lat1, lon1, lat2, lon2) -> float:
    """Distancia en km sobre la esfera (radio 6,371 km)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


class Estado:
    """
    Estado del mundo en un instante: historiales por equipo, tabla, series de liguilla, enfrentamientos,
    árbitros, medias de liga y parámetros que se reestiman al cambiar de torneo. `ingerir` es lo único
    que lo modifica; `variables` sólo lee (salvo memorias internas que dependen del propio estado).
    """

    def __init__(self, sedes: pd.DataFrame, calendario: dict, onces: dict, conv: dict, cartas: dict):
        self.onces, self.conv, self.cartas = onces, conv, cartas
        self.sede_no_antes = {k: _a_epoca(v) for k, v in SEDE_NO_ANTES.items()}
        self.cal = calendario                            # equipo -> [(t, ot, tinfo)] ordenado
        # sedes
        self.id_sede = {}
        self.sede_info = {}                              # sede -> (lat, lon, alt, sint_desde, sint_hasta)
        for r in sedes.to_dict("records"):
            s = r.get("sede", "")
            if not s:
                continue
            self.id_sede[str(r["estadio_id"])] = s
            if s not in self.sede_info:
                try:
                    lat, lon = float(r["lat"]), float(r["lon"])
                except (TypeError, ValueError):
                    lat = lon = NAN
                try:
                    alt = float(r["altitud_m"])
                except (TypeError, ValueError):
                    alt = NAN
                sd = _a_epoca(r["sintetico_desde"]) if r.get("sintetico_desde") else None
                sh = _a_epoca(r["sintetico_hasta"]) + DIA if r.get("sintetico_hasta") else None
                self.sede_info[s] = (lat, lon, alt, sd, sh)
        # historiales
        self.eq: dict[str, Hist] = {}
        self.elo: dict[str, float] = {}
        self.ot_min = None
        self.ot_max = -1
        self.tabla: dict[str, dict] = {}                 # torneo -> equipo -> [pj, pts, gf, gc]
        self.tabla_ver: dict[str, int] = {}
        self._cache_pos: dict = {}
        self.jugo_torneo: dict[int, set] = {}            # ot -> equipos con partidos
        self.h2h: dict[tuple, list] = {}                 # (a, b) ordenado -> [(t, ot, fase, local, gl, gv, sede)]
        self.series: dict[tuple, list] = {}              # (torneo, fase, a, b) -> piernas conocidas
        self.series_cerradas: set = set()
        self.series_eq: dict[str, list] = {}             # equipo -> [(ot, fase, ganó)]
        self.series_h2h: dict[tuple, list] = {}          # (a, b) -> [(ot, fase, ganador)]
        self.amarillas: dict[tuple, dict] = {}           # (equipo, torneo, 'R'|'L') -> jugador -> amarillas
        self.arb: dict[str, list] = {}                   # árbitro -> [n, n_tarj, tarj, n_pen, pen]
        # medias de liga con sumas corridas (enteros: exactas y deterministas)
        self.liga = deque()                              # (gl, gv) de fase regular
        self.liga_s = [0, 0, 0, 0]                       # gl, gv, victorias locales, empates
        self.liga_g = deque()
        self.liga_g_s = 0
        self.liga_tar = deque()
        self.liga_tar_s = 0
        self.liga_pen = deque()
        self.liga_pen_s = 0
        # parámetros que se reestiman al cambiar de torneo (sólo con el pasado)
        self.xg_obs = deque(maxlen=VENTANA_XG)           # (tiros fuera de puerta, tiros a puerta, goles)
        self.xg_coef = None
        self.k_sede = math.inf
        self.diag = {"k_sede": [], "xg": []}             # bitácora de esas estimaciones

    # ---------------------------------------------------------------------------------------------
    # utilidades de sede
    # ---------------------------------------------------------------------------------------------
    def _habitual(self, h: Hist, t: int):
        """
        Sede habitual del equipo en el instante t: la más frecuente en sus últimos 6 partidos de local
        dentro de los 365 días previos (empate -> la más reciente); None si no jugó de local en ese lapso.
        """
        cuenta, orden = {}, []
        limite = t - 365 * DIA
        for r in reversed(h.L[-VENTANA_HABITUAL:]):
            if r.t < limite:
                break
            if r.sede is not None:
                if r.sede not in cuenta:
                    orden.append(r.sede)
                cuenta[r.sede] = cuenta.get(r.sede, 0) + 1
        hab = None
        for s in orden:                                  # de más reciente a más antigua
            if hab is None or cuenta[s] > cuenta[hab]:
                hab = s
        return hab

    def _sede_partido(self, pid: str, estadio_id: str, local: str, h_local: Hist, t: int):
        """(sede, imputada): la del id de ESPN (con correcciones conocidas) o, si no hay, la habitual del local."""
        s = SEDE_CORREGIDA_PARTIDO.get(pid) or SEDE_CORREGIDA_LOCAL.get((estadio_id, local)) or self.id_sede.get(estadio_id)
        if s and not (s in self.sede_no_antes and t < self.sede_no_antes[s]):
            return s, 0
        return self._habitual(h_local, t), 1

    def _alt_sint(self, sede, t):
        """(altitud, sintético 0/1) de la sede en la fecha t; None si no se sabe."""
        if sede is None:
            return None, None
        lat, lon, alt, sd, sh = self.sede_info[sede]
        sint = 1 if (sd is not None and t >= sd and (sh is None or t < sh)) else 0
        return (alt if alt == alt else None), sint

    # ---------------------------------------------------------------------------------------------
    # parámetros lentos (se refrescan al conocer el primer partido de un torneo nuevo)
    # ---------------------------------------------------------------------------------------------
    def _refrescar(self, torneo: str):
        """Reestima, con lo conocido hasta ahora, la regresión de goles esperados y la K de las sedes."""
        # goles esperados: goles ~ b0 + b1 * tiros fuera de puerta + b2 * tiros a puerta
        if len(self.xg_obs) >= 300:
            a = np.array(self.xg_obs, dtype="float64")
            x = np.column_stack([np.ones(len(a)), a[:, 0], a[:, 1]])
            coef, *_ = np.linalg.lstsq(x, a[:, 2], rcond=None)
            self.xg_coef = (float(coef[0]), float(coef[1]), float(coef[2]))
            self.diag["xg"].append((torneo, len(a)) + self.xg_coef)
        # credibilidad de Bühlmann-Straub para la ventaja de local por (equipo, sede)
        unidades, ss, gl_ = [], 0.0, 0
        for nombre in sorted(self.eq):
            h = self.eq[nombre]
            por_sede = {}
            for r in h.L:
                if r.sede is not None:
                    por_sede.setdefault(r.sede, []).append(r.gf - r.gc)
            tiempos = {}
            for r in h.L:
                if r.sede is not None:
                    a_, b_ = tiempos.get(r.sede, (r.t, r.t))
                    tiempos[r.sede] = (min(a_, r.t), max(b_, r.t))
            for sede in sorted(por_sede):
                xc = por_sede[sede]
                t0, t1 = tiempos[sede]
                xf = [r.gf - r.gc for r in h.V if t0 <= r.t <= t1]
                if len(xc) < 17 or len(xf) < 17:
                    continue
                mc, mf = sum(xc) / len(xc), sum(xf) / len(xf)
                ss += sum((v - mc) ** 2 for v in xc) + sum((v - mf) ** 2 for v in xf)
                gl_ += len(xc) + len(xf) - 2
                unidades.append((mc - mf, len(xc) * len(xf) / (len(xc) + len(xf))))
        k = math.inf
        sigma2 = tau2 = NAN
        if len(unidades) >= 10 and gl_ > 0:
            sigma2 = ss / gl_
            m_tot = sum(m for _, m in unidades)
            media = sum(d * m for d, m in unidades) / m_tot
            num = sum(m * (d - media) ** 2 for d, m in unidades) - (len(unidades) - 1) * sigma2
            den = m_tot - sum(m * m for _, m in unidades) / m_tot
            tau2 = num / den if den > 0 else NAN
            if tau2 == tau2 and tau2 > 0:
                k = sigma2 / tau2
        self.k_sede = k
        self.diag["k_sede"].append((torneo, len(unidades), sigma2, tau2, k))

    # ---------------------------------------------------------------------------------------------
    # ingestión de un partido jugado
    # ---------------------------------------------------------------------------------------------
    def ingerir(self, m: dict):
        """Incorpora al estado un partido jugado (se llama en orden de `_tinfo`, id)."""
        L, V = m["local"], m["visitante"]
        gl, gv = int(m["gl"]), int(m["gv"])
        t, tor, ot, fase, pid = m["_t"], m["torneo"], m["_ot"], m["fase"], m["id"]
        if ot > self.ot_max:
            self._refrescar(tor)
            self.ot_max = ot
        if self.ot_min is None:
            self.ot_min = ot
        hL = self.eq.get(L)
        if hL is None:
            hL = self.eq[L] = Hist()
        hV = self.eq.get(V)
        if hV is None:
            hV = self.eq[V] = Hist()

        sede, _ = self._sede_partido(pid, m["estadio_id"], L, hL, t)
        alt, sint = self._alt_sint(sede, t)

        # estadísticas del partido
        stL = stV = None
        if m["tiene_stats"] == 1 and m["tiros_l"] == m["tiros_l"] and m["tiros_v"] == m["tiros_v"]:
            tl, tv = m["tiros_l"], m["tiros_v"]
            pl, pv = m["tiros_puerta_l"], m["tiros_puerta_v"]
            stL = (tl, tv, pl, pv, m["corners_l"], m["corners_v"], m["posesion_l"], m["faltas_l"], m["faltas_v"],
                   m["amarillas_l"], gl, gv)
            stV = (tv, tl, pv, pl, m["corners_v"], m["corners_l"], m["posesion_v"], m["faltas_v"], m["faltas_l"],
                   m["amarillas_v"], gv, gl)
            if pl == pl and pv == pv:
                self.xg_obs.append((max(tl - pl, 0.0), pl, float(gl)))
                self.xg_obs.append((max(tv - pv, 0.0), pv, float(gv)))

        # tarjetas -> expulsados y suspendidos para el siguiente partido
        alcance = "R" if fase == "regular" else "L"
        info_t = []
        for eq_ in (L, V):
            ev = self.cartas.get((pid, eq_), ())
            dobles = {j for j, tipo in ev if tipo == "segunda_amarilla"}
            n_rojas, susp = 0, set()
            cont = None
            for j, tipo in ev:
                if tipo == "amarilla":
                    if j and j not in dobles:
                        if cont is None:
                            cont = self.amarillas.setdefault((eq_, tor, alcance), {})
                        c = cont.get(j, 0) + 1
                        cont[j] = c
                        if c % 5 == 0 and ot >= OT_AMARILLAS_SUSPENDEN:
                            susp.add(j)
                else:                                    # roja o segunda amarilla
                    n_rojas += 1
                    if j:
                        susp.add(j)
            info_t.append((n_rojas, frozenset(susp)))

        asis = m["asistencia"]
        asis = asis if (asis == asis and asis > 0) else None
        rl = Reg(t, pid, ot, tor, fase, 1, V, gl, gv, sede, alt, sint, stL, self.onces.get((pid, L)),
                 self.conv.get((pid, L)), info_t[0][0], info_t[0][1], asis)
        rv = Reg(t, pid, ot, tor, fase, 0, L, gv, gl, sede, alt, sint, stV, self.onces.get((pid, V)),
                 self.conv.get((pid, V)), info_t[1][0], info_t[1][1], None)

        # Elo (con las fuerzas previas)
        ra, rb = self._elo(L, ot), self._elo(V, ot)
        esperado = 1.0 / (1.0 + 10.0 ** (-(ra + ELO_LOCAL - rb) / 400.0))
        real = 1.0 if gl > gv else (0.5 if gl == gv else 0.0)
        g = abs(gl - gv)
        mult = 1.0 if g <= 1 else (1.5 if g == 2 else (11.0 + g) / 8.0)
        delta = K_ELO * mult * (real - esperado)
        self.elo[L], self.elo[V] = ra + delta, rb - delta

        hL.p.append(rl)
        hL.L.append(rl)
        hV.p.append(rv)
        hV.V.append(rv)
        self.jugo_torneo.setdefault(ot, set()).update((L, V))

        if fase == "regular":
            tb = self.tabla.setdefault(tor, {})
            for eq_, gf, gc in ((L, gl, gv), (V, gv, gl)):
                f = tb.get(eq_)
                if f is None:
                    f = tb[eq_] = [0, 0, 0, 0]
                f[0] += 1
                f[1] += 3 if gf > gc else (1 if gf == gc else 0)
                f[2] += gf
                f[3] += gc
            self.tabla_ver[tor] = self.tabla_ver.get(tor, 0) + 1
            # medias de liga
            self.liga.append((gl, gv))
            s = self.liga_s
            s[0] += gl
            s[1] += gv
            s[2] += 1 if gl > gv else 0
            s[3] += 1 if gl == gv else 0
            if len(self.liga) > VENTANA_LIGA:
                a, b = self.liga.popleft()
                s[0] -= a
                s[1] -= b
                s[2] -= 1 if a > b else 0
                s[3] -= 1 if a == b else 0
            self.liga_g.append(gl + gv)
            self.liga_g_s += gl + gv
            if len(self.liga_g) > VENTANA_LIGA_GOLES:
                self.liga_g_s -= self.liga_g.popleft()
        else:
            self._ingerir_serie(m, L, V, gl, gv, tor, ot, fase)

        llave = (L, V) if L < V else (V, L)
        self.h2h.setdefault(llave, []).append((t, ot, fase, L, gl, gv, sede))

        # tarjetas y penales del partido (para la media de la liga y del árbitro)
        tar = pen = None
        if m["tiene_stats"] == 1 and m["amarillas_l"] == m["amarillas_l"] and m["amarillas_v"] == m["amarillas_v"]:
            rj = (m["rojas_l"] if m["rojas_l"] == m["rojas_l"] else 0) + (m["rojas_v"] if m["rojas_v"] == m["rojas_v"] else 0)
            tar = int(m["amarillas_l"] + m["amarillas_v"] + rj)
            self.liga_tar.append(tar)
            self.liga_tar_s += tar
            if len(self.liga_tar) > VENTANA_LIGA:
                self.liga_tar_s -= self.liga_tar.popleft()
        if m["penales_tirados_l"] == m["penales_tirados_l"] and m["penales_tirados_v"] == m["penales_tirados_v"]:
            pen = int(m["penales_tirados_l"] + m["penales_tirados_v"])
            self.liga_pen.append(pen)
            self.liga_pen_s += pen
            if len(self.liga_pen) > VENTANA_LIGA:
                self.liga_pen_s -= self.liga_pen.popleft()
        arb = m["arbitro"].strip()
        if arb:
            a = self.arb.get(arb)
            if a is None:
                a = self.arb[arb] = [0, 0, 0, 0, 0]
            a[0] += 1
            if tar is not None:
                a[1] += 1
                a[2] += tar
            if pen is not None:
                a[3] += 1
                a[4] += pen

    def _elo(self, equipo: str, ot: int) -> float:
        """Elo vigente; un equipo sin historia entra en 1500 (primer torneo de la base) o 1450."""
        r = self.elo.get(equipo)
        if r is None:
            return ELO_INICIAL if (self.ot_min is None or ot == self.ot_min) else ELO_NUEVO
        return r

    def _ingerir_serie(self, m, L, V, gl, gv, tor, ot, fase):
        """Registra una pierna de liguilla y, si la serie queda completa, decide al ganador por regla."""
        a, b = (L, V) if L < V else (V, L)
        llave = (tor, fase, a, b)
        piernas = self.series.setdefault(llave, [])
        pierna = m["pierna"]
        piernas.append({"pierna": pierna, "local": L, "visitante": V, "gl": gl, "gv": gv,
                        "gl_et": m["gl_et"], "gv_et": m["gv_et"], "pen_l": m["pen_l"], "pen_v": m["pen_v"]})
        completa = (pierna != pierna) or pierna == 2
        if not completa or llave in self.series_cerradas:
            return
        self.series_cerradas.add(llave)
        gan = self._ganador_serie(piernas, tor, fase)
        for eq_ in (a, b):
            self.series_eq.setdefault(eq_, []).append((ot, fase, None if gan is None else gan == eq_))
        self.series_h2h.setdefault((a, b), []).append((ot, fase, gan))

    def _ganador_serie(self, piernas, tor, fase):
        """
        Ganador de una serie por regla: global a 90 min; en la final, tiempos extra y penales; en las
        demás, penales si los hubo, gol de visitante si regía, y al final la mejor posición en la tabla.
        """
        ult = piernas[-1]
        a, b = ult["local"], ult["visitante"]            # a = local de la última pierna
        ga = gb = va = vb = 0
        for p in piernas:
            if p["local"] == a:
                ga += p["gl"]
                gb += p["gv"]
                vb += p["gv"]
            else:
                ga += p["gv"]
                gb += p["gl"]
                va += p["gv"]
        if ga != gb:
            return a if ga > gb else b
        if ult["gl_et"] == ult["gl_et"] and ult["gv_et"] == ult["gv_et"]:
            ea = ga - ult["gl"] + ult["gl_et"]            # global con el marcador de 120 min de la última pierna
            eb = gb - ult["gv"] + ult["gv_et"]
            if ea != eb:
                return a if ea > eb else b
        if ult["pen_l"] == ult["pen_l"] and ult["pen_v"] == ult["pen_v"] and ult["pen_l"] != ult["pen_v"]:
            return a if ult["pen_l"] > ult["pen_v"] else b
        manual = GANADOR_MANUAL.get((tor, fase, min(a, b), max(a, b)))
        if manual is not None:
            return manual
        if fase == "final":
            return None
        if formato_torneo(tor)["gol_visitante"] and len(piernas) == 2 and va != vb:
            return a if va > vb else b
        res = self._posiciones(tor)
        if res is None:
            return None
        pa, pb = res[1].get(a), res[1].get(b)
        if pa is None or pb is None or pa == pb:
            return None
        return a if pa < pb else b

    # ---------------------------------------------------------------------------------------------
    # lecturas del estado
    # ---------------------------------------------------------------------------------------------
    def _posiciones(self, tor: str):
        """(orden, posición por equipo) de la tabla regular del torneo; None si aún no hay partidos."""
        tb = self.tabla.get(tor)
        if not tb:
            return None
        ver = self.tabla_ver[tor]
        c = self._cache_pos.get(tor)
        if c is not None and c[0] == ver:
            return c[1]
        orden = sorted(tb, key=lambda e: (-tb[e][1], -(tb[e][2] - tb[e][3]), -tb[e][2], e))
        res = (orden, {e: i + 1 for i, e in enumerate(orden)})
        self._cache_pos[tor] = (ver, res)
        return res

    def _medias_liga(self):
        """(goles por partido, ventaja de local, p local, p empate, puntos esperados local y visita)."""
        n = len(self.liga)
        if n < 100:
            return NAN, NAN, NAN, NAN, NAN, NAN
        s = self.liga_s
        pl, pe = s[2] / n, s[3] / n
        goles = self.liga_g_s / len(self.liga_g)
        return goles, (s[0] - s[1]) / n, pl, pe, 3 * pl + pe, 3 * (1 - pl - pe) + pe

    def _plantel(self, h: Hist):
        """(titularidades por jugador, partidos con once válido, onces del más reciente al más antiguo)."""
        ver = len(h.p)
        if h.cache_xi is not None and h.cache_xi[0] == ver:
            return h.cache_xi[1]
        cuenta, onces = {}, []
        for r in reversed(h.p[-15:]):
            if r.xi is not None:
                onces.append(r.xi)
                for j in r.xi:
                    cuenta[j] = cuenta.get(j, 0) + 1
                if len(onces) == 10:
                    break
        res = (cuenta, len(onces), onces)
        h.cache_xi = (ver, res)
        return res

    # ---------------------------------------------------------------------------------------------
    # variables de un partido (sólo lectura)
    # ---------------------------------------------------------------------------------------------
    def variables(self, M: dict) -> dict:
        """Todas las variables del partido M con el estado actual (su corte)."""
        v = {}
        L, V = M["local"], M["visitante"]
        hL, hV = self.eq.get(L, _VACIO), self.eq.get(V, _VACIO)
        t, tor, ot, fase = M["_t"], M["torneo"], M["_ot"], M["fase"]
        goles, vl, p_loc, p_emp, pts_casa, pts_fuera = self._medias_liga()

        # 0) fuerza base
        v["elo_l"], v["elo_v"] = self._elo(L, ot), self._elo(V, ot)
        v["liga_goles"], v["liga_vl"], v["liga_p_local"], v["liga_p_empate"] = goles, vl, p_loc, p_emp

        self._v_calendario(v, M, L, V)
        for s, h, cond in (("l", hL, hL.L), ("v", hV, hV.V)):
            self._v_forma(v, s, h, cond, tor)
            self._v_rachas(v, s, h, cond)
            self._v_juego(v, s, h)
            self._v_plantel(v, s, h, M, L if s == "l" else V, v[f"pendientes_previos_{s}"] > 0)
            self._v_otros_equipo(v, s, h, L if s == "l" else V, ot)
        self._v_tabla(v, M, L, V)
        self._v_sede(v, M, hL, hV, L, V, vl)
        self._v_h2h(v, M, L, V, vl, pts_casa, pts_fuera)
        self._v_fase(v, M, L, V)
        self._v_mercado(v, M)
        self._v_arbitro(v, M)

        # asistencia reciente del local
        asis = [r.asis for r in reversed(hL.L[-12:]) if r.asis is not None][:5]
        v["asistencia5_l"] = sum(asis) / len(asis) if len(asis) >= 3 else NAN

        for base in _BASES_DIF:
            v[base + "_dif"] = v[base + "_l"] - v[base + "_v"]
        a, b = v["descanso_l"], v["descanso_v"]
        v["descanso_dif"] = (min(a, TOPE_DIF_DESCANSO) - min(b, TOPE_DIF_DESCANSO)) if (a == a and b == b) else NAN
        return v

    # ---- a) forma -----------------------------------------------------------------------------------
    @staticmethod
    def _resumen(v, base, s, regs, minimo):
        n = len(regs)
        if n < minimo:
            ppp = gf = gc = dg = NAN
        else:
            pts = a = b = 0
            for r in regs:
                pts += r.pts
                a += r.gf
                b += r.gc
            ppp, gf, gc, dg = pts / n, a / n, b / n, (a - b) / n
        v[f"{base}_ppp_{s}"], v[f"{base}_gf_{s}"], v[f"{base}_gc_{s}"], v[f"{base}_dg_{s}"] = ppp, gf, gc, dg

    @staticmethod
    def _resumen_exp(v, base, s, regs):
        n = len(regs)
        if n < 3:
            ppp = gf = gc = dg = NAN
        else:
            w = pts = a = b = 0.0
            for k in range(n):                           # k = 0 es el más reciente
                r = regs[n - 1 - k]
                p = _PESOS_EXP[k]
                w += p
                pts += p * r.pts
                a += p * r.gf
                b += p * r.gc
            ppp, gf, gc, dg = pts / w, a / w, b / w, (a - b) / w
        v[f"{base}_ppp_{s}"], v[f"{base}_gf_{s}"], v[f"{base}_gc_{s}"], v[f"{base}_dg_{s}"] = ppp, gf, gc, dg

    def _v_forma(self, v, s, h, cond, tor):
        p = h.p
        for n, mn in ((5, 3), (10, 5)):
            self._resumen(v, f"forma{n}", s, p[-n:], mn)
            self._resumen(v, f"forma{n}_cond", s, cond[-n:], mn)
        self._resumen_exp(v, "formaexp", s, p[-MAX_FORMA_EXP:])
        self._resumen_exp(v, "formaexp_cond", s, cond[-MAX_FORMA_EXP:])
        del_torneo = []
        for r in reversed(p):
            if r.torneo != tor:
                break
            del_torneo.append(r)
        v[f"torneo_pj_{s}"] = float(len(del_torneo))
        self._resumen(v, "torneo", s, del_torneo, 1)

    # ---- b) rachas ----------------------------------------------------------------------------------
    @staticmethod
    def _rachas(v, pref, s, regs):
        nombres = ("vict", "inv", "singanar", "derr", "anot", "sinanot", "cero")
        if not regs:
            for k in nombres:
                v[f"{pref}_{k}_{s}"] = NAN
            return
        cuenta = [0] * 7
        viva = [True] * 7
        for r in reversed(regs[-60:]):
            cond = (r.pts == 3, r.pts >= 1, r.pts < 3, r.pts == 0, r.gf > 0, r.gf == 0, r.gc == 0)
            alguna = False
            for i in range(7):
                if viva[i]:
                    if cond[i]:
                        cuenta[i] += 1
                        alguna = True
                    else:
                        viva[i] = False
            if not alguna:
                break
        for i, k in enumerate(nombres):
            v[f"{pref}_{k}_{s}"] = float(cuenta[i])

    def _v_rachas(self, v, s, h, cond):
        self._rachas(v, "racha", s, h.p)
        self._rachas(v, "racha_cond", s, cond)

    # ---- g) juego -------------------------------------------------------------------------------------
    def _v_juego(self, v, s, h):
        con = []
        for r in reversed(h.p[-20:]):
            if r.st is not None:
                con.append(r.st)
                if len(con) == 10:
                    break
        v[f"juego_n_{s}"] = float(len(con))
        coef = self.xg_coef

        def medias(regs, minimo):
            n = len(regs)
            if n < minimo:
                return None
            tf = tc = pf = pc = cf = cc = ff = fc = am = 0.0
            xf = xc = gf = gc = 0.0
            npos = 0
            pos = 0.0
            nx = 0
            for st in regs:
                tf += st[0]
                tc += st[1]
                if st[2] == st[2] and st[3] == st[3]:
                    pf += st[2]
                    pc += st[3]
                    if coef is not None:
                        nx += 1
                        xf += max(coef[0] + coef[1] * max(st[0] - st[2], 0.0) + coef[2] * st[2], 0.0)
                        xc += max(coef[0] + coef[1] * max(st[1] - st[3], 0.0) + coef[2] * st[3], 0.0)
                        gf += st[10]
                        gc += st[11]
                else:
                    pf = pc = NAN
                cf += st[4]
                cc += st[5]
                if st[6] == st[6]:
                    npos += 1
                    pos += st[6]
                ff += st[7]
                fc += st[8]
                am += st[9]
            d = {"tiros_f": tf / n, "tiros_c": tc / n, "tp_f": pf / n, "tp_c": pc / n, "corners_f": cf / n,
                 "corners_c": cc / n, "faltas_f": ff / n, "faltas_c": fc / n, "amarillas": am / n,
                 "posesion": pos / npos if npos >= 3 else NAN}
            if nx == n and nx > 0:
                d.update(xg_f=xf / n, xg_c=xc / n, suerte_f=(gf - xf) / n, suerte_c=(gc - xc) / n)
            else:
                d.update(xg_f=NAN, xg_c=NAN, suerte_f=NAN, suerte_c=NAN)
            return d

        m10 = medias(con, 5)
        m5 = medias(con[:5], 3)
        for k in ("tiros_f", "tiros_c", "tp_f", "tp_c", "corners_f", "corners_c", "faltas_f", "faltas_c",
                  "xg_f", "xg_c", "posesion", "amarillas", "suerte_f", "suerte_c"):
            v[f"juego10_{k}_{s}"] = m10[k] if m10 is not None else NAN
        v[f"juego10_xgdif_{s}"] = (m10["xg_f"] - m10["xg_c"]) if m10 is not None else NAN
        for k in ("tiros_f", "tiros_c", "tp_f", "tp_c", "xg_f", "xg_c"):
            v[f"juego5_{k}_{s}"] = m5[k] if m5 is not None else NAN

    # ---- h, i) disciplina, ausencias y alineación ------------------------------------------------------
    def _v_plantel(self, v, s, h, M, equipo, desfasado):
        """
        Disciplina, ausencias y alineación. `desfasado` = el partido anterior del equipo aún no se conoce en
        el corte (está programado o cae en el mismo bloque): las suspensiones no se pueden deducir y quedan
        vacías; lo demás se calcula con el último partido conocido.
        """
        cuenta, n, onces = self._plantel(h)
        prev = h.p[-1] if h.p else None
        reciente = prev is not None and (M["_t"] - prev.t) <= CADUCA_SUSPENSION_DIAS * DIA
        sin_previo = prev is None or desfasado
        if sin_previo:
            v[f"rojas_prev_{s}"] = v[f"susp_n_{s}"] = NAN
            susp = frozenset()
        else:
            susp = prev.susp if reciente else frozenset()
            v[f"rojas_prev_{s}"] = float(prev.n_rojas) if reciente else 0.0
            v[f"susp_n_{s}"] = float(len(susp))
        hay_plantel = n >= MIN_ONCES
        umbral = UMBRAL_HABITUAL * n
        habituales = {j for j, c in cuenta.items() if c >= umbral} if hay_plantel else set()
        if sin_previo:
            v[f"susp_imp_{s}"] = v[f"susp_titulares_{s}"] = NAN
        elif not susp:
            v[f"susp_imp_{s}"] = v[f"susp_titulares_{s}"] = 0.0
        elif hay_plantel:
            v[f"susp_imp_{s}"] = sum(cuenta.get(j, 0) for j in susp) / n
            v[f"susp_titulares_{s}"] = float(len(habituales & susp))
        else:
            v[f"susp_imp_{s}"] = v[f"susp_titulares_{s}"] = NAN
        # titulares habituales fuera de la lista del partido anterior
        if hay_plantel and prev is not None and prev.conv is not None and reciente:
            fuera = habituales - prev.conv
            v[f"aus_conv_n_{s}"] = float(len(fuera))
            v[f"aus_conv_imp_{s}"] = sum(cuenta[j] for j in fuera) / n
            v[f"aus_tit_previa_{s}"] = NAN if desfasado else float(len(fuera | (habituales & susp)))
        else:
            v[f"aus_conv_n_{s}"] = v[f"aus_conv_imp_{s}"] = v[f"aus_tit_previa_{s}"] = NAN
        # once previsto (disponible al pronosticar)
        previsto = None
        if hay_plantel and prev is not None and prev.xi is not None:
            previsto = prev.xi - susp
            v[f"once_previa_hab_{s}"] = sum(cuenta.get(j, 0) for j in previsto) / (11.0 * n)
        else:
            v[f"once_previa_hab_{s}"] = NAN
        v[f"once_previa_cambios_{s}"] = float(11 - len(onces[0] & onces[1])) if len(onces) >= 2 else NAN
        v[f"once_previa_rot5_{s}"] = float(len(frozenset().union(*onces[:5]))) if len(onces) >= 5 else NAN
        # once real (NO disponible al pronosticar)
        xi = self.onces.get((M["id"], equipo))
        if xi is not None and hay_plantel:
            v[f"once_real_hab_{s}"] = sum(cuenta.get(j, 0) for j in xi) / (11.0 * n)
            v[f"once_real_aus_{s}"] = float(len(habituales - xi))
        else:
            v[f"once_real_hab_{s}"] = v[f"once_real_aus_{s}"] = NAN
        v[f"once_real_cambios_{s}"] = float(11 - len(xi & onces[0])) if (xi is not None and onces) else NAN
        v[f"once_real_acierto_previa_{s}"] = len(xi & previsto) / 11.0 if (xi is not None and previsto is not None) else NAN

    # ---- l) otros (por equipo) ---------------------------------------------------------------------------
    def _v_otros_equipo(self, v, s, h, equipo, ot):
        n = len(h.p)
        v[f"n_prev_{s}"] = float(n)
        v[f"poca_historia_{s}"] = 1.0 if n < 34 else 0.0
        if self.ot_min is None or ot - 2 < self.ot_min:
            v[f"recien_ascendido_{s}"] = NAN
        else:
            jugo = sum(1 for k in (ot - 1, ot - 2) if equipo in self.jugo_torneo.get(k, ()))
            hubo = sum(1 for k in (ot - 1, ot - 2) if k in self.jugo_torneo)
            v[f"recien_ascendido_{s}"] = 1.0 if jugo < hubo else 0.0

    # ---- c) tabla -------------------------------------------------------------------------------------------
    def _v_tabla(self, v, M, L, V):
        tor = M["torneo"]
        fm = formato_torneo(tor)
        tb = self.tabla.get(tor) or {}
        res = self._posiciones(tor)
        orden = res[0] if res else []
        completa = len(tb) == fm["partidos"] + 1
        for s, e in (("l", L), ("v", V)):
            f = tb.get(e)
            if f is None:
                v[f"tabla_pos_{s}"] = v[f"tabla_ppp_{s}"] = v[f"tabla_dgpp_{s}"] = NAN
                v[f"tabla_dist8_{s}"] = v[f"tabla_dist_zona_{s}"] = NAN
                v[f"tabla_pj_{s}"] = v[f"tabla_pts_{s}"] = 0.0
                v[f"tabla_rest_{s}"] = float(fm["partidos"])
                v[f"tabla_clasificado_{s}"] = v[f"tabla_eliminado_{s}"] = 0.0
                continue
            pj, pts = f[0], f[1]
            v[f"tabla_pos_{s}"] = float(res[1][e])
            v[f"tabla_pj_{s}"], v[f"tabla_pts_{s}"] = float(pj), float(pts)
            v[f"tabla_ppp_{s}"] = pts / pj
            v[f"tabla_dgpp_{s}"] = (f[2] - f[3]) / pj
            v[f"tabla_dist8_{s}"] = float(pts - tb[orden[7]][1]) if len(orden) >= 8 else NAN
            z = fm["zona"]
            v[f"tabla_dist_zona_{s}"] = float(pts - tb[orden[z - 1]][1]) if len(orden) >= z else NAN
            rest = max(fm["partidos"] - pj, 0)
            v[f"tabla_rest_{s}"] = float(rest)
            clas = elim = 0.0
            if completa:
                alcanzan = arriba = 0
                maximo = pts + 3 * rest
                for o in orden:
                    if o == e:
                        continue
                    fo = tb[o]
                    if fo[1] + 3 * max(fm["partidos"] - fo[0], 0) >= pts:
                        alcanzan += 1
                    if fo[1] > maximo:
                        arriba += 1
                clas = 1.0 if alcanzan < z else 0.0
                elim = 1.0 if arriba >= z else 0.0
            v[f"tabla_clasificado_{s}"], v[f"tabla_eliminado_{s}"] = clas, elim
        if M["fase"] == "regular":
            pj = v["tabla_pj_l"] + v["tabla_pj_v"]
            v["jornada_est"] = float(int(pj // 2) + 1)
            v["avance_torneo"] = min(pj / (2.0 * fm["partidos"]), 1.0)
        else:
            v["jornada_est"] = NAN
            v["avance_torneo"] = 1.0

    # ---- d) calendario ----------------------------------------------------------------------------------------
    def _v_calendario(self, v, M, L, V):
        t, ot, corte = M["_t"], M["_ot"], M["_corte"]
        largas = 0
        for s, e in (("l", L), ("v", V)):
            cal = self.cal.get(e, ())
            i = bisect.bisect_left(cal, (t,))
            if i == 0:
                v[f"descanso_{s}"] = NAN
                v[f"pj14_{s}"] = 0.0
                v[f"pausa_larga_{s}"] = 0.0
                v[f"primer_partido_torneo_{s}"] = 1.0
                v[f"pendientes_previos_{s}"] = 0.0
                continue
            tp, otp, _ = cal[i - 1]
            dias = (t - tp) / DIA
            v[f"descanso_{s}"] = min(dias, MAX_DESCANSO)
            v[f"pj14_{s}"] = float(i - bisect.bisect_left(cal, (t - 14 * DIA,)))
            mismo = otp == ot
            larga = 1.0 if (dias > 10 and mismo) else 0.0
            v[f"pausa_larga_{s}"] = larga
            largas += int(larga)
            v[f"primer_partido_torneo_{s}"] = 0.0 if mismo else 1.0
            pend, j = 0, i - 1
            while j >= 0 and cal[j][2] > corte:
                pend += 1
                j -= 1
            v[f"pendientes_previos_{s}"] = float(pend)
        v["regreso_pausa"] = 1.0 if largas == 2 else 0.0
        v["media_semana"] = 1.0 if M["_ds"] in (1, 2, 3) else 0.0
        v["dia_semana"] = float(M["_ds"])
        v["hora_local"] = float(M["_hora"])
        v["mes"] = float(M["_mes"])

    # ---- e) sede -------------------------------------------------------------------------------------------------
    def _v_sede(self, v, M, hL, hV, L, V, vl):
        t = M["_t"]
        sede, imput = self._sede_partido(M["id"], M["estadio_id"], L, hL, t)
        hab_l, hab_v = self._habitual(hL, t), self._habitual(hV, t)
        v["sede_imputada"] = float(imput)
        if sede is None:
            for k in ("sede_altitud", "sede_altura", "sede_sintetico", "sede_habitual_l", "sede_compartida",
                      "sede_tambien_v", "sede_alt_dif_v", "sede_viaje_km_v", "sede_viaje_km_l"):
                v[k] = NAN
            info = None
        else:
            info = self.sede_info[sede]
            alt, sint = self._alt_sint(sede, t)
            v["sede_altitud"] = alt if alt is not None else NAN
            v["sede_altura"] = (1.0 if alt >= ALTURA_M else 0.0) if alt is not None else NAN
            v["sede_sintetico"] = float(sint)
            v["sede_habitual_l"] = (1.0 if hab_l == sede else 0.0) if hab_l is not None else NAN
            v["sede_tambien_v"] = (1.0 if hab_v == sede else 0.0) if hab_v is not None else NAN
            comp = 0.0
            for nombre, h in self.eq.items():
                if nombre != L and self._habitual(h, t) == sede:
                    comp = 1.0
                    break
            v["sede_compartida"] = comp
            if hab_v is not None:
                iv = self.sede_info[hab_v]
                v["sede_alt_dif_v"] = info[2] - iv[2]
                v["sede_viaje_km_v"] = 0.0 if hab_v == sede else _haversine(iv[0], iv[1], info[0], info[1])
            else:
                v["sede_alt_dif_v"] = v["sede_viaje_km_v"] = NAN
            if hab_l is not None:
                il = self.sede_info[hab_l]
                v["sede_viaje_km_l"] = 0.0 if hab_l == sede else _haversine(il[0], il[1], info[0], info[1])
            else:
                v["sede_viaje_km_l"] = NAN
        # ventaja de local del equipo en esta sede, con credibilidad
        casa = [r for r in hL.L if r.sede == sede] if sede is not None else []
        v["sede_n_l"] = float(len(casa)) if sede is not None else NAN
        z = 0.0
        d = NAN
        if casa:
            casa = casa[-VENTANA_SEDE:]
            t0 = casa[0].t
            sf = nf = 0
            for r in reversed(hL.V):
                if r.t < t0:
                    break
                sf += r.gf - r.gc
                nf += 1
            if nf:
                nc = len(casa)
                d = sum(r.gf - r.gc for r in casa) / nc - sf / nf
                m = nc * nf / (nc + nf)
                z = m / (m + self.k_sede) if self.k_sede != math.inf else 0.0
        if vl != vl:
            v["sede_vl_l"] = v["sede_vl_rel_l"] = v["sede_vl_z_l"] = NAN
        else:
            rel = z * (d - 2.0 * vl) if z > 0.0 else 0.0
            v["sede_vl_rel_l"] = rel
            v["sede_vl_l"] = vl + rel
            v["sede_vl_z_l"] = z
        # rendimiento del visitante en altura y en sintético
        alto, bajo, sint_, nat = [], [], [], []
        for r in reversed(hV.V[-200:]):
            dg = r.gf - r.gc
            if r.alt is not None:
                if r.alt >= ALTURA_M:
                    if len(alto) < 20:
                        alto.append(dg)
                elif len(bajo) < 40:
                    bajo.append(dg)
            if r.sint is not None:
                if r.sint == 1:
                    if len(sint_) < 10:
                        sint_.append(dg)
                elif len(nat) < 40:
                    nat.append(dg)
        for pref, a, b in (("visita_altura", alto, bajo), ("visita_sint", sint_, nat)):
            v[f"{pref}_n_v"] = float(len(a))
            ma = sum(a) / len(a) if len(a) >= 3 else NAN
            v[f"{pref}_dg_v"] = ma
            v[f"{pref}_rel_v"] = ma - sum(b) / len(b) if (len(a) >= 3 and len(b) >= 3) else NAN

    # ---- f) historial directo -----------------------------------------------------------------------------------
    def _v_h2h(self, v, M, L, V, vl, pts_casa, pts_fuera):
        llave = (L, V) if L < V else (V, L)
        lista = self.h2h.get(llave, ())
        v["h2h_n"] = float(len(lista))
        sede, _ = self._sede_partido(M["id"], M["estadio_id"], L, self.eq.get(L, _VACIO), M["_t"])

        def resumen(partidos):
            """(puntos y DG por partido del local actual, ajustados por localía y encogidos, n)."""
            n = len(partidos)
            if n == 0 or vl != vl:
                return NAN, NAN
            sp = sd = 0.0
            for (_, _, _, loc, gl, gv, _) in partidos:
                if loc == L:
                    dg, base_p, base_d = gl - gv, pts_casa, vl
                else:
                    dg, base_p, base_d = gv - gl, pts_fuera, -vl
                sp += (3 if dg > 0 else (1 if dg == 0 else 0)) - base_p
                sd += dg - base_d
            z = n / (n + K_H2H)
            return z * sp / n, z * sd / n

        v["h2h6_pts_l"], v["h2h6_dg_l"] = resumen(lista[-6:])
        v["h2h10_pts_l"], v["h2h10_dg_l"] = resumen(lista[-10:])
        en_sede = [x for x in lista if x[3] == L and x[6] == sede] if sede is not None else []
        v["h2h_sede_n"] = float(len(en_sede))
        v["h2h_sede_pts_l"], v["h2h_sede_dg_l"] = resumen(en_sede[-6:])
        lig = [x for x in lista if x[2] != "regular"]
        v["h2h_lig_n"] = float(len(lig))
        v["h2h_lig_pts_l"], v["h2h_lig_dg_l"] = resumen(lig[-10:])
        fin = [x for x in lig if x[2] == "final"]
        v["h2h_final_n"] = float(len(fin))
        v["h2h_final_dg_l"] = resumen(fin[-10:])[1]
        ser = self.series_h2h.get(llave, ())
        v["h2h_lig_series_n"] = float(len(ser))
        v["h2h_lig_series_bal_l"] = float(sum((g == L) - (g == V) for _, _, g in ser))
        fs = [x for x in ser if x[1] == "final"]
        v["h2h_final_series_n"] = float(len(fs))
        v["h2h_final_series_bal_l"] = float(sum((g == L) - (g == V) for _, _, g in fs))

    # ---- j) fase -----------------------------------------------------------------------------------------------
    def _v_fase(self, v, M, L, V):
        tor, ot, fase = M["torneo"], M["_ot"], M["fase"]
        lig = fase != "regular"
        pierna = M["pierna"]
        v["es_liguilla"] = 1.0 if lig else 0.0
        v["ronda"] = float(FASES_RONDA.get(fase, 0))
        v["pierna"] = pierna if (lig and pierna == pierna) else NAN
        vuelta = lig and pierna == 2
        v["es_vuelta"] = 1.0 if vuelta else 0.0
        v["global_gf_l"] = v["global_gc_l"] = v["global_dif_l"] = NAN
        if vuelta:
            a, b = (L, V) if L < V else (V, L)
            for p in self.series.get((tor, fase, a, b), ()):
                if p["pierna"] == 1:
                    gf, gc = (p["gl"], p["gv"]) if p["local"] == L else (p["gv"], p["gl"])
                    v["global_gf_l"], v["global_gc_l"], v["global_dif_l"] = float(gf), float(gc), float(gf - gc)
        sl = sv = NAN
        if lig:
            res = self._posiciones(tor)
            if res is not None:
                sl, sv = float(res[1].get(L, NAN)), float(res[1].get(V, NAN))
        v["sembrado_l"], v["sembrado_v"] = sl, sv
        fav_l = fav_v = 0.0
        if fase in ("cuartos", "semifinal") and sl == sl and sv == sv and sl != sv:
            fav_l, fav_v = (1.0, 0.0) if sl < sv else (0.0, 1.0)
        v["empate_favorece_l"], v["empate_favorece_v"] = fav_l, fav_v
        v["regla_gol_visitante"] = 1.0 if (fase in ("cuartos", "semifinal") and formato_torneo(tor)["gol_visitante"]) else 0.0
        v["ventaja_serie_l"] = v["global_dif_l"] + 0.5 * (fav_l - fav_v) if vuelta else NAN
        for s, e in (("l", L), ("v", V)):
            jug = gan = fin = tit = 0
            for (o, f, g) in self.series_eq.get(e, ()):
                if ot - 6 <= o <= ot:
                    jug += 1
                    gan += 1 if g else 0
                if f == "final" and ot - 10 <= o <= ot:
                    fin += 1
                    tit += 1 if g else 0
            v[f"lig_series6_{s}"], v[f"lig_ganadas6_{s}"] = float(jug), float(gan)
            v[f"finales10_{s}"], v[f"titulos10_{s}"] = float(fin), float(tit)

    # ---- k) mercado ----------------------------------------------------------------------------------------------
    @staticmethod
    def _v_mercado(v, M):
        claves = ("mercado_p_l", "mercado_p_e", "mercado_p_v", "mercado_margen", "mercado_abre_p_l",
                  "mercado_abre_p_e", "mercado_abre_p_v", "mercado_linea", "mercado_p_over", "mercado_abre_p_over")
        for k in claves:
            v[k] = NAN
        a, e, b = M["ml_l"], M["ml_e"], M["ml_v"]
        hay = a == a and e == e and b == b and min(a, e, b) > 1.0
        linea, over, under = M["total_linea"], M["over"], M["under"]
        dudoso = 0.0
        if hay and (min(a, e, b) < 1.08 or e < 2.0 or e > 12.0
                    or (linea == 2.5 and ((over == over and over < 1.15) or (under == under and under < 1.15)))):
            dudoso = 1.0                                 # momios capturados en vivo: fugan el resultado
        v["mercado_dudoso"] = dudoso if hay else NAN
        if dudoso:
            return
        if hay:
            s = 1 / a + 1 / e + 1 / b
            v["mercado_p_l"], v["mercado_p_e"], v["mercado_p_v"] = (1 / a) / s, (1 / e) / s, (1 / b) / s
            v["mercado_margen"] = s - 1.0
        a, e, b = M["ml_l_abre"], M["ml_e_abre"], M["ml_v_abre"]
        if a == a and e == e and b == b and min(a, e, b) > 1.0:
            s = 1 / a + 1 / e + 1 / b
            v["mercado_abre_p_l"], v["mercado_abre_p_e"], v["mercado_abre_p_v"] = (1 / a) / s, (1 / e) / s, (1 / b) / s
        if linea == linea:
            v["mercado_linea"] = linea
            if over == over and under == under and min(over, under) > 1.0:
                v["mercado_p_over"] = (1 / over) / (1 / over + 1 / under)
            oa, ua = M["over_abre"], M["under_abre"]
            if oa == oa and ua == ua and min(oa, ua) > 1.0:
                v["mercado_abre_p_over"] = (1 / oa) / (1 / oa + 1 / ua)

    # ---- l) árbitro ----------------------------------------------------------------------------------------------
    def _v_arbitro(self, v, M):
        arb = M["arbitro"].strip()
        if not arb:
            v["arb_n"] = v["arb_tarjetas"] = v["arb_penales"] = NAN
            return
        a = self.arb.get(arb, (0, 0, 0, 0, 0))
        v["arb_n"] = float(a[0])
        if len(self.liga_tar) >= 100:
            media = self.liga_tar_s / len(self.liga_tar)
            v["arb_tarjetas"] = (K_ARBITRO * media + a[2]) / (K_ARBITRO + a[1])
        else:
            v["arb_tarjetas"] = NAN
        if len(self.liga_pen) >= 100:
            media = self.liga_pen_s / len(self.liga_pen)
            v["arb_penales"] = (K_ARBITRO * media + a[4]) / (K_ARBITRO + a[3])
        else:
            v["arb_penales"] = NAN


_BASES_DIF = [base for base, lados, *_ in CATALOGO if lados == "lvd"]


# ==================================================================================================
# Construcción
# ==================================================================================================
def construir(partidos_todos: pd.DataFrame | None = None, hasta=None, corte: str = "partido",
              tarjetas: pd.DataFrame | None = None, alineaciones: pd.DataFrame | None = None,
              sedes: pd.DataFrame | None = None, guardar: bool = False, desde: str = DESDE,
              devolver_estado: bool = False, _calcular_desde: int | None = None):
    """
    Variables a la fecha de cada partido (una fila por partido jugado desde `desde` y por cada programado).

    partidos_todos: tabla de partidos (como partidos.csv, en texto o ya tipada); None = leerla de disco.
    hasta: instante UTC; los partidos que empiezan en ese instante o después se tratan como programados
        (historial truncado). Sus alineaciones y tarjetas se ignoran.
    corte: 'partido' | 'bloque' | 'dia' (ver el encabezado del módulo).
    tarjetas, alineaciones, sedes: tablas auxiliares; None = leerlas de disco.
    guardar: escribe la caché (parquet) y las firmas para la actualización incremental.
    devolver_estado: devuelve (tabla, estado final) para diagnósticos.
    """
    partidos_todos = leer_partidos() if partidos_todos is None else partidos_todos
    tarjetas = leer_tarjetas() if tarjetas is None else tarjetas
    alineaciones = leer_alineaciones() if alineaciones is None else alineaciones
    sedes = leer_sedes() if sedes is None else sedes
    if len(tarjetas) and pd.api.types.is_numeric_dtype(tarjetas["partido_id"]):
        tarjetas = tarjetas.assign(partido_id=_txt(tarjetas["partido_id"]), jugador_id=_txt(tarjetas["jugador_id"]))
    if len(alineaciones) and pd.api.types.is_numeric_dtype(alineaciones["partido_id"]):
        alineaciones = alineaciones.assign(partido_id=_txt(alineaciones["partido_id"]),
                                           jugador_id=_txt(alineaciones["jugador_id"]),
                                           titular=_txt(alineaciones["titular"]))

    tab = _preparar(partidos_todos, hasta, corte)
    onces, conv, cartas = _preparar_aux(tab, tarjetas, alineaciones, hasta)
    regs = tab.to_dict("records")

    calendario: dict[str, list] = {}
    for m in regs:                                       # ya vienen ordenados por inicio
        tinfo = m["_tinfo"] if m["estado"] == "jugado" else math.inf
        for e in (m["local"], m["visitante"]):
            calendario.setdefault(e, []).append((m["_t"], m["_ot"], tinfo))

    est = Estado(sedes, calendario, onces, conv, cartas)
    t_desde = _a_epoca(desde)
    jugados = sorted((m for m in regs if m["estado"] == "jugado"), key=lambda m: (m["_tinfo"], m["_idn"]))
    objetivos = sorted((m for m in regs if m["estado"] == "programado" or m["_t"] >= t_desde),
                       key=lambda m: (m["_corte"], m["_t"], m["_idn"]))
    filas, ident = [], []
    k, n_j = 0, len(jugados)
    for M in objetivos:
        c = M["_corte"]
        while k < n_j and jugados[k]["_tinfo"] <= c:
            est.ingerir(jugados[k])
            k += 1
        if _calcular_desde is not None and M["_t"] < _calcular_desde:
            continue
        filas.append(est.variables(M))
        ident.append((M["_idn"], M["fecha_utc"], c, M["torneo"], periodo_de(M["torneo"]), M["fase"], M["estado"],
                      M["local"], M["visitante"], M["_t"]))

    cols_var = list(catalogo()["variable"])
    if filas and set(filas[0]) != set(cols_var):         # el catálogo y el cálculo deben coincidir
        raise RuntimeError(f"variables sin catálogo: {sorted(set(filas[0]) - set(cols_var))}; "
                           f"catálogo sin cálculo: {sorted(set(cols_var) - set(filas[0]))}")
    df = pd.DataFrame(filas, columns=cols_var).astype("float64")
    idf = pd.DataFrame(ident, columns=["id", "fecha_utc", "corte_utc", "torneo", "periodo", "fase", "estado",
                                       "local", "visitante", "_t"])
    idf["corte_utc"] = pd.to_datetime(idf["corte_utc"], unit="s", utc=True)
    idf["fecha_utc"] = pd.to_datetime(idf["fecha_utc"], utc=True)
    df = pd.concat([idf, df], axis=1).sort_values(["_t", "id"], kind="mergesort").drop(columns="_t").reset_index(drop=True)
    df = _tipos(df)
    if guardar:
        _guardar(df, tab, tarjetas, alineaciones, sedes, corte)
    return (df, est) if devolver_estado else df


# ==================================================================================================
# Caché y actualización incremental
# ==================================================================================================
def _rutas(corte: str):
    sufijo = "" if corte == "partido" else f"_{corte}"
    return (DIR_CACHE / f"variables{sufijo}.parquet", DIR_CACHE / f"variables{sufijo}_firmas.parquet",
            DIR_CACHE / f"variables{sufijo}_meta.json")


def _guardar(df, tab, tarjetas, alineaciones, sedes, corte):
    """Escribe la tabla, las firmas por partido y la firma global."""
    DIR_CACHE.mkdir(parents=True, exist_ok=True)
    r_tab, r_fir, r_meta = _rutas(corte)
    firmas = _firmas(tab, tarjetas, alineaciones)
    tabla_firmas = pd.DataFrame({"id": firmas.index, "firma": firmas.to_numpy(), "t": tab["_t"].to_numpy(),
                                 "estado": tab["estado"].to_numpy()})
    for datos_, ruta in ((df, r_tab), (tabla_firmas, r_fir)):   # escritura atómica: otros procesos leen la caché
        tmp = ruta.with_suffix(".tmp")
        datos_.to_parquet(tmp, index=False)
        tmp.replace(ruta)
    r_meta.write_text(json.dumps({"firma_global": _firma_global(corte, sedes), "corte": corte, "version": VERSION,
                                  "filas": int(len(df)), "columnas": int(df.shape[1]),
                                  "generado_utc": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")},
                                 ensure_ascii=False, indent=1), encoding="utf-8")


def _tipos(df: pd.DataFrame) -> pd.DataFrame:
    """Tipos fijos de las columnas de identificación (iguales al construir, al leer la caché y al unir)."""
    df["id"] = df["id"].astype("int64")
    for c in ("fecha_utc", "corte_utc"):
        df[c] = pd.to_datetime(df[c], utc=True).dt.as_unit("ns")
    for c in ("torneo", "periodo", "fase", "estado", "local", "visitante"):
        df[c] = df[c].astype("str")
    return df


def cargar(corte: str = "partido") -> pd.DataFrame:
    """Lee la caché de variables (constrúyela antes con actualizar())."""
    return _tipos(pd.read_parquet(_rutas(corte)[0]))


def actualizar(corte: str = "partido", forzar: bool = False, verboso: bool = False) -> pd.DataFrame:
    """
    Pone al día la caché leyendo los CSV de datos/. Si la caché es válida sólo recalcula las filas de los
    partidos que empiezan en o después del primer partido nuevo o modificado (y todos los pendientes);
    lo anterior no puede cambiar porque cada fila depende sólo de su pasado. Si cambió algo global
    (versión, sedes, formato) o no hay caché, reconstruye todo.
    """
    t0 = time.time()
    partidos, tarjetas, alineaciones, sedes = leer_partidos(), leer_tarjetas(), leer_alineaciones(), leer_sedes()
    r_tab, r_fir, r_meta = _rutas(corte)
    completo = forzar or not (r_tab.exists() and r_fir.exists() and r_meta.exists())
    if not completo:
        try:
            meta = json.loads(r_meta.read_text(encoding="utf-8"))
            completo = meta.get("firma_global") != _firma_global(corte, sedes)
        except Exception:
            completo = True
    if completo:
        df = construir(partidos, corte=corte, tarjetas=tarjetas, alineaciones=alineaciones, sedes=sedes, guardar=True)
        if verboso:
            print(f"[variables:{corte}] reconstrucción completa: {len(df)} filas en {time.time() - t0:.1f} s")
        return df

    tab = _preparar(partidos, None, corte)
    nuevas = _firmas(tab, tarjetas, alineaciones)
    viejas = pd.read_parquet(r_fir)
    v_firma = dict(zip(viejas["id"], viejas["firma"]))
    v_t = dict(zip(viejas["id"], viejas["t"]))
    n_t = dict(zip(tab["id"], tab["_t"]))
    cambios = [min(n_t[i], v_t.get(i, n_t[i])) for i, f in nuevas.items() if v_firma.get(i) != f]
    cambios += [v_t[i] for i in v_firma if i not in n_t]
    pend = tab.loc[tab["estado"] == "programado", "_t"]
    if len(pend):
        cambios.append(int(pend.min()))
    cache = cargar(corte)
    if not cambios:
        if verboso:
            print(f"[variables:{corte}] sin cambios ({len(cache)} filas, {time.time() - t0:.1f} s)")
        return cache
    desde_t = int(min(cambios))
    nuevo = construir(partidos, corte=corte, tarjetas=tarjetas, alineaciones=alineaciones, sedes=sedes,
                      _calcular_desde=desde_t)
    epoca = pd.Timestamp("1970-01-01", tz="UTC")
    t_cache = ((cache["fecha_utc"] - epoca) // pd.Timedelta(seconds=1)).astype("int64")
    vigentes = set(pd.to_numeric(tab["id"], errors="coerce").astype("int64"))
    viejo = cache[(t_cache < desde_t) & cache["id"].isin(vigentes)]
    df = _tipos(pd.concat([viejo, nuevo], ignore_index=True))
    df = df.sort_values(["fecha_utc", "id"], kind="mergesort").reset_index(drop=True)
    _guardar(df, tab, tarjetas, alineaciones, sedes, corte)
    if verboso:
        print(f"[variables:{corte}] incremental: {len(nuevo)} filas recalculadas de {len(df)} "
              f"(desde {pd.Timestamp(desde_t, unit='s', tz='UTC'):%Y-%m-%d %H:%M}Z) en {time.time() - t0:.1f} s")
    return df


def ids_sin_sede(partidos: pd.DataFrame | None = None, sedes: pd.DataFrame | None = None) -> pd.DataFrame:
    """Estadios de ESPN (desde 2010) que no están en estadios_sedes.csv: hay que agregarlos a mano."""
    p = leer_partidos() if partidos is None else partidos
    s = leer_sedes() if sedes is None else sedes
    p = p[(p["fecha_utc"].astype(str) >= DESDE) & (_txt(p["estadio_id"]) != "")]
    falt = p[~_txt(p["estadio_id"]).isin(set(s["estadio_id"]))]
    return falt.groupby(["estadio_id", "estadio", "ciudad"]).size().rename("partidos").reset_index()


# ==================================================================================================
# Documentación y análisis exploratorio (sólo DESARROLLO)
# ==================================================================================================
def tabla_catalogo_md(df: pd.DataFrame | None = None) -> str:
    """Tabla Markdown de todas las variables con el primer torneo desde el que hay dato (>= 80% de filas)."""
    df = cargar() if df is None else df
    cat = catalogo()
    jug = df[df["estado"] == "jugado"]
    torneos = sorted(jug["torneo"].unique(), key=orden_torneo)
    cob = jug.groupby("torneo")[list(cat["variable"])].agg(lambda s: s.notna().mean()).reindex(torneos)
    lineas = ["| Variable | Grupo | Definición | Hay dato desde | Cobertura en DESARROLLO | Disponible al pronosticar |",
              "|---|---|---|---|---:|---|"]
    des = jug[jug["periodo"] == "desarrollo"]
    etiqueta = {"si": "sí", "no": "NO (_real)", "mercado": "sólo con momios publicados", "si*": "sí, si ya hay árbitro designado"}
    for r in cat.itertuples():
        c = cob[r.variable]
        desde = next((t for i, t in enumerate(torneos) if (c.iloc[i:] >= 0.8).all()), None)
        if desde is None:
            desde = next((t for t in torneos if c[t] > 0), "sin dato")
            desde = f"{desde} (parcial)" if desde != "sin dato" else desde
        lineas.append(f"| `{r.variable}` | {r.grupo} | {r.definicion} | {desde} | {des[r.variable].notna().mean():.0%} | {etiqueta[r.disponible]} |")
    return "\n".join(lineas)


def _logit_ordenado(y: np.ndarray, x: np.ndarray):
    """
    Logit ordenado (momios proporcionales) para y en {0 visita, 1 empate, 2 local}: P(y <= k) = F(c_k - x'b).
    Máxima verosimilitud con BFGS; errores estándar de la inversa del hessiano numérico.
    Devuelve (coeficientes b, errores estándar de b, log-verosimilitud).
    """
    from scipy.optimize import minimize
    n, p = x.shape

    def nll(par):
        c1, c2 = par[0], par[0] + math.exp(par[1])
        eta = x @ par[2:]
        f1 = 1.0 / (1.0 + np.exp(-(c1 - eta)))
        f2 = 1.0 / (1.0 + np.exp(-(c2 - eta)))
        pr = np.where(y == 0, f1, np.where(y == 1, f2 - f1, 1.0 - f2))
        return -np.sum(np.log(np.clip(pr, 1e-12, None)))

    ini = np.zeros(p + 2)
    ini[0], ini[1] = -1.0, math.log(1.2)
    r = minimize(nll, ini, method="BFGS", options={"gtol": 1e-6, "maxiter": 500})
    par = r.x
    k = len(par)
    h = np.zeros((k, k))
    eps = 1e-4
    for i in range(k):
        for j in range(i, k):
            pp = par.copy(); pp[i] += eps; pp[j] += eps
            pm = par.copy(); pm[i] += eps; pm[j] -= eps
            mp = par.copy(); mp[i] -= eps; mp[j] += eps
            mm = par.copy(); mm[i] -= eps; mm[j] -= eps
            h[i, j] = h[j, i] = (nll(pp) - nll(pm) - nll(mp) + nll(mm)) / (4 * eps * eps)
    try:
        cov = np.linalg.inv(h)
        ee = np.sqrt(np.clip(np.diag(cov), 0, None))[2:]
    except np.linalg.LinAlgError:
        ee = np.full(p, np.nan)
    return par[2:], ee, -r.fun


def _resultados_desarrollo(df: pd.DataFrame, partidos: pd.DataFrame | None = None) -> pd.DataFrame:
    """Filas de DESARROLLO jugadas (sin resultados de escritorio) con y = 0 visita, 1 empate, 2 local."""
    p = leer_partidos() if partidos is None else partidos
    res = p[p["estado"] == "jugado"][["id", "gl", "gv", "nota"]].copy()
    res["id"] = pd.to_numeric(res["id"]).astype("int64")
    gl, gv = res["gl"].astype(int), res["gv"].astype(int)
    res["y"] = np.where(gl > gv, 2, np.where(gl == gv, 1, 0))
    res["goles"] = gl + gv
    res = res[~res["nota"].astype(str).str.contains("escritorio|abandonado", case=False, regex=True)]
    return df[(df["periodo"] == "desarrollo") & (df["estado"] == "jugado")].merge(res[["id", "y", "goles"]], on="id")


def analisis_exploratorio(df: pd.DataFrame | None = None, partidos: pd.DataFrame | None = None,
                          base: str = "elo") -> pd.DataFrame:
    """
    Asociación univariada de cada variable con el resultado MÁS ALLÁ de la fuerza base, sólo en DESARROLLO.

    Para cada variable x: logit ordenado del resultado (visita < empate < local) sobre la fuerza base y x
    estandarizada; se reporta el coeficiente de x por desviación estándar (positivo = favorece al local),
    su error estándar, z, el valor p de la razón de verosimilitudes (1 g.l.) y la mejora de log-loss por
    partido frente al modelo con sólo la base, en la misma muestra.
      base='elo'      -> fuerza base = elo_dif / 100 (todo DESARROLLO).
      base='mercado'  -> fuerza base = log(p_local / p_visita) del cierre sin margen (sólo donde hay momios).
    Es exploratorio y DENTRO de muestra: sirve para orientar, no para elegir variables (con ~300 pruebas se
    esperan ~15 con p < 0.05 por puro azar; por eso se agrega el valor q de Benjamini-Hochberg).
    """
    from scipy.stats import chi2
    df = cargar() if df is None else df
    d = _resultados_desarrollo(df, partidos)
    if base == "elo":
        d = d.assign(_base=d["elo_dif"] / 100.0)
        excluir = {"elo_dif", "elo_l", "elo_v"}
    elif base == "mercado":
        d = d.assign(_base=np.log(d["mercado_p_l"] / d["mercado_p_v"]))
        excluir = {"mercado_p_l", "mercado_p_v", "mercado_p_e", "mercado_dudoso"}
    else:
        raise ValueError("base debe ser 'elo' o 'mercado'")
    cat = catalogo()
    filas, memo = [], {}
    for r in cat.itertuples():
        var = r.variable
        fila = {"variable": var, "grupo": r.grupo, "disponible": r.disponible}
        sub = d[["y", "_base", var]].dropna() if var not in excluir else d.iloc[:0]
        fila["n"] = len(sub)
        if len(sub) >= 100 and sub[var].nunique() >= 2 and sub[var].std() > 0:
            y = sub["y"].to_numpy()
            xb = sub["_base"].to_numpy().reshape(-1, 1)
            z = ((sub[var] - sub[var].mean()) / sub[var].std()).to_numpy().reshape(-1, 1)
            llave = hash(sub.index.to_numpy().tobytes())  # el modelo base se reusa si la muestra es la misma
            if llave not in memo:
                memo[llave] = _logit_ordenado(y, xb)[2]
            ll0 = memo[llave]
            b, ee, ll1 = _logit_ordenado(y, np.hstack([xb, z]))
            lr = max(2 * (ll1 - ll0), 0.0)
            fila.update(coef=b[1], ee=ee[1], z=b[1] / ee[1] if ee[1] > 0 else np.nan, p_rv=float(chi2.sf(lr, 1)),
                        mejora_logloss=(ll1 - ll0) / len(sub), coef_base=b[0], media=sub[var].mean(), de=sub[var].std())
        filas.append(fila)
    out = pd.DataFrame(filas)
    # Benjamini-Hochberg sobre las variables disponibles al pronosticar (sin mercado ni _real)
    m = out["p_rv"].notna() & out["disponible"].isin(["si", "si*"])
    orden = out.loc[m, "p_rv"].sort_values()
    q = (orden * m.sum() / np.arange(1, len(orden) + 1))[::-1].cummin()[::-1]
    out["q_bh"] = np.nan
    out.loc[q.index, "q_bh"] = q.clip(upper=1.0)
    return out


def _poisson(y: np.ndarray, x: np.ndarray):
    """Regresión de Poisson (enlace log) por IRLS. Devuelve (coeficientes, errores estándar, log-verosimilitud)."""
    from scipy.special import gammaln
    x1 = np.column_stack([np.ones(len(y)), x])
    b = np.zeros(x1.shape[1])
    b[0] = math.log(max(y.mean(), 1e-9))
    for _ in range(50):
        mu = np.exp(x1 @ b)
        paso = np.linalg.solve(x1.T @ (x1 * mu[:, None]), x1.T @ (y - mu))
        b = b + paso
        if np.max(np.abs(paso)) < 1e-10:
            break
    mu = np.exp(x1 @ b)
    cov = np.linalg.inv(x1.T @ (x1 * mu[:, None]))
    return b, np.sqrt(np.diag(cov)), float(np.sum(y * np.log(mu) - mu - gammaln(y + 1)))


def analisis_goles(df: pd.DataFrame | None = None, partidos: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Asociación univariada con el TOTAL de goles del partido, sólo en DESARROLLO: regresión de Poisson de
    los goles sobre liga_goles (nivel de la liga en ese momento) y la variable estandarizada. Coeficiente
    por desviación estándar (0.03 = +3% de goles), error estándar y valor p de razón de verosimilitudes.
    """
    from scipy.stats import chi2
    df = cargar() if df is None else df
    d = _resultados_desarrollo(df, partidos)
    d = d.assign(
        goles10_suma=d["forma10_gf_l"] + d["forma10_gc_l"] + d["forma10_gf_v"] + d["forma10_gc_v"],
        xg10_suma=d["juego10_xg_f_l"] + d["juego10_xg_c_l"] + d["juego10_xg_f_v"] + d["juego10_xg_c_v"],
        tiros10_suma=d["juego10_tiros_f_l"] + d["juego10_tiros_c_l"] + d["juego10_tiros_f_v"] + d["juego10_tiros_c_v"],
        elo_abs=d["elo_dif"].abs())
    variables = ["goles10_suma", "xg10_suma", "tiros10_suma", "elo_abs", "sede_altitud", "sede_alt_dif_v",
                 "sede_viaje_km_v", "sede_sintetico", "es_liguilla", "es_vuelta", "media_semana", "hora_local", "mes",
                 "descanso_l", "descanso_v", "avance_torneo", "susp_n_l", "susp_n_v", "arb_penales", "arb_tarjetas",
                 "mercado_linea", "mercado_p_over"]
    filas = []
    for var in variables:
        sub = d[["goles", "liga_goles", var]].dropna()
        y = sub["goles"].to_numpy(dtype="float64")
        base = (sub["liga_goles"] - sub["liga_goles"].mean()).to_numpy().reshape(-1, 1)
        z = ((sub[var] - sub[var].mean()) / sub[var].std()).to_numpy().reshape(-1, 1)
        _, _, ll0 = _poisson(y, base)
        b, ee, ll1 = _poisson(y, np.hstack([base, z]))
        filas.append({"variable": var, "n": len(sub), "coef": b[2], "ee": ee[2], "z": b[2] / ee[2],
                      "p_rv": float(chi2.sf(max(2 * (ll1 - ll0), 0), 1))})
    return pd.DataFrame(filas)


def analisis_md(df: pd.DataFrame | None = None) -> str:
    """Texto Markdown del análisis exploratorio (las tablas de VARIABLES.md salen de aquí)."""
    df = cargar() if df is None else df
    a = analisis_exploratorio(df, base="elo")
    m = analisis_exploratorio(df, base="mercado").set_index("variable")
    d = _resultados_desarrollo(df)
    lineas = [f"Muestra: {len(d)} partidos de DESARROLLO; con momios de cierre utilizables: "
              f"{int(d['mercado_p_l'].notna().sum())}.", ""]
    val = a[a["p_rv"].notna() & a["disponible"].isin(["si", "si*"])]
    lineas += [f"Variables disponibles probadas (base Elo): {len(val)}; con p < 0.05: {int((val['p_rv'] < 0.05).sum())} "
               f"(por azar se esperarían {0.05 * len(val):.0f}); con q de Benjamini-Hochberg < 0.10: "
               f"{int((val['q_bh'] < 0.10).sum())}.", ""]
    lineas += ["### Por grupo (base Elo)", "",
               "| Grupo | Variables | p < 0.05 | q < 0.10 | Mejor variable | coef (ee) | p | Δ log-loss por partido |",
               "|---|---:|---:|---:|---|---:|---:|---:|"]
    for g, sub in a[a["p_rv"].notna()].groupby("grupo"):
        mejor = sub.sort_values("p_rv").iloc[0]
        lineas.append(f"| {g} | {len(sub)} | {int((sub['p_rv'] < 0.05).sum())} | {int((sub['q_bh'] < 0.10).sum())} | "
                      f"`{mejor['variable']}` | {mejor['coef']:+.3f} ({mejor['ee']:.3f}) | {mejor['p_rv']:.4f} | "
                      f"{mejor['mejora_logloss']:.5f} |")
    lineas += ["", "### Todas las variables", "",
               "| Variable | Grupo | n | coef (ee), base Elo | z | p | q BH | Δ log-loss | n con momios | coef (ee), base mercado | p |",
               "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]

    def fmt(x, f):
        return "" if x != x else format(x, f)

    for r in a.itertuples():
        mm = m.loc[r.variable]
        ce = f"{r.coef:+.3f} ({r.ee:.3f})" if r.coef == r.coef else "sin datos suficientes"
        cm = f"{mm['coef']:+.3f} ({mm['ee']:.3f})" if mm["coef"] == mm["coef"] else ""
        lineas.append(f"| `{r.variable}` | {r.grupo} | {r.n} | {ce} | {fmt(r.z, '+.2f')} | {fmt(r.p_rv, '.4f')} | "
                      f"{fmt(r.q_bh, '.3f')} | {fmt(r.mejora_logloss, '.5f')} | {int(mm['n'])} | {cm} | {fmt(mm['p_rv'], '.4f')} |")
    g = analisis_goles(df)
    lineas += ["", "### Total de goles (Poisson sobre liga_goles + variable)", "",
               "| Variable | n | coef por DE (ee) | z | p |", "|---|---:|---:|---:|---:|"]
    for r in g.itertuples():
        lineas.append(f"| `{r.variable}` | {r.n} | {r.coef:+.3f} ({r.ee:.3f}) | {r.z:+.2f} | {r.p_rv:.4f} |")
    return "\n".join(lineas)


def _main(argv):
    if "--catalogo" in argv:
        print(tabla_catalogo_md())
        return
    if "--analisis" in argv:
        print(analisis_md())
        return
    forzar = "--completo" in argv
    for corte in ("partido", "bloque"):
        df = actualizar(corte=corte, forzar=forzar, verboso=True)
        pend = df[df["estado"] == "programado"]
        print(f"  {corte}: {len(df)} filas, {df.shape[1]} columnas, {len(pend)} pendientes")
    falt = ids_sin_sede()
    if len(falt):
        print("AVISO: estadios de ESPN sin fila en estadios_sedes.csv (se imputa la sede habitual del local):")
        print(falt.to_string(index=False))


if __name__ == "__main__":
    _main(sys.argv[1:])
