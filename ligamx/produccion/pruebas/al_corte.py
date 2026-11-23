# -*- coding: utf-8 -*-
"""
Datos «como estaban» en una fecha de corte, para que las pruebas no dependan de cómo va la temporada.

Las pruebas de producción usan un corte fijo (10-nov-2026, con la Jornada 17 por jugar). Al avanzar la
temporada esos partidos ya están jugados en partidos.csv, aparecen filas reales de liguilla y, más adelante,
el calendario del torneo siguiente; sin esta función `datos.pendientes()` queda vacío y la siembra cambia.
`al_corte()` devuelve una COPIA en memoria (nunca toca datos/): lo del torneo posterior al corte vuelve a
«programado» sin marcador ni estadísticas, se quitan las filas de liguilla de ese torneo posteriores al corte
y los torneos siguientes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from modelo import datos
from produccion import simulador as S


def al_corte(df: pd.DataFrame, corte: str, torneo: str) -> pd.DataFrame:
    c = S.a_utc(corte)
    orden = int(df.loc[df["torneo"] == torneo, "orden_torneo"].iloc[0])
    quitar = (df["orden_torneo"] > orden) | ((df["torneo"] == torneo) & df["fase"].isin(S.FASES_LIGUILLA) & (df["fecha_utc"] >= c))
    d = df[~quitar].copy()
    fut = (d["torneo"] == torneo) & (d["fecha_utc"] >= c) & (d["estado"] != "cancelado")
    previas = set(datos.COLS_PREPARTIDO) | {"estado", "estado_espn", "temporada_espn", "fase_espn", "nota", "escritorio"}
    for col in d.columns:
        if col in previas:
            continue
        if d[col].dtype == bool:
            d.loc[fut, col] = False
        elif pd.api.types.is_integer_dtype(d[col]):
            d.loc[fut, col] = 0
        elif pd.api.types.is_float_dtype(d[col]):
            d.loc[fut, col] = np.nan
        else:
            d.loc[fut, col] = None
    d.loc[fut, "estado"] = "programado"
    return d.reset_index(drop=True)


def pendientes_al_corte(corte: str, torneo: str) -> pd.DataFrame:
    """Lo que `datos.pendientes()` devolvía en el corte: partidos de fase regular de `torneo` desde el corte."""
    d = al_corte(datos.cargar(), corte, torneo)
    p = d[(d["torneo"] == torneo) & (d["estado"] == "programado") & (d["fase"] == "regular")]
    return p.sort_values(["fecha_utc", "id"]).loc[:, datos.COLS_PREPARTIDO].reset_index(drop=True)
