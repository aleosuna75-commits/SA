# -*- coding: utf-8 -*-
"""
Producción de Cerebro Liga MX: mercados, combinadas y contexto de cada partido.

Todo este paquete consume SÓLO el contrato de `Pronosticador` (ver modelo/pronostico.py o
produccion/pronosticador_provisional.py): `equipos`, `partidos(df)`, `malla(n, fase, semilla)` y
`fuerzas()`. Se usa desde la carpeta `ligamx/` (igual que `modelo`).
"""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent            # .../ligamx
RUTA_CAMPEON = RAIZ / "modelo" / "campeon.json"


def origen_pronosticador() -> str:
    """'campeon' si existe modelo/campeon.json (se usa modelo.pronostico); si no, 'provisional'."""
    return "campeon" if RUTA_CAMPEON.exists() else "provisional"


def obtener_pronosticador(corte=None):
    """
    Pronosticador ajustado con lo jugado antes de `corte` (por omisión: ahora).

    Si existe modelo/campeon.json devuelve modelo.pronostico.Pronosticador (el modelo campeón; un
    error al importarlo o ajustarlo NO se oculta: producción no debe caer en silencio a un modelo
    peor). Si no existe, devuelve la clase provisional (Poisson simple), que cumple el mismo contrato.
    """
    if RUTA_CAMPEON.exists():
        from modelo.pronostico import Pronosticador
    else:
        from .pronosticador_provisional import Pronosticador
    return Pronosticador(corte=corte)
