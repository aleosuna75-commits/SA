# -*- coding: utf-8 -*-
"""
================================================================================
  PROYECCIÓN DE CAMPEÓN — Apertura 2026
================================================================================
Simula lo que falta del torneo (fase regular + liguilla) y devuelve la
probabilidad de cada equipo de terminar campeón, de clasificar y de ser líder.

QUÉ SE SABE Y QUÉ SE ASUME
--------------------------
El calendario oficial (PDF de Liga MX) publica sede y horario de las 17
jornadas, pero los EMPAREJAMIENTOS de la J11 en adelante no son públicos todavía.
Sin embargo, el torneo es round-robin simple: 18 equipos, 17 jornadas, cada par
se enfrenta exactamente una vez. Por lo tanto:

  * El CONJUNTO de partidos que faltan está totalmente determinado: son las 63
    parejas que aún no se han enfrentado. No se asume nada.
  * Cuántos partidos de LOCAL le quedan a cada equipo también está determinado:
    sale de contar sedes en el PDF oficial. Suma 153 exacto, que es el total de
    partidos del torneo.
  * Lo único que NO se conoce es qué equipo es local en cada pareja concreta.

En vez de inventar una asignación, se INTEGRA sobre ella: en cada simulación se
sortea una orientación válida (una que respeta el número de localías de cada
equipo). Así la incertidumbre del calendario queda incorporada al resultado en
lugar de escondida en un supuesto.

LIGUILLA
--------
Clasifican los 8 primeros, sin play-in (formato Apertura 2026). Cuartos 1-8,
2-7, 3-6, 4-5 a doble partido; el mejor sembrado avanza si el global empata.
Semifinales resembradas. En la final el empate se resuelve por penales (50/50).
================================================================================
"""
import math
import random
from collections import defaultdict

import numpy as np

import cerebro_ligamx_2026 as C

PUNTOS_V, PUNTOS_E = 3, 1
CLASIFICAN = 8


def orientacion_valida(parejas, locales_restantes, rng):
    """
    Asigna local/visitante a cada pareja restante respetando EXACTAMENTE cuántos
    partidos de local le faltan a cada equipo (dato del calendario oficial).

    Es un problema de asignación con cupos, no algo que resuelva un greedy: hay
    que poder deshacer decisiones. Se usa el método de caminos aumentantes de
    Kuhn — como cada pareja tiene sólo dos candidatos posibles (sus dos equipos),
    "reubicar" una pareja ya asignada significa mandarla a su otro equipo, y la
    recursión es directa.

    El orden de las parejas y de los candidatos se sortea, así que llamadas
    sucesivas devuelven orientaciones válidas distintas.
    """
    cupo = dict(locales_restantes)
    if sum(cupo.values()) != len(parejas):
        raise ValueError(f"las localías ({sum(cupo.values())}) no cuadran con "
                         f"los partidos restantes ({len(parejas)})")

    asignado = {}                      # índice de pareja -> equipo local
    carga = {e: 0 for e in cupo}
    en_equipo = {e: set() for e in cupo}

    def colocar(i, visitados):
        a, b = parejas[i]
        cand = [a, b]
        rng.shuffle(cand)
        for t in cand:
            if t in visitados:
                continue
            visitados.add(t)
            if carga[t] < cupo[t]:
                asignado[i] = t; carga[t] += 1; en_equipo[t].add(i)
                return True
            # t está lleno: intenta mandar a otro lado alguna pareja suya
            for j in list(en_equipo[t]):
                otro = parejas[j][0] if parejas[j][1] == t else parejas[j][1]
                if otro in visitados:
                    continue
                en_equipo[t].discard(j); carga[t] -= 1
                if colocar(j, visitados):
                    asignado[i] = t; carga[t] += 1; en_equipo[t].add(i)
                    return True
                en_equipo[t].add(j); carga[t] += 1; asignado[j] = t
        return False

    orden = list(range(len(parejas)))
    rng.shuffle(orden)
    for i in orden:
        if not colocar(i, set()):
            raise RuntimeError("el calendario restante no admite una orientación "
                               "compatible con las localías oficiales")

    return [(asignado[i], parejas[i][0] if parejas[i][1] == asignado[i] else parejas[i][1])
            for i in range(len(parejas))]


def tabla_inicial(jugados):
    """Puntos, diferencia y goles a favor con los partidos ya jugados."""
    t = defaultdict(lambda: {"pts": 0, "gf": 0, "gc": 0, "pj": 0})
    for local, visitante, gl, gv in jugados:
        for e in (local, visitante):
            t[e]["pj"] += 1
        t[local]["gf"] += gl; t[local]["gc"] += gv
        t[visitante]["gf"] += gv; t[visitante]["gc"] += gl
        if gl > gv:
            t[local]["pts"] += PUNTOS_V
        elif gl < gv:
            t[visitante]["pts"] += PUNTOS_V
        else:
            t[local]["pts"] += PUNTOS_E; t[visitante]["pts"] += PUNTOS_E
    return t


class Sorteador:
    """
    Muestreador de marcadores. Precalcula la acumulada de cada matriz para
    sortear con una búsqueda binaria en vez de recorrer 121 pesos por partido:
    con 20,000 simulaciones × 77 partidos eso es la diferencia entre minutos y
    segundos.
    """

    def __init__(self, ratings, equipos):
        self.ancho = {}
        self.acum = {}
        for loc in equipos:
            for vis in equipos:
                if loc == vis:
                    continue
                lam_l, lam_v, _ = C.lambdas_partido(loc, vis, ratings, jornada_actual=False)
                M = C.matriz_marcadores(lam_l, lam_v)
                self.acum[(loc, vis)] = np.cumsum(M.ravel())
                self.ancho[(loc, vis)] = M.shape[1]

    def marcador(self, loc, vis, u):
        a = self.acum[(loc, vis)]
        i = int(np.searchsorted(a, u * a[-1]))
        return divmod(i, self.ancho[(loc, vis)])


def simular(equipos, jugados, parejas_restantes, locales_restantes, ratings,
            n_sims=20000, semilla=20260814, n_calendarios=200):
    """Devuelve probabilidades de campeón, clasificación y liderato."""
    rng = random.Random(semilla)
    sorteo = Sorteador(ratings, equipos)

    # Resolver la orientación es caro; se precalcula un repertorio de calendarios
    # válidos y cada simulación toma uno. Así la incertidumbre de qué equipo es
    # local en cada pareja queda integrada en el resultado.
    repertorio = [orientacion_valida(parejas_restantes, locales_restantes, rng)
                  for _ in range(n_calendarios)]

    base = tabla_inicial(jugados)
    campeon = defaultdict(int); clasifica = defaultdict(int)
    lider = defaultdict(int); finalista = defaultdict(int)
    pts_acum = defaultdict(float)

    for _ in range(n_sims):
        t = {e: dict(base[e]) if e in base else {"pts": 0, "gf": 0, "gc": 0, "pj": 0}
             for e in equipos}
        for loc, vis in repertorio[rng.randrange(len(repertorio))]:
            gl, gv = sorteo.marcador(loc, vis, rng.random())
            t[loc]["gf"] += gl; t[loc]["gc"] += gv
            t[vis]["gf"] += gv; t[vis]["gc"] += gl
            if gl > gv:
                t[loc]["pts"] += PUNTOS_V
            elif gl < gv:
                t[vis]["pts"] += PUNTOS_V
            else:
                t[loc]["pts"] += PUNTOS_E; t[vis]["pts"] += PUNTOS_E

        orden = sorted(equipos, key=lambda e: (t[e]["pts"], t[e]["gf"] - t[e]["gc"],
                                               t[e]["gf"], rng.random()), reverse=True)
        for e in equipos:
            pts_acum[e] += t[e]["pts"]
        lider[orden[0]] += 1
        for e in orden[:CLASIFICAN]:
            clasifica[e] += 1

        # --- liguilla: siembra 1..8 ---
        siembra = {e: i + 1 for i, e in enumerate(orden[:CLASIFICAN])}
        vivos = orden[:CLASIFICAN]

        def serie(alto, bajo):
            """Doble partido (ida en casa del peor sembrado); si el global
            empata, avanza el mejor sembrado."""
            ida = sorteo.marcador(bajo, alto, rng.random())
            vuelta = sorteo.marcador(alto, bajo, rng.random())
            return alto if (ida[1] + vuelta[0]) >= (ida[0] + vuelta[1]) else bajo

        ronda = [(vivos[0], vivos[7]), (vivos[1], vivos[6]),
                 (vivos[2], vivos[5]), (vivos[3], vivos[4])]
        semis = [serie(a, b) for a, b in ronda]
        semis.sort(key=lambda e: siembra[e])
        f1 = serie(semis[0], semis[3])
        f2 = serie(semis[1], semis[2])
        for e in (f1, f2):
            finalista[e] += 1
        finalistas = sorted([f1, f2], key=lambda e: siembra[e])
        # final: la ida en casa del peor sembrado; el empate global va a penales (50/50)
        ida = sorteo.marcador(finalistas[1], finalistas[0], rng.random())
        vuelta = sorteo.marcador(finalistas[0], finalistas[1], rng.random())
        a = ida[1] + vuelta[0]
        b = ida[0] + vuelta[1]
        campeon[finalistas[0] if (a > b or (a == b and rng.random() < .5)) else finalistas[1]] += 1

    return [{"equipo": e,
             "campeon": round(campeon[e] / n_sims, 4),
             "finalista": round(finalista[e] / n_sims, 4),
             "clasifica": round(clasifica[e] / n_sims, 4),
             "lider": round(lider[e] / n_sims, 4),
             "puntos_esperados": round(pts_acum[e] / n_sims, 1),
             "pts_actuales": base[e]["pts"] if e in base else 0,
             "pj": base[e]["pj"] if e in base else 0}
            for e in sorted(equipos, key=lambda x: -campeon[x])]
