# -*- coding: utf-8 -*-
"""
Modelo EN JUEGO: probabilidad del resultado final de un partido que ya empezó.

Idea: con las lambdas PREVIAS del partido (goles esperados a 90 minutos del pronóstico sellado), el
minuto, el marcador y las expulsiones,

    marcador final = marcador actual + goles restantes,
    goles restantes de cada equipo ~ Poisson( lambda x fracción restante x ajustes ).

  * La FRACCIÓN RESTANTE sale de la curva empírica de goles por minuto (datos/goles.csv): qué parte de
    los goles de un partido cae después de cada minuto. Hay más goles en el segundo tiempo y el tiempo
    agregado pesa cada año más, por eso la curva se estima sólo con los últimos VENTANA_TORNEOS torneos
    anteriores al corte (nunca con el futuro).
  * Los AJUSTES son multiplicadores del ritmo de gol según el marcador (va perdiendo, gana por 1, gana
    por 2 o más) y según las expulsiones (juega con uno menos / con uno más). Se estiman con una
    regresión de Poisson sobre los tramos de cada partido (exposición = lambda previa fuera de muestra x
    parte de la curva que cubre el tramo) y sólo entran los que pasan de UMBRAL_Z errores estándar.
  * El estado se CONGELA: el multiplicador de ahora se aplica a todo lo que falta (aproximación de
    primer orden; si el que pierde empata, su ritmo en realidad vuelve al de empate).

Uso:
    python3 -m produccion.en_juego ajustar     # parámetros de producción -> salidas/en_juego_parametros.json
    python3 -m produccion.en_juego validar     # validación sin fuga en DESARROLLO -> salidas/en_juego_validacion.json
    python3 -m produccion.en_juego curva       # imprime la fracción restante por minuto

Convención de minuto: «minuto m completo» significa que los goles con minuto <= m ya están en el
marcador. El reloj de ESPN en vivo («57'») dice que se está jugando el minuto 57: se usa el punto
medio de esa casilla (en_curso=True).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from modelo import arnes, datos, metricas

RAIZ = datos.RAIZ
DIR_SALIDAS = RAIZ / "salidas"
RUTA_PARAMETROS = DIR_SALIDAS / "en_juego_parametros.json"
RUTA_VALIDACION = DIR_SALIDAS / "en_juego_validacion.json"
MAXG = arnes.MAX_GOLES

# --- Línea de tiempo en casillas -------------------------------------------------------------------
A1, A2 = 12, 16                       # casillas de tiempo agregado: 45+1..45+12 y 90+1..90+16 (la última acumula)
INI_2T = 45 + A1                      # primera casilla del segundo tiempo (minuto 46)
N_CASILLAS = 45 + A1 + 45 + A2        # 118
FIN_1T = INI_2T - 1                   # última casilla del primer tiempo (con su agregado)

VENTANA_TORNEOS = 8                   # torneos (4 años) con los que se estima la curva
MIN_GOLES_CURVA = 800                 # si la ventana trae menos goles, se amplía hacia atrás
UMBRAL_Z = 2.0                        # un ajuste sólo entra si su coeficiente pasa de 2 errores estándar
MODELO_LAMBDAS = "ensamble"           # lambdas previas fuera de muestra (modelo/pred/<nombre>.parquet)
MINUTOS_VALIDACION = (15, 30, 45, 60, 75)
MINUTOS_PISO_AGREGADO = 1.5           # con el balón rodando en el agregado se supone que queda al menos esto
FRACCION_EXTRA = 1.0 / 3.0            # tiempos extra: 30 de 90 minutos (igual que el simulador)
ESTADOS_MARCADOR = ("pierde", "empata", "gana_1", "gana_2")
ESTADOS_ROJA = ("igual", "con_menos", "con_mas")
SIN_EFECTOS = {"base": 1.0, "pierde": 1.0, "gana_1": 1.0, "gana_2": 1.0, "con_menos": 1.0, "con_mas": 1.0}


# ==================================================================================================
# Línea de tiempo
# ==================================================================================================
def casilla(periodo: int, minuto: int, anadido: int = 0) -> int:
    """
    Casilla (0..117) de una jugada del tiempo reglamentario. Primer tiempo: minutos 1..45 -> 0..44 y
    45+a -> 44+a; segundo tiempo: 46..90 -> 57..101 y 90+a -> 101+a. Los registros viejos que traen el
    agregado como minuto 47 (periodo 1) o 93 (periodo 2) caen en la casilla de agregado que les toca.
    """
    periodo, minuto, anadido = int(periodo), int(minuto), int(anadido or 0)
    if periodo <= 1:
        if minuto <= 45 and anadido == 0:
            return max(minuto, 1) - 1
        a = anadido if minuto <= 45 else (minuto - 45) + anadido
        return 44 + min(max(a, 1), A1)
    if minuto <= 90 and anadido == 0:
        return INI_2T + min(max(minuto, 46), 90) - 46
    a = anadido if minuto <= 90 else (minuto - 90) + anadido
    return INI_2T + 44 + min(max(a, 1), A2)


def casilla_de_minuto(minuto: int) -> int:
    """Casilla en la que QUEDA COMPLETO el minuto m de la validación (45 = descanso, con su agregado)."""
    minuto = int(minuto)
    if minuto <= 0:
        return -1
    if minuto < 45:
        return minuto - 1
    if minuto == 45:
        return FIN_1T
    if minuto < 90:
        return INI_2T + minuto - 46
    return N_CASILLAS - 1


class Curva:
    """Reparto de los goles del tiempo reglamentario por casilla (`w`, suma 1) y fracción restante."""

    def __init__(self, w, meta: dict | None = None):
        w = np.asarray(w, float)
        if w.shape != (N_CASILLAS,) or (w < 0).any() or not np.isfinite(w).all() or w.sum() <= 0:
            raise ValueError("curva inválida")
        self.w = w / w.sum()
        self.acum = np.cumsum(self.w)
        self.meta = dict(meta or {})
        # piso con el balón rodando en el agregado: ritmo de los 3 primeros minutos agregados de cada tiempo
        self.piso_1t = MINUTOS_PISO_AGREGADO * float(self.w[45:48].mean())
        self.piso_2t = MINUTOS_PISO_AGREGADO * float(self.w[INI_2T + 45:INI_2T + 48].mean())
        self.parte_2t = float(self.w[INI_2T:].sum())

    def tras(self, c: int) -> float:
        """Fracción de los goles que cae DESPUÉS de completarse la casilla c (c = -1: todo el partido)."""
        if c < 0:
            return 1.0
        return float(max(0.0, 1.0 - self.acum[min(int(c), N_CASILLAS - 1)]))

    def restante(self, minuto: int | None, periodo: int | None = None, anadido: int | None = 0,
                 descanso: bool = False, en_curso: bool = False) -> float:
        """
        Fracción de los goles esperados del partido que falta por caer.
          minuto <= 0 o None      -> 1 (no ha empezado);
          descanso=True           -> lo que pesa el segundo tiempo;
          en_curso=False          -> el minuto (con su agregado) ya está completo;
          en_curso=True           -> se está jugando ese minuto (reloj en vivo): punto medio de la casilla y,
                                     en tiempo agregado, un piso de MINUTOS_PISO_AGREGADO minutos de juego
                                     (mientras ESPN diga que se juega, algo falta).
        Es monótona: nunca sube al avanzar el reloj.
        """
        if descanso:
            return self.parte_2t
        if minuto is None or minuto <= 0:
            return 1.0
        minuto, anadido = int(minuto), int(anadido or 0)
        if periodo is None:
            periodo = 1 if minuto <= 45 else 2
        periodo = 1 if periodo <= 1 else 2
        c = casilla(periodo, minuto, anadido)
        if not en_curso:
            return self.tras(c)
        r = 0.5 * (self.tras(c - 1) + self.tras(c))
        if (periodo == 1 and c >= 45) or (periodo == 2 and c >= INI_2T + 45):      # tiempo agregado
            piso = (self.parte_2t + self.piso_1t) if periodo == 1 else self.piso_2t
            # el piso no rompe la monotonía: nunca más que lo que faltaba al completarse el minuto 45 / 90
            tope = self.tras(44) if periodo == 1 else self.tras(INI_2T + 44)
            r = min(max(r, piso), tope)
        return float(r)

    def por_minuto(self) -> list[dict]:
        """Tabla legible: fracción restante al completarse cada minuto (para VIVO.md y la línea de órdenes)."""
        out = [{"minuto": "0'", "restante": 1.0}]
        for m in (5, 10, 15, 20, 25, 30, 35, 40, 45):
            out.append({"minuto": f"{m}'", "restante": self.restante(m, 1)})
        out.append({"minuto": "descanso", "restante": self.parte_2t})
        for m in (50, 55, 60, 65, 70, 75, 80, 85, 90):
            out.append({"minuto": f"{m}'", "restante": self.restante(m, 2)})
        for a in (2, 4, 6, 8):
            out.append({"minuto": f"90'+{a}'", "restante": self.restante(90, 2, a)})
        return out


# ==================================================================================================
# Efectos del marcador y de las expulsiones
# ==================================================================================================
def estado_marcador(dif: int) -> str:
    """Estado del equipo según su diferencia de goles en ese momento."""
    return "pierde" if dif < 0 else "empata" if dif == 0 else "gana_1" if dif == 1 else "gana_2"


def estado_roja(propias: int, rival: int) -> str:
    """Estado del equipo según las expulsiones: con uno menos, con uno más o iguales."""
    return "con_menos" if propias > rival else "con_mas" if rival > propias else "igual"


def multiplicador(ef: dict, dif: int, rojas_propias: int = 0, rojas_rival: int = 0) -> float:
    """Multiplicador del ritmo de gol de un equipo en su estado actual (1.0 si ningún ajuste aplica)."""
    m = float(ef.get("base", 1.0))
    em = estado_marcador(int(dif))
    if em != "empata":
        m *= float(ef.get(em, 1.0))
    er = estado_roja(int(rojas_propias or 0), int(rojas_rival or 0))
    if er != "igual":
        m *= float(ef.get(er, 1.0))
    return m


class Parametros:
    """Curva + efectos, con de dónde salieron (`meta`). Se guardan en salidas/en_juego_parametros.json."""

    def __init__(self, curva: Curva, ef: dict | None = None, meta: dict | None = None):
        self.curva = curva
        self.ef = {**SIN_EFECTOS, **(ef or {})}
        self.meta = dict(meta or {})

    def a_json(self) -> dict:
        return {"version": 1, "w": [round(float(x), 6) for x in self.curva.w], "curva": self.curva.meta,
                "efectos": {k: round(float(v), 4) for k, v in self.ef.items()}, "meta": self.meta,
                "restante_por_minuto": [{"minuto": d["minuto"], "restante": round(d["restante"], 4)}
                                        for d in self.curva.por_minuto()]}

    @classmethod
    def de_json(cls, d: dict) -> "Parametros":
        return cls(Curva(d["w"], d.get("curva")), d.get("efectos"), d.get("meta"))


# ==================================================================================================
# Pronóstico en juego de un partido
# ==================================================================================================
def lambdas_restantes(par: Parametros, lam_l: float, lam_v: float, gl: int, gv: int, fraccion: float,
                      rojas_l: int = 0, rojas_v: int = 0) -> tuple[float, float]:
    """Goles esperados que le faltan a cada equipo: lambda previa x fracción restante x ajustes."""
    dif = int(gl) - int(gv)
    lr_l = float(lam_l) * fraccion * multiplicador(par.ef, dif, rojas_l, rojas_v)
    lr_v = float(lam_v) * fraccion * multiplicador(par.ef, -dif, rojas_v, rojas_l)
    return max(lr_l, 0.0), max(lr_v, 0.0)


def matriz_final(gl: int, gv: int, lam_rest_l: float, lam_rest_v: float, rho: float = 0.0) -> np.ndarray:
    """
    Matriz 11x11 [goles del local, goles del visitante] del marcador FINAL: el marcador actual más los
    goles restantes (Poisson; con `rho`, la corrección de Dixon-Coles sobre los goles que faltan, que
    al minuto 0 reproduce la matriz previa y se desvanece conforme se acaba el tiempo). Lo que pasaría
    de 10 goles se acumula en la orilla.
    """
    R = arnes.matriz_marcadores(max(float(lam_rest_l), 1e-9), max(float(lam_rest_v), 1e-9), float(rho))
    gl, gv = int(min(gl, MAXG)), int(min(gv, MAXG))
    F = np.zeros_like(R)
    n = MAXG + 1
    F[gl:, gv:] = R[:n - gl, :n - gv]
    if gl:
        F[MAXG, gv:] += R[n - gl:, :n - gv].sum(axis=0)
    if gv:
        F[gl:, MAXG] += R[:n - gl, n - gv:].sum(axis=1)
    if gl and gv:
        F[MAXG, MAXG] += R[n - gl:, n - gv:].sum()
    return F / F.sum()


def pronostico(par: Parametros, lam_l: float, lam_v: float, gl: int, gv: int, minuto: int | None,
               periodo: int | None = None, anadido: int | None = 0, rojas_l: int = 0, rojas_v: int = 0,
               descanso: bool = False, en_curso: bool = True, rho: float = 0.0, terminado: bool = False) -> dict:
    """
    Pronóstico al momento de un partido: 1X2 final, goles que se espera que falten y marcador final más
    probable. `terminado` fija el marcador (fracción restante 0). Devuelve también la matriz `M`.
    """
    fr = 0.0 if terminado else par.curva.restante(minuto, periodo, anadido, descanso=descanso, en_curso=en_curso)
    lr_l, lr_v = lambdas_restantes(par, lam_l, lam_v, gl, gv, fr, rojas_l, rojas_v)
    M = matriz_final(gl, gv, lr_l, lr_v, rho)
    p = np.asarray(arnes.p1x2(M), float).ravel()
    x, y, q = arnes.marcador_mas_probable(M)
    return {"p_local": float(p[0]), "p_empate": float(p[1]), "p_visitante": float(p[2]),
            "goles_restantes_l": float(lr_l), "goles_restantes_v": float(lr_v), "fraccion_restante": float(fr),
            "marcador_final": {"gl": int(x), "gv": int(y), "prob": float(q)}, "M": M}


# ==================================================================================================
# Liguilla: probabilidad de avanzar al momento
# ==================================================================================================
def prob_avanza(fase: str, M1, M2, mejor_local_1: bool, mejor_local_2: bool,
                lam_vuelta: tuple[float, float] | None = None) -> dict:
    """
    P(avanza el mejor sembrado) con `simulador.prob_serie`. M1 y M2 son las matrices de la ida y la
    vuelta tal como estén: `simulador.matriz_fija` si ya se jugó, `matriz_final` (condicional al
    marcador y al minuto) si está en juego, o la matriz previa si no ha empezado. En cuartos y
    semifinales el global empatado lo gana el mejor sembrado; en la final hay tiempos extra con
    `lam_vuelta` (lambdas completas de la vuelta, local y visitante) x 1/3 y penales a 50/50.
    """
    from . import simulador
    if fase == "final":
        if lam_vuelta is None:
            raise ValueError("la final necesita lam_vuelta para los tiempos extra")
        extra = (float(lam_vuelta[0]) * FRACCION_EXTRA, float(lam_vuelta[1]) * FRACCION_EXTRA)
        r = simulador.prob_serie(M1, M2, mejor_local_1, mejor_local_2, "final", extra)
    else:
        r = simulador.prob_serie(M1, M2, mejor_local_1, mejor_local_2, "posicion")
    G = r["G"]
    i, j = np.unravel_index(int(np.argmax(G)), G.shape)
    return {"p_avanza_mejor": float(r["p_mejor"]), "p_avanza_peor": float(r["p_peor"]),
            "p_global_mejor": float(r["p_global_mejor"]), "p_global_empate": float(r["p_global_empate"]),
            "p_global_peor": float(r["p_global_peor"]),
            "global_probable": {"mejor": int(i), "peor": int(j), "prob": float(G[i, j])}}


def prob_tiempos_extra(el: int, ev: int, lam_rest_l: float, lam_rest_v: float, penales: bool = False) -> float:
    """
    P(gana el LOCAL de la vuelta) con la final ya en tiempos extra: marcador del tiempo extra (el, ev),
    goles que se espera que falten en lo que queda de los 30 minutos y, si sigue el empate, penales a
    50/50. Con `penales`=True ya se está en la tanda (50/50 hasta que ESPN dé el final).
    """
    if penales:
        return 0.5
    M = matriz_final(el, ev, lam_rest_l, lam_rest_v, 0.0)
    p = np.asarray(arnes.p1x2(M), float).ravel()
    return float(p[0] + 0.5 * p[1])


def fraccion_extra_restante(minuto: int | None, periodo: int) -> float:
    """Parte de los 30 minutos de tiempo extra que falta (lineal: no hay datos para una curva propia)."""
    if periodo >= 5:
        return 0.0
    if minuto is None:
        return 1.0 if periodo <= 3 else 0.5
    return float(min(1.0, max(0.0, (120 - (int(minuto) - 0.5)) / 30.0)))


# ==================================================================================================
# Datos: partidos con goles y rojas en casillas
# ==================================================================================================
def preparar(df: pd.DataFrame | None = None) -> dict:
    """
    Partidos jugados y evaluables cuyos goles con minuto suman el marcador de 90 minutos, con sus
    jugadas en casillas: `partidos` (id, torneo, orden_torneo, fecha_utc, local, visitante, gl, gv) y
    `ev` {id: [(casilla, clase, lado)]} ordenadas (clase 0 = gol, 1 = roja; lado 0 = local, 1 = visita;
    en la misma casilla el gol va antes que la roja).
    """
    df = datos.cargar() if df is None else df
    j = df[(df["estado"] == "jugado") & df["evaluable"] & (df["tiene_eventos"] == 1)]
    g = datos.tabla("goles")
    g = g[(g["periodo"] <= 2) & g["partido_id"].isin(j["id"])]
    t = datos.tabla("tarjetas")
    t = t[(t["periodo"] <= 2) & t["tipo"].isin(("roja", "segunda_amarilla")) & t["partido_id"].isin(j["id"])]
    local = dict(zip(j["id"].astype(int), j["local"]))
    ev: dict[int, list] = {int(i): [] for i in j["id"]}
    cuenta: dict[int, list] = {int(i): [0, 0] for i in j["id"]}
    for pid, p, m, a, e in zip(g["partido_id"], g["periodo"], g["minuto"], g["anadido"], g["equipo"]):
        lado = 0 if e == local[int(pid)] else 1
        ev[int(pid)].append((casilla(p, m, a), 0, lado))
        cuenta[int(pid)][lado] += 1
    for pid, p, m, a, e in zip(t["partido_id"], t["periodo"], t["minuto"], t["anadido"], t["equipo"]):
        ev[int(pid)].append((casilla(p, m, a), 1, 0 if e == local[int(pid)] else 1))
    ok = [int(i) for i, x, y in zip(j["id"], j["gl"], j["gv"]) if cuenta[int(i)] == [int(x), int(y)]]
    j = j[j["id"].isin(ok)].sort_values(["fecha_utc", "id"])
    for i in ok:
        ev[i].sort()
    cols = ["id", "torneo", "orden_torneo", "fecha_utc", "bloque", "periodo", "local", "visitante", "gl", "gv"]
    return {"partidos": j[cols].reset_index(drop=True), "ev": {i: ev[i] for i in ok}}


def curva_al_corte(prep: dict, corte=None, ventana: int = VENTANA_TORNEOS) -> Curva:
    """
    Curva con los goles de los partidos ANTERIORES a `corte` (None = todos) de los últimos `ventana`
    torneos que tengan algún partido antes del corte. Si juntan menos de MIN_GOLES_CURVA se amplía la
    ventana hacia atrás. Nunca usa un partido posterior al corte.
    """
    p = prep["partidos"]
    if corte is not None:
        p = p[p["fecha_utc"] < pd.Timestamp(corte)]
    if p.empty:
        raise ValueError("no hay partidos anteriores al corte para estimar la curva")
    ordenes = np.sort(p["orden_torneo"].unique())[::-1]
    k = min(ventana, len(ordenes))
    while True:
        sel = p[p["orden_torneo"] >= ordenes[k - 1]]
        cuenta = np.zeros(N_CASILLAS)
        for i in sel["id"]:
            for c, clase, _ in prep["ev"][int(i)]:
                if clase == 0:
                    cuenta[c] += 1
        if cuenta.sum() >= MIN_GOLES_CURVA or k >= len(ordenes):
            break
        k += 1
    if cuenta.sum() <= 0:
        raise ValueError("la ventana no tiene goles")
    meta = {"partidos": int(len(sel)), "goles": int(cuenta.sum()), "torneos": int(k),
            "desde": str(sel["fecha_utc"].min().date()), "hasta": str(sel["fecha_utc"].max().date()),
            "parte_1t": float(cuenta[:45].sum() / cuenta.sum()), "parte_agregado_1t": float(cuenta[45:INI_2T].sum() / cuenta.sum()),
            "parte_2t": float(cuenta[INI_2T:INI_2T + 45].sum() / cuenta.sum()),
            "parte_agregado_2t": float(cuenta[INI_2T + 45:].sum() / cuenta.sum())}
    return Curva(cuenta, meta)


def estado_en(eventos: list, c: int) -> tuple[int, int, int, int]:
    """(gl, gv, rojas_l, rojas_v) al completarse la casilla c."""
    s = [0, 0, 0, 0]
    for cc, clase, lado in eventos:
        if cc > c:
            break
        s[clase * 2 + lado] += 1
    return s[0], s[1], s[2], s[3]


def tabla_tramos(eventos: list, lam_l: float, lam_v: float, curva: Curva) -> dict:
    """
    Goles observados (O) y esperados sin ajustes (E = lambda x parte de la curva) de un partido,
    repartidos por el estado de cada equipo: {(estado_marcador, estado_roja): [O, E]}. La casilla de una
    jugada se carga entera al estado anterior a la jugada.
    """
    out: dict[tuple, list] = {}
    s = [0, 0, 0, 0]
    u0 = 0.0
    for c, clase, lado in list(eventos) + [(N_CASILLAS - 1, 2, -1)]:
        u1 = float(curva.acum[c])
        for k, lam in ((0, lam_l), (1, lam_v)):
            dif = (s[0] - s[1]) if k == 0 else (s[1] - s[0])
            llave = (estado_marcador(dif), estado_roja(s[2 + k], s[3 - k]))
            d = out.setdefault(llave, [0.0, 0.0])
            d[1] += lam * (u1 - u0)
            if clase == 0 and lado == k:
                d[0] += 1.0
        if clase in (0, 1):
            s[clase * 2 + lado] += 1
        u0 = u1
    return out


COLUMNAS_GLM = ("base", "pierde", "gana_1", "gana_2", "con_menos", "con_mas")


def _diseno(celdas: list[tuple], columnas: tuple) -> np.ndarray:
    X = np.zeros((len(celdas), len(columnas)))
    for i, (em, er) in enumerate(celdas):
        for k, c in enumerate(columnas):
            X[i, k] = 1.0 if c == "base" else float(c in (em, er))
    return X


def _poisson(O: np.ndarray, E: np.ndarray, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Regresión de Poisson con exposición E (Newton); devuelve coeficientes y errores estándar."""
    if X.shape[1] == 0:
        return np.zeros(0), np.zeros(0)
    b = np.zeros(X.shape[1])
    for _ in range(60):
        mu = E * np.exp(X @ b)
        H = X.T @ (mu[:, None] * X) + 1e-9 * np.eye(X.shape[1])
        paso = np.linalg.solve(H, X.T @ (O - mu))
        b += paso
        if np.abs(paso).max() < 1e-10:
            break
    mu = E * np.exp(X @ b)
    cov = np.linalg.inv(X.T @ (mu[:, None] * X) + 1e-9 * np.eye(X.shape[1]))
    return b, np.sqrt(np.diag(cov))


def ajustar_efectos(celdas: dict, umbral: float = UMBRAL_Z) -> dict:
    """
    Multiplicadores a partir de {(estado_marcador, estado_roja): [O, E]} sumadas sobre partidos:
      1) modelo completo (base + pierde + gana_1 + gana_2 + con_menos + con_mas);
      2) se conservan sólo los estados con |z| >= umbral y se reajusta con `base`;
      3) si `base` no pasa del umbral se quita (queda en 1) y se reajusta.
    Con pocos datos no pasa nada del umbral y todos los multiplicadores valen 1. Devuelve `ef` y el
    detalle (coeficiente, error estándar y z de cada paso; O y E por estado).
    """
    llaves = [k for k, v in celdas.items() if v[1] > 0]
    det = {"n_goles": float(sum(v[0] for v in celdas.values())), "esperados": float(sum(v[1] for v in celdas.values())),
           "umbral_z": umbral, "completo": {}, "final": {}, "por_estado": {}}
    ef = dict(SIN_EFECTOS)
    if not llaves or det["n_goles"] < 30:
        det["motivo"] = "sin datos suficientes: no se aplica ningún ajuste"
        return {"ef": ef, "detalle": det}
    O = np.array([celdas[k][0] for k in llaves], float)
    E = np.array([celdas[k][1] for k in llaves], float)
    for nombre, pos in (("pierde", 0), ("empata", 0), ("gana_1", 0), ("gana_2", 0), ("igual", 1), ("con_menos", 1), ("con_mas", 1)):
        m = np.array([k[pos] == nombre for k in llaves])
        if m.any() and E[m].sum() > 0:
            det["por_estado"][nombre] = {"goles": float(O[m].sum()), "esperados": float(E[m].sum()),
                                         "razon": float(O[m].sum() / E[m].sum())}
    presentes = [c for c in COLUMNAS_GLM if c == "base" or any(c in k for k in llaves)]
    b, ee = _poisson(O, E, _diseno(llaves, tuple(presentes)))
    for c, x, s in zip(presentes, b, ee):
        det["completo"][c] = {"coef": float(x), "ee": float(s), "z": float(x / s) if s > 0 else 0.0,
                              "multiplicador": float(math.exp(x))}
    elegidos = [c for c in presentes if c != "base" and abs(det["completo"][c]["z"]) >= umbral]
    cols = ["base"] + elegidos
    b, ee = _poisson(O, E, _diseno(llaves, tuple(cols)))
    if abs(b[0] / ee[0]) < umbral:
        det["base_descartada"] = {"coef": float(b[0]), "ee": float(ee[0]), "z": float(b[0] / ee[0])}
        cols = elegidos
        b, ee = _poisson(O, E, _diseno(llaves, tuple(cols)))
    for c, x, s in zip(cols, b, ee):
        ef[c] = float(math.exp(x))
        det["final"][c] = {"coef": float(x), "ee": float(s), "z": float(x / s) if s > 0 else 0.0,
                           "multiplicador": float(math.exp(x))}
    det["aplicados"] = list(cols)
    return {"ef": ef, "detalle": det}


def _sumar(a: dict, b: dict) -> dict:
    for k, v in b.items():
        d = a.setdefault(k, [0.0, 0.0])
        d[0] += v[0]; d[1] += v[1]
    return a


def _lambdas_fuera_de_muestra(nombre: str = MODELO_LAMBDAS) -> pd.DataFrame | None:
    """Lambdas previas walk-forward de DESARROLLO (None si el archivo no existe: se regenera con el arnés)."""
    try:
        if not arnes.ruta_pred(nombre).exists():
            return None
        return arnes.leer_pred(nombre).set_index("id")
    except Exception:
        return None


def celdas_por_torneo(prep: dict, pred: pd.DataFrame, ventana: int = VENTANA_TORNEOS) -> dict:
    """
    {orden_torneo: celdas} con los tramos de los partidos que tienen lambdas fuera de muestra. La
    exposición de cada partido usa la curva estimada ANTES de su torneo (sin fuga y de su época).
    """
    p = prep["partidos"]
    p = p[p["id"].isin(pred.index)]
    out = {}
    for orden, g in p.groupby("orden_torneo", sort=True):
        cur = curva_al_corte(prep, g["fecha_utc"].min(), ventana)
        acc: dict = {}
        for i in g["id"]:
            _sumar(acc, tabla_tramos(prep["ev"][int(i)], float(pred.at[i, "lam_l"]), float(pred.at[i, "lam_v"]), cur))
        out[int(orden)] = acc
    return out


def ajustar(df: pd.DataFrame | None = None, corte=None, escribir: bool = True, ruta: Path | None = None) -> Parametros:
    """
    Parámetros de PRODUCCIÓN: curva con los últimos VENTANA_TORNEOS torneos hasta `corte` (None = todo
    lo jugado) y efectos con todos los partidos de DESARROLLO que tienen lambdas fuera de muestra
    (modelo/pred/ensamble.parquet). Si ese archivo no existe se conservan los efectos del JSON guardado
    (o ninguno) y se dice en `meta`.
    """
    prep = preparar(df)
    cur = curva_al_corte(prep, corte)
    pred = _lambdas_fuera_de_muestra()
    meta = {"generado_utc": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
            "firma": firma_datos(), "modelo_lambdas": MODELO_LAMBDAS, "ventana_torneos": VENTANA_TORNEOS}
    if pred is not None:
        por_t = celdas_por_torneo(prep, pred)
        tot: dict = {}
        for c in por_t.values():
            _sumar(tot, c)
        r = ajustar_efectos(tot)
        ef, meta["efectos"] = r["ef"], r["detalle"]
        meta["efectos"]["partidos"] = int(prep["partidos"]["id"].isin(pred.index).sum())
        meta["efectos"]["torneos"] = len(por_t)
        meta["efectos"]["ee_bootstrap_torneos"] = _bootstrap_efectos(por_t, r["detalle"].get("aplicados", []))
    else:
        previo = leer_parametros(ruta, actualizar=False)
        ef = dict(previo.ef) if previo is not None else dict(SIN_EFECTOS)
        meta["efectos"] = (previo.meta.get("efectos") if previo is not None else None) or {}
        meta["aviso"] = (f"modelo/pred/{MODELO_LAMBDAS}.parquet no existe: se conservan los efectos guardados"
                         if previo is not None else f"modelo/pred/{MODELO_LAMBDAS}.parquet no existe: sin ajustes")
    par = Parametros(cur, ef, meta)
    if escribir:
        ruta = Path(ruta or RUTA_PARAMETROS)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps(par.a_json(), ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(ruta)
    return par


def _bootstrap_efectos(por_t: dict, aplicados: list, B: int = 400, semilla: int = 20261110) -> dict:
    """Error estándar de los coeficientes aplicados remuestreando TORNEOS completos (robustez del error de Poisson)."""
    cols = tuple(aplicados)
    if not cols or len(por_t) < 4:
        return {}
    ordenes = sorted(por_t)
    rng = np.random.default_rng(semilla)
    reps = []
    for _ in range(B):
        tot: dict = {}
        for o in rng.choice(ordenes, size=len(ordenes), replace=True):
            _sumar(tot, por_t[int(o)])
        llaves = [k for k, v in tot.items() if v[1] > 0]
        O = np.array([tot[k][0] for k in llaves]); E = np.array([tot[k][1] for k in llaves])
        try:
            b, _ = _poisson(O, E, _diseno(llaves, cols))
            reps.append(b)
        except np.linalg.LinAlgError:
            continue
    if len(reps) < 50:
        return {}
    ee = np.std(np.array(reps), axis=0, ddof=1)
    return {c: float(s) for c, s in zip(cols, ee)}


def firma_datos() -> str:
    """Huella de los archivos de los que salen los parámetros (para saber cuándo reajustar)."""
    partes = []
    for r in (datos.DIR_DATOS / "goles.csv", datos.DIR_DATOS / "tarjetas.csv", datos.RUTA_PARTIDOS,
              arnes.ruta_pred(MODELO_LAMBDAS)):
        try:                                                       # por contenido, no por fecha: un clon nuevo no fuerza un reajuste
            b = Path(r).read_bytes()
            partes.append(f"{Path(r).name}:{len(b)}:{hashlib.sha1(b).hexdigest()[:16]}")
        except OSError:
            partes.append(f"{Path(r).name}:no")
    return "|".join(partes)


def leer_parametros(ruta: Path | None = None, actualizar: bool = True) -> Parametros | None:
    """
    Parámetros guardados. Con `actualizar`=True los reajusta si no existen o si los datos cambiaron
    (firma distinta); si el reajuste falla se usan los guardados. Devuelve None sólo si no hay nada.
    """
    ruta = Path(ruta or RUTA_PARAMETROS)
    guardado = None
    try:
        guardado = Parametros.de_json(json.loads(ruta.read_text(encoding="utf-8")))
    except Exception:
        guardado = None
    if not actualizar:
        return guardado
    if guardado is not None and guardado.meta.get("firma") == firma_datos():
        return guardado
    try:
        return ajustar(ruta=ruta)
    except Exception as e:                                         # mejor parámetros de ayer que ninguno
        print(f"aviso: no se pudieron reajustar los parámetros en juego: {type(e).__name__}: {e}", file=sys.stderr)
        return guardado


# ==================================================================================================
# Validación sin fuga en DESARROLLO
# ==================================================================================================
def _p1x2_lote(gl, gv, lr_l, lr_v, rho: float = 0.0) -> np.ndarray:
    """P(1X2 final) de muchos partidos: marcador actual + goles restantes (matrices de arnes)."""
    R = arnes.matrices_marcadores(np.maximum(lr_l, 1e-9), np.maximum(lr_v, 1e-9), rho)
    i, j = np.indices((MAXG + 1, MAXG + 1))
    d = (np.asarray(gl) - np.asarray(gv))[:, None, None] + (i - j)[None, :, :]
    return np.stack([(R * (d > 0)).sum(axis=(1, 2)), (R * (d == 0)).sum(axis=(1, 2)), (R * (d < 0)).sum(axis=(1, 2))], axis=1)


def validar(df: pd.DataFrame | None = None, escribir: bool = True, rho_alterno: float = -0.05) -> dict:
    """
    Walk-forward por torneo en DESARROLLO (Apertura 2016 a Clausura 2025). Para cada torneo, la curva,
    los efectos y la tabla de «se queda como va» se estiman SÓLO con partidos anteriores a su primer
    partido; las lambdas previas son las fuera de muestra de modelo/pred/ensamble.parquet. En los
    minutos 15, 30, 45 (descanso), 60 y 75 se califica P(resultado final) contra:
      previo        el pronóstico previo, sin mirar el marcador;
      persistencia  «se queda como va»: frecuencia histórica del resultado final dado el resultado
                    parcial en ese minuto (ventana previa), sin mirar a los equipos;
      curva         el modelo sin ajustes (sólo fracción restante);
      marcador      curva + efecto del marcador (sin el de las rojas).
    """
    t0 = time.time()
    prep = preparar(df)
    pred = _lambdas_fuera_de_muestra()
    if pred is None:
        raise FileNotFoundError(f"falta modelo/pred/{MODELO_LAMBDAS}.parquet (lambdas fuera de muestra)")
    p = prep["partidos"]
    des = p[p["id"].isin(pred.index) & (p["periodo"] == "desarrollo")]
    por_t = celdas_por_torneo(prep, pred)
    y_final = metricas.resultado_1x2(p["gl"], p["gv"])
    res_de = dict(zip(p["id"].astype(int), y_final))
    filas = []
    historia_ef = []
    for orden, g in des.groupby("orden_torneo", sort=True):
        corte = g["fecha_utc"].min()
        cur = curva_al_corte(prep, corte)
        tot: dict = {}
        for o, c in por_t.items():
            if o < orden:
                _sumar(tot, c)
        aj = ajustar_efectos(tot)
        ef = aj["ef"]
        ef_m = {**ef, "con_menos": 1.0, "con_mas": 1.0}
        if ef["con_menos"] != 1.0 or ef["con_mas"] != 1.0:        # sin rojas hay que reajustar base y marcador
            sin = {}
            for (em, _), v in tot.items():
                d = sin.setdefault((em, "igual"), [0.0, 0.0]); d[0] += v[0]; d[1] += v[1]
            ef_m = ajustar_efectos(sin)["ef"]
        historia_ef.append({"torneo": str(g["torneo"].iloc[0]), "goles_previos": aj["detalle"]["n_goles"],
                            "aplicados": aj["detalle"].get("aplicados", []),
                            "efectos": {k: round(v, 4) for k, v in ef.items()}})
        # «se queda como va»: frecuencias de la misma ventana que la curva
        previos = p[p["fecha_utc"] < corte]
        ordenes = np.sort(previos["orden_torneo"].unique())[::-1][:VENTANA_TORNEOS]
        vent = previos[previos["orden_torneo"].isin(ordenes)]
        frec = {}
        for m in MINUTOS_VALIDACION:
            T = np.ones((3, 3))                                   # suavizado de Laplace
            c = casilla_de_minuto(m)
            for i in vent["id"]:
                a, b, _, _ = estado_en(prep["ev"][int(i)], c)
                T[0 if a > b else 1 if a == b else 2, res_de[int(i)]] += 1
            frec[m] = T / T.sum(axis=1, keepdims=True)
        for i in g["id"]:
            i = int(i)
            r = pred.loc[i]
            for m in MINUTOS_VALIDACION:
                c = casilla_de_minuto(m)
                a, b, ra, rb = estado_en(prep["ev"][i], c)
                fr = cur.tras(c)
                fila = {"id": i, "torneo": r["torneo"], "bloque": r["bloque"], "minuto": m, "gl": a, "gv": b,
                        "rojas_l": ra, "rojas_v": rb, "fr": fr, "y": int(res_de[i]),
                        "lam_l": float(r["lam_l"]), "lam_v": float(r["lam_v"]),
                        "rest_obs": float(r["gl"] + r["gv"] - a - b)}
                for nombre, e in (("modelo", ef), ("curva", SIN_EFECTOS), ("marcador", ef_m)):
                    fila[f"ll_{nombre}"] = fila["lam_l"] * fr * multiplicador(e, a - b, ra, rb)
                    fila[f"lv_{nombre}"] = fila["lam_v"] * fr * multiplicador(e, b - a, rb, ra)
                fila.update({"pre_l": float(r["p_l"]), "pre_e": float(r["p_e"]), "pre_v": float(r["p_v"])})
                q = frec[m][0 if a > b else 1 if a == b else 2]
                fila.update({"per_l": float(q[0]), "per_e": float(q[1]), "per_v": float(q[2])})
                filas.append(fila)
    D = pd.DataFrame(filas)
    P = {}
    for nombre in ("modelo", "curva", "marcador"):
        P[nombre] = _p1x2_lote(D["gl"].to_numpy(), D["gv"].to_numpy(), D[f"ll_{nombre}"].to_numpy(), D[f"lv_{nombre}"].to_numpy())
    P["modelo_rho"] = _p1x2_lote(D["gl"].to_numpy(), D["gv"].to_numpy(), D["ll_modelo"].to_numpy(), D["lv_modelo"].to_numpy(), rho_alterno)
    P["previo"] = D[["pre_l", "pre_e", "pre_v"]].to_numpy()
    P["previo"] = P["previo"] / P["previo"].sum(axis=1, keepdims=True)
    P["persistencia"] = D[["per_l", "per_e", "per_v"]].to_numpy()
    y = D["y"].to_numpy()
    bl = D["bloque"].to_numpy()
    LL = {k: metricas.logloss_1x2(v, y) for k, v in P.items()}
    BR = {k: metricas.brier_1x2(v, y) for k, v in P.items()}
    estado_ahora = np.where(D["gl"] > D["gv"], 0, np.where(D["gl"] == D["gv"], 1, 2))
    out = {"generado_utc": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"), "modelo_lambdas": MODELO_LAMBDAS,
           "partidos": int(D["id"].nunique()), "torneos": int(D["torneo"].nunique()), "rho_alterno": rho_alterno,
           "ventana_torneos": VENTANA_TORNEOS, "umbral_z": UMBRAL_Z, "efectos_por_torneo": historia_ef, "por_minuto": {}}

    def r4(d):
        return {k: (round(float(v), 4) if isinstance(v, (float, np.floating)) and np.isfinite(v) else (None if isinstance(v, (float, np.floating)) else v))
                for k, v in d.items()}

    for m in MINUTOS_VALIDACION:
        s = (D["minuto"] == m).to_numpy()
        d = {"n": int(s.sum()), "fraccion_restante_media": round(float(D.loc[s, "fr"].mean()), 4), "logloss": {}, "brier": {},
             "acierto": {}, "contra": {}}
        for k in P:
            d["logloss"][k] = r4(metricas.bootstrap_bloques(LL[k][s], bl[s]))
            d["brier"][k] = round(float(BR[k][s].mean()), 4)
            d["acierto"][k] = round(float((np.argmax(np.round(P[k][s], 10), axis=1) == y[s]).mean()), 4)
        d["acierto"]["se_queda_como_va"] = round(float((estado_ahora[s] == y[s]).mean()), 4)
        for ref in ("previo", "persistencia", "curva", "marcador", "modelo_rho"):
            d["contra"][ref] = r4(metricas.diferencia_pareada(LL["modelo"][s], LL[ref][s], bl[s]))
        cal = metricas.calibracion_deciles(P["modelo"][s], y[s])
        d["calibracion"] = [{"p_media": round(float(a), 4), "frec_obs": round(float(b), 4), "n": int(n)}
                            for a, b, n in zip(cal["p_media"], cal["frec_obs"], cal["n"])]
        d["error_calibracion"] = round(metricas.error_calibracion(P["modelo"][s], y[s]), 4)
        d["pendiente_calibracion"] = round(metricas.pendiente_calibracion(P["modelo"][s], y[s]), 3)
        # goles que faltaban: esperados por el modelo contra observados
        esp = (D.loc[s, "ll_modelo"] + D.loc[s, "lv_modelo"]).to_numpy()
        d["goles_restantes"] = {"esperados_modelo": round(float(esp.mean()), 4),
                                "esperados_curva": round(float((D.loc[s, "ll_curva"] + D.loc[s, "lv_curva"]).mean()), 4),
                                "observados": r4(metricas.bootstrap_bloques(D.loc[s, "rest_obs"].to_numpy(), bl[s]))}
        # sólo los partidos con alguna expulsión antes de ese minuto y con hombres disparejos
        rj = s & (D["rojas_l"] != D["rojas_v"]).to_numpy()
        if rj.sum() >= 20:
            d["con_expulsion"] = {"n": int(rj.sum()),
                                  "logloss_modelo": round(float(LL["modelo"][rj].mean()), 4),
                                  "logloss_marcador": round(float(LL["marcador"][rj].mean()), 4),
                                  "logloss_curva": round(float(LL["curva"][rj].mean()), 4),
                                  "modelo_menos_marcador": r4(metricas.diferencia_pareada(LL["modelo"][rj], LL["marcador"][rj], bl[rj]))}
        out["por_minuto"][str(m)] = d
    out["todos_los_minutos"] = {ref: r4(metricas.diferencia_pareada(LL["modelo"], LL[ref], bl))
                                for ref in ("previo", "persistencia", "curva", "marcador", "modelo_rho")}
    out["segundos"] = round(time.time() - t0, 1)
    if escribir:
        RUTA_VALIDACION.parent.mkdir(parents=True, exist_ok=True)
        RUTA_VALIDACION.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def _imprimir_validacion(v: dict) -> None:
    print(f"validación en juego · {v['partidos']} partidos de DESARROLLO · lambdas de {v['modelo_lambdas']}")
    print("min   n     modelo   previo   persist  curva    | mod-previo (ee)     mod-persist (ee)    mod-curva (ee)     ECE")
    for m, d in v["por_minuto"].items():
        ll, c = d["logloss"], d["contra"]
        print(f"{m:>3s}  {d['n']:5d}  {ll['modelo']['media']:.4f}  {ll['previo']['media']:.4f}  {ll['persistencia']['media']:.4f}  "
              f"{ll['curva']['media']:.4f}   | {c['previo']['dif']:+.4f} ({c['previo']['ee']:.4f})   "
              f"{c['persistencia']['dif']:+.4f} ({c['persistencia']['ee']:.4f})   {c['curva']['dif']:+.4f} ({c['curva']['ee']:.4f})   "
              f"{d['error_calibracion']:.4f}")


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Modelo en juego de la Liga MX")
    ap.add_argument("cmd", choices=("ajustar", "validar", "curva"))
    a = ap.parse_args(argv)
    if a.cmd == "ajustar":
        par = ajustar()
        print(json.dumps({"curva": par.curva.meta, "efectos": par.ef,
                          "aplicados": (par.meta.get("efectos") or {}).get("aplicados")}, ensure_ascii=False, indent=1))
    elif a.cmd == "validar":
        _imprimir_validacion(validar())
    else:
        par = leer_parametros()
        for d in par.curva.por_minuto():
            print(f"{d['minuto']:>9s}  {d['restante']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
