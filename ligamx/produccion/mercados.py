# -*- coding: utf-8 -*-
"""
Motor de mercados de un partido a partir de (lam_l, lam_v, rho).

1. Matriz de marcadores M (11 x 11, la de modelo/arnes.py: Poisson + Dixon-Coles, renormalizada).
2. Distribución conjunta EXACTA por mitades J[h1, a1, h2, a2] por adelgazamiento de Poisson: cada gol
   del local cae en el primer tiempo con probabilidad p1_l (p1_v para la visita), independiente de los
   demás. Dado el marcador final (x, y), los goles del primer tiempo son Binomial(x, p1_l) y
   Binomial(y, p1_v), así que
        J[h1, a1, h2, a2] = M[h1+h2, a1+a2] · Bin(h1; h1+h2, p1_l) · Bin(a1; a1+a2, p1_v).
   Es la misma construcción del motor previo (_joint_mitades: Poisson por mitad, corrección
   Dixon-Coles sobre el marcador FINAL y renormalización), pero escrita desde M: la marginal de
   tiempo completo de J es M exactamente, sin masa perdida por truncar cada mitad.
   p1_l y p1_v se estiman de goles.csv sólo con partidos anteriores al corte (últimos ~6 años).
3. Catálogo de mercados: cada uno es una máscara booleana sobre las celdas de J (o una región de M en
   los marcadores exactos), con clave, etiqueta, familia, tipo y probabilidad.

Las celdas con masa son las 4,356 combinaciones (x, y, h1, a1) con h1 <= x <= 10 y a1 <= y <= 10; todo
el módulo trabaja con el vector `q` de esas celdas (o una matriz, un renglón por partido).

Línea de comandos (desde ligamx/):  python3 -m produccion.mercados validar
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd

from modelo import arnes, datos, metricas

MAXG = arnes.MAX_GOLES                                   # 10
N = MAXG + 1
ANIOS_P1 = 6.0                                           # ventana para la proporción de goles del 1T

# --- celdas (x, y, h1, a1) con masa ----------------------------------------------------------------
_cel = np.array([(x, y, h1, a1) for x in range(N) for y in range(N)
                 for h1 in range(x + 1) for a1 in range(y + 1)], dtype=np.int64)
X, Y, H1, A1 = _cel[:, 0], _cel[:, 1], _cel[:, 2], _cel[:, 3]   # final local, final visita, 1T local, 1T visita
H2, A2 = X - H1, Y - A1                                         # goles del segundo tiempo
N_CELDAS = len(_cel)                                            # 4,356
_COMB_L = np.array([math.comb(int(x), int(h)) for x, h in zip(X, H1)], dtype=float)
_COMB_V = np.array([math.comb(int(y), int(a)) for y, a in zip(Y, A1)], dtype=float)
_IDX_XY = X * N + Y


# ==================================================================================================
# Conjunta por mitades
# ==================================================================================================
def celdas(M, p1_l, p1_v) -> np.ndarray:
    """
    Vector(es) q de probabilidad de las celdas (x, y, h1, a1) a partir de M (11x11 o n x 11 x 11) y
    de la proporción de goles en el primer tiempo del local y de la visita (escalares o por partido).
    """
    M = np.asarray(M, float)
    uno = M.ndim == 2
    M = M[None] if uno else M
    pl = np.atleast_1d(np.asarray(p1_l, float))[:, None]
    pv = np.atleast_1d(np.asarray(p1_v, float))[:, None]
    if ((pl <= 0) | (pl >= 1) | (pv <= 0) | (pv >= 1)).any():
        raise ValueError("p1_l y p1_v deben estar en (0, 1)")
    q = (M[:, X, Y] * _COMB_L * pl ** H1 * (1.0 - pl) ** H2 * _COMB_V * pv ** A1 * (1.0 - pv) ** A2)
    return q[0] if uno else q


def tensor(q) -> np.ndarray:
    """J[h1, a1, h2, a2] (11 x 11 x 11 x 11) a partir del vector de celdas de UN partido."""
    J = np.zeros((N, N, N, N))
    J[H1, A1, H2, A2] = np.asarray(q, float)
    return J


def celdas_de_tensor(J) -> np.ndarray:
    """Inversa de `tensor`."""
    return np.asarray(J, float)[H1, A1, H2, A2]


def marginal_final(q) -> np.ndarray:
    """Matriz 11x11 del marcador final que resulta de sumar las mitades (debe coincidir con M)."""
    return np.bincount(_IDX_XY, weights=np.asarray(q, float), minlength=N * N).reshape(N, N)


def conjunta_mitades(lam_l: float, lam_v: float, rho: float = 0.0, p1_l: float | None = None,
                     p1_v: float | None = None) -> np.ndarray:
    """J[h1, a1, h2, a2] de un partido. Sin p1_* usa la proporción estimada a la fecha (proporcion_1t)."""
    if p1_l is None or p1_v is None:
        p1_l, p1_v = proporcion_1t()[:2]
    return tensor(celdas(arnes.matriz_marcadores(lam_l, lam_v, rho), p1_l, p1_v))


# ==================================================================================================
# Proporción de goles del primer tiempo (sólo con el pasado)
# ==================================================================================================
_cache_conteos: dict = {}


def _conteos_mitades(partidos: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Por partido evaluable con goles con minuto completos (tiene_eventos = 1): goles del local y de la
    visita en el primer tiempo y en los 90 minutos (periodos 1 y 2 de goles.csv), en orden de fecha.
    """
    df = datos.cargar() if partidos is None else partidos
    llave = (len(df), int(df["id"].sum()), int((df["estado"] == "jugado").sum()))
    if llave in _cache_conteos:
        return _cache_conteos[llave]
    j = df[df["evaluable"] & (df["tiene_eventos"] == 1)][["id", "fecha_utc", "local", "visitante"]]
    g = datos.tabla("goles", j)
    g = g[g["periodo"].isin([1, 2])].merge(j, left_on="partido_id", right_on="id", how="inner")
    es_l = (g["equipo"] == g["local"]).to_numpy()
    es_v = (g["equipo"] == g["visitante"]).to_numpy()
    p1 = (g["periodo"] == 1).to_numpy()
    c = pd.DataFrame({"id": g["id"].to_numpy(), "g1_l": es_l & p1, "g_l": es_l, "g1_v": es_v & p1, "g_v": es_v})
    c = c.groupby("id").sum()
    t = j.set_index("id").join(c).fillna({"g1_l": 0, "g_l": 0, "g1_v": 0, "g_v": 0})
    t = t.sort_values("fecha_utc", kind="mergesort").reset_index()
    _cache_conteos.clear()
    _cache_conteos[llave] = t
    return t


def proporciones_1t_cortes(cortes, anios: float = ANIOS_P1, partidos: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Para cada corte: p1_l y p1_v = goles del primer tiempo / goles totales (local y visita) en los
    partidos con fecha_utc en [corte - anios, corte). Columnas: p1_l, p1_v, n (partidos usados).
    """
    t = _conteos_mitades(partidos)
    f = pd.DatetimeIndex(t["fecha_utc"]).as_unit("ns").asi8
    cs = np.vstack([np.zeros(4), np.cumsum(t[["g1_l", "g_l", "g1_v", "g_v"]].to_numpy(float), axis=0)])
    cortes = pd.DatetimeIndex(pd.to_datetime(np.atleast_1d(cortes), utc=True))
    c_ns = cortes.as_unit("ns").asi8
    hi = np.searchsorted(f, c_ns, side="left")                       # estrictamente antes del corte
    lo = np.searchsorted(f, c_ns - int(anios * 365.25 * 86400 * 1e9), side="left")
    s = cs[hi] - cs[lo]
    with np.errstate(invalid="ignore", divide="ignore"):
        out = pd.DataFrame({"p1_l": s[:, 0] / s[:, 1], "p1_v": s[:, 2] / s[:, 3], "n": hi - lo}, index=cortes)
    return out


def proporcion_1t(corte=None, anios: float = ANIOS_P1, partidos: pd.DataFrame | None = None) -> tuple[float, float, int]:
    """(p1_l, p1_v, n_partidos) con los partidos anteriores a `corte` (por omisión, ahora)."""
    corte = pd.Timestamp.now(tz="UTC") if corte is None else pd.Timestamp(corte)
    r = proporciones_1t_cortes([corte], anios, partidos).iloc[0]
    if not (r["n"] > 0 and np.isfinite(r["p1_l"]) and np.isfinite(r["p1_v"])):
        raise ValueError("no hay goles con minuto antes del corte para estimar el reparto por mitades")
    return float(r["p1_l"]), float(r["p1_v"]), int(r["n"])


# ==================================================================================================
# Catálogo de mercados
# ==================================================================================================
@dataclass(frozen=True)
class Mercado:
    """
    Un mercado = un suceso sobre las celdas (x, y, h1, a1).
      clave     identificador estable.          etiqueta  texto con {L} y {V} (nombres de los equipos).
      tipo      nombre del mercado como se muestra (Resultado, Doble oportunidad, Total de goles...).
      familia   grupo de mercados que hablan de lo mismo: la combinada toma a lo más uno por familia.
      mascara   celdas donde el pick gana.      nula  celdas donde la apuesta se devuelve (o None).
    Un mercado con `nula` no es un suceso binario: su probabilidad es P(gana | no nula) y no entra a
    la combinada exacta.
    """
    clave: str
    etiqueta: str
    familia: str
    tipo: str
    mascara: np.ndarray
    nula: np.ndarray | None = None

    @property
    def combinable(self) -> bool:
        return self.nula is None


def _construir_catalogo() -> list[Mercado]:
    T, T1, T2, D, D1, D2 = X + Y, H1 + A1, H2 + A2, X - Y, H1 - A1, H2 - A2
    c: list[Mercado] = []

    def m(clave, etiqueta, familia, tipo, mascara, nula=None):
        c.append(Mercado(clave, etiqueta, familia, tipo, np.asarray(mascara, bool),
                         None if nula is None else np.asarray(nula, bool)))

    # resultado final
    m("1", "Gana {L}", "resultado", "Resultado", D > 0)
    m("X", "Empate", "resultado", "Resultado", D == 0)
    m("2", "Gana {V}", "resultado", "Resultado", D < 0)
    m("1X", "{L} o empate", "resultado", "Doble oportunidad", D >= 0)
    m("X2", "{V} o empate", "resultado", "Doble oportunidad", D <= 0)
    m("12", "No hay empate", "resultado", "Doble oportunidad", D != 0)
    m("SE_1", "{L}, sin empate (se devuelve si empatan)", "resultado", "Sin empate", D > 0, D == 0)
    m("SE_2", "{V}, sin empate (se devuelve si empatan)", "resultado", "Sin empate", D < 0, D == 0)
    m("H_L-1.5", "{L} gana por 2 o más goles (hándicap -1.5)", "resultado", "Hándicap", D >= 2)
    m("H_V+1.5", "{V} gana, empata o pierde por un gol (hándicap +1.5)", "resultado", "Hándicap", D <= 1)
    m("H_V-1.5", "{V} gana por 2 o más goles (hándicap -1.5)", "resultado", "Hándicap", D <= -2)
    m("H_L+1.5", "{L} gana, empata o pierde por un gol (hándicap +1.5)", "resultado", "Hándicap", D >= -1)
    m("HA_L-1", "{L} -1 asiático (se devuelve si gana por uno)", "resultado", "Hándicap", D >= 2, D == 1)
    m("HA_V+1", "{V} +1 asiático (se devuelve si pierde por uno)", "resultado", "Hándicap", D <= 0, D == 1)
    # totales
    for linea in (1.5, 2.5, 3.5):
        s = str(linea).replace(".", "")
        m(f"O{s}", f"Más de {linea} goles", "total", "Total de goles", T > linea)
        m(f"U{s}", f"Menos de {linea} goles", "total", "Total de goles", T < linea)
    m("AA_SI", "Ambos anotan", "ambos", "Ambos anotan", (X > 0) & (Y > 0))
    m("AA_NO", "Al menos uno no anota", "ambos", "Ambos anotan", (X == 0) | (Y == 0))
    # por equipo (la portería en cero de un equipo es el complemento de que anote el rival)
    m("L_ANOTA", "{L} anota", "goles_local", "Total de {L}", X >= 1)
    m("L_2MAS", "{L} anota 2 o más", "goles_local", "Total de {L}", X >= 2)
    m("L_U15", "{L} anota menos de 1.5", "goles_local", "Total de {L}", X <= 1)
    m("PC_V", "{V} deja su portería en cero", "goles_local", "Portería en cero", X == 0)
    m("V_ANOTA", "{V} anota", "goles_visita", "Total de {V}", Y >= 1)
    m("V_2MAS", "{V} anota 2 o más", "goles_visita", "Total de {V}", Y >= 2)
    m("V_U15", "{V} anota menos de 1.5", "goles_visita", "Total de {V}", Y <= 1)
    m("PC_L", "{L} deja su portería en cero", "goles_visita", "Portería en cero", Y == 0)
    # descanso
    m("D_1", "{L} gana al descanso", "descanso", "Resultado al descanso", D1 > 0)
    m("D_X", "Empate al descanso", "descanso", "Resultado al descanso", D1 == 0)
    m("D_2", "{V} gana al descanso", "descanso", "Resultado al descanso", D1 < 0)
    m("D_1X", "{L} o empate al descanso", "descanso", "Doble oportunidad al descanso", D1 >= 0)
    m("D_X2", "{V} o empate al descanso", "descanso", "Doble oportunidad al descanso", D1 <= 0)
    m("D_12", "No hay empate al descanso", "descanso", "Doble oportunidad al descanso", D1 != 0)
    # goles por mitad
    m("G1T_SI", "Hay gol en el primer tiempo", "goles_1t", "Gol en el primer tiempo", T1 >= 1)
    m("G1T_NO", "Sin goles en el primer tiempo", "goles_1t", "Gol en el primer tiempo", T1 == 0)
    m("O15_1T", "Más de 1.5 goles en el primer tiempo", "goles_1t", "Total del primer tiempo", T1 >= 2)
    m("U15_1T", "Menos de 1.5 goles en el primer tiempo", "goles_1t", "Total del primer tiempo", T1 <= 1)
    m("G2T_SI", "Hay gol en el segundo tiempo", "goles_2t", "Gol en el segundo tiempo", T2 >= 1)
    m("G2T_NO", "Sin goles en el segundo tiempo", "goles_2t", "Gol en el segundo tiempo", T2 == 0)
    m("MAS_1T", "Más goles en el primer tiempo que en el segundo", "mitades", "Mitad con más goles", T1 > T2)
    m("MAS_2T", "Más goles en el segundo tiempo que en el primero", "mitades", "Mitad con más goles", T2 > T1)
    m("MIT_IGUAL", "Mismos goles en las dos mitades", "mitades", "Mitad con más goles", T1 == T2)
    m("GM_L", "{L} gana alguna mitad", "gana_mitad", "Gana alguna mitad", (D1 > 0) | (D2 > 0))
    m("GM_V", "{V} gana alguna mitad", "gana_mitad", "Gana alguna mitad", (D1 < 0) | (D2 < 0))
    # descanso / final
    nom = {1: "{L}", 0: "empate", -1: "{V}"}
    cod = {1: "1", 0: "X", -1: "2"}
    for a in (1, 0, -1):
        for b in (1, 0, -1):
            m(f"DF_{cod[a]}/{cod[b]}", f"Descanso/final: {nom[a]} / {nom[b]}", "descanso_final",
              "Descanso/final", (np.sign(D1) == a) & (np.sign(D) == b))
    claves = [x.clave for x in c]
    if len(set(claves)) != len(claves):
        raise AssertionError("claves de mercado repetidas")
    return c


@lru_cache(maxsize=1)
def catalogo() -> tuple[Mercado, ...]:
    """Catálogo fijo (no depende del partido). Los marcadores exactos se agregan por partido."""
    return tuple(_construir_catalogo())


@lru_cache(maxsize=1)
def _matrices() -> tuple[np.ndarray, np.ndarray]:
    """(máscaras de gana, máscaras de nula) como matrices float (K, N_CELDAS) del catálogo fijo."""
    cat = catalogo()
    G = np.array([x.mascara for x in cat], dtype=float)
    Z = np.array([x.nula if x.nula is not None else np.zeros(N_CELDAS, bool) for x in cat], dtype=float)
    return G, Z


def claves() -> list[str]:
    return [x.clave for x in catalogo()]


def probabilidades(q) -> np.ndarray:
    """
    Probabilidad de cada mercado del catálogo fijo: (K,) para un partido o (n, K) para varios.
    En los mercados con devolución es P(gana | no hay devolución).
    """
    G, Z = _matrices()
    q = np.asarray(q, float)
    p, z = q @ G.T, q @ Z.T
    return p / (1.0 - z)


def etiqueta(m: Mercado, local: str = "Local", visitante: str = "Visita") -> str:
    return m.etiqueta.format(L=local, V=visitante)


def mercados_partido(lam_l: float, lam_v: float, rho: float = 0.0, p1_l: float | None = None,
                     p1_v: float | None = None, local: str = "Local", visitante: str = "Visita",
                     top: int = 5) -> dict:
    """
    Todo lo de un partido: {"lam_l", "lam_v", "rho", "p1_l", "p1_v", "M", "q", "mercados", "marcadores"}.
    `mercados` es una lista de dicts {clave, etiqueta, familia, tipo, prob, momio_justo, combinable,
    p_nula} (catálogo fijo y, al final, los `top` marcadores exactos más probables, familia "marcador").
    """
    if p1_l is None or p1_v is None:
        p1_l, p1_v = proporcion_1t()[:2]
    M = arnes.matriz_marcadores(lam_l, lam_v, rho)
    q = celdas(M, p1_l, p1_v)
    G, Z = _matrices()
    pz = q @ Z.T
    pr = (q @ G.T) / (1.0 - pz)
    lista = []
    for mk, p, z in zip(catalogo(), pr, pz):
        lista.append({"clave": mk.clave, "etiqueta": etiqueta(mk, local, visitante), "familia": mk.familia,
                      "tipo": mk.tipo.format(L=local, V=visitante), "prob": float(p),
                      "momio_justo": float(1.0 / p) if p > 0 else math.inf,
                      "combinable": mk.combinable, "p_nula": float(z)})
    marcadores = []
    for x, y, p in arnes.top_marcadores(M, top):
        marcadores.append({"clave": f"ME_{x}-{y}", "etiqueta": f"Marcador exacto {local} {x}-{y} {visitante}",
                           "familia": "marcador", "tipo": "Marcador exacto", "prob": float(p),
                           "momio_justo": float(1.0 / p), "combinable": False, "p_nula": 0.0,
                           "gl": int(x), "gv": int(y)})
    return {"lam_l": float(lam_l), "lam_v": float(lam_v), "rho": float(rho), "p1_l": float(p1_l),
            "p1_v": float(p1_v), "M": M, "q": q, "mercados": lista + marcadores, "marcadores": marcadores}


def mascara_marcador(gl: int, gv: int) -> np.ndarray:
    """Máscara de celdas del marcador exacto gl-gv (para cruzarlo con otros mercados)."""
    return (X == gl) & (Y == gv)


def resultado_en_celdas(gl, gv, gl_ht, gv_ht) -> np.ndarray:
    """
    Índice de la celda que ocurrió en cada partido (para calificar mercados con lo observado).
    Marcadores con más de 10 goles se recortan a 10. -1 si falta el medio tiempo o es incoherente.
    """
    gl, gv = np.minimum(np.asarray(gl, float), MAXG), np.minimum(np.asarray(gv, float), MAXG)
    h, a = np.asarray(gl_ht, float), np.asarray(gv_ht, float)
    ok = np.isfinite(gl) & np.isfinite(gv) & np.isfinite(h) & np.isfinite(a) & (h <= gl) & (a <= gv)
    pos = {tuple(r): i for i, r in enumerate(_cel.tolist())}
    out = np.full(len(gl), -1, dtype=np.int64)
    for i in np.flatnonzero(ok):
        out[i] = pos[(int(gl[i]), int(gv[i]), int(h[i]), int(a[i]))]
    return out


# ==================================================================================================
# Validación con datos (DESARROLLO, lambdas guardadas de un modelo)
# ==================================================================================================
def _pendiente_logit(p: np.ndarray, y: np.ndarray) -> float:
    """Pendiente b de la recalibración logit(y) ~ a + b·logit(p) (1 = calibrado; < 1 = sobreconfiado)."""
    x = np.log(np.clip(p, 1e-9, 1 - 1e-9) / np.clip(1 - p, 1e-9, 1))
    a, b = 0.0, 1.0
    for _ in range(50):
        mu = 1.0 / (1.0 + np.exp(-(a + b * x)))
        g = np.array([np.sum(y - mu), np.sum((y - mu) * x)])
        w = mu * (1 - mu)
        Hm = np.array([[w.sum(), (w * x).sum()], [(w * x).sum(), (w * x * x).sum()]])
        paso = np.linalg.solve(Hm + 1e-9 * np.eye(2), g)
        a, b = a + paso[0], b + paso[1]
        if np.max(np.abs(paso)) < 1e-10:
            break
    return float(b)


def tabla_deciles(p, y, n_grupos: int = 10) -> pd.DataFrame:
    """Pronosticado contra observado por deciles de la probabilidad pronosticada (suceso binario)."""
    p, y = np.asarray(p, float), np.asarray(y, float)
    orden = np.argsort(p, kind="mergesort")
    filas = []
    for k, ix in enumerate(np.array_split(orden, n_grupos), 1):
        pm, fo = p[ix].mean(), y[ix].mean()
        ee = math.sqrt(max(pm * (1 - pm), 1e-12) / len(ix))
        filas.append({"decil": k, "n": len(ix), "pronosticado": pm, "observado": fo, "dif": fo - pm,
                      "z": (fo - pm) / ee})
    return pd.DataFrame(filas)


def resumen_binario(p, y, bloques) -> dict:
    """
    Calibración global de un suceso binario: medias, z de la diferencia, error de calibración por
    deciles, pendiente y log-loss contra la constante (frecuencia observada en la misma muestra, que
    es una referencia favorecida: usa el propio periodo). d_ll < 0 = el modelo gana.
    """
    p, y = np.clip(np.asarray(p, float), 1e-12, 1 - 1e-12), np.asarray(y, float)
    f = y.mean()
    ll = -(y * np.log(p) + (1 - y) * np.log(1 - p))
    ll0 = -(y * math.log(f) + (1 - y) * math.log(1 - f))
    d = metricas.diferencia_pareada(ll, ll0, bloques)
    b = metricas.bootstrap_bloques(y - p, bloques)
    t = tabla_deciles(p, y)
    return {"n": int(len(y)), "pronosticado": float(p.mean()), "observado": float(f),
            "dif": float(f - p.mean()), "ee_dif": b["ee"], "z_dif": float((f - p.mean()) / b["ee"]),
            "ece": float((t["dif"].abs() * t["n"]).sum() / t["n"].sum()),
            "pendiente": _pendiente_logit(p, y), "logloss": float(ll.mean()), "logloss_cte": float(ll0.mean()),
            "d_ll": d["dif"], "ee_d_ll": d["ee"], "z_d_ll": d["z"]}


def validar_desarrollo(nombre: str = "poisson_simple", anios: float = ANIOS_P1) -> dict:
    """
    Calibración de los mercados por mitades y de totales en DESARROLLO con las lambdas guardadas en
    modelo/pred/<nombre>.parquet (rho = 0 si el archivo no lo trae) y la proporción de goles del primer
    tiempo estimada, para cada partido, sólo con lo anterior a su corte (walk-forward).
    Devuelve {"n", "p1", "resumen" (una fila por mercado), "deciles" {clave: tabla}, "descanso_1x2"}.
    """
    pred = arnes.leer_pred(nombre)                       # desarrollo, por bloque
    df = datos.cargar()
    pred = pred.merge(df[["id", "gl_ht", "gv_ht"]], on="id", how="left")
    pred = pred[pred["lam_l"].notna() & pred["gl_ht"].notna()].reset_index(drop=True)
    p1 = proporciones_1t_cortes(pred["corte"], anios, df)
    rho = pred["x_rho"].to_numpy(float) if "x_rho" in pred.columns else 0.0
    M = arnes.matrices_marcadores(pred["lam_l"].to_numpy(), pred["lam_v"].to_numpy(), rho)
    q = celdas(M, p1["p1_l"].to_numpy(), p1["p1_v"].to_numpy())
    P = probabilidades(q)                                # (n, K)
    obs = resultado_en_celdas(pred["gl"], pred["gv"], pred["gl_ht"], pred["gv_ht"])
    ok = obs >= 0
    G, Z = _matrices()
    cat = catalogo()
    bloques = pred["bloque"].to_numpy()
    filas, deciles = [], {}
    for k, mk in enumerate(cat):
        if not mk.combinable:
            continue
        y = G[k, obs[ok]]
        r = resumen_binario(P[ok, k], y, bloques[ok])
        filas.append({"clave": mk.clave, "mercado": etiqueta(mk), **r})
        deciles[mk.clave] = tabla_deciles(P[ok, k], y)
    resumen = pd.DataFrame(filas).set_index("clave")
    # 1X2 al descanso como pronóstico de tres clases
    kk = [claves().index(c) for c in ("D_1", "D_X", "D_2")]
    P3 = P[ok][:, kk]
    P3 = P3 / P3.sum(axis=1, keepdims=True)
    y3 = np.argmax(G[np.array(kk)][:, obs[ok]], axis=0)
    ll3 = -np.log(P3[np.arange(len(y3)), y3])
    f3 = np.bincount(y3, minlength=3) / len(y3)
    ll3c = -np.log(f3[y3])
    d3 = metricas.diferencia_pareada(ll3, ll3c, bloques[ok])
    descanso = {"n": int(len(y3)), "logloss": float(ll3.mean()), "logloss_cte": float(ll3c.mean()),
                "d_ll": d3["dif"], "ee_d_ll": d3["ee"], "frecuencias": f3.tolist(),
                "pronosticado": P3.mean(axis=0).tolist(),
                "deciles_conjuntos": tabla_deciles(P3.ravel(), np.eye(3)[y3].ravel())}
    return {"n": int(ok.sum()), "n_sin_descanso": int((~ok).sum()),
            "p1": {"p1_l_media": float(p1["p1_l"].mean()), "p1_v_media": float(p1["p1_v"].mean()),
                   "p1_l_min": float(p1["p1_l"].min()), "p1_l_max": float(p1["p1_l"].max()),
                   "p1_v_min": float(p1["p1_v"].min()), "p1_v_max": float(p1["p1_v"].max()),
                   "n_medio": float(p1["n"].mean())},
            "resumen": resumen, "deciles": deciles, "descanso_1x2": descanso}


# ==================================================================================================
# Córners y tarjetas totales (modelos simples; familia aparte, NUNCA entran a la combinada exacta)
# ==================================================================================================
CONTEOS = {"corners": {"local": ("corners_l",), "visita": ("corners_v",), "linea": 9.5, "arbitro": False},
           "tarjetas": {"local": ("amarillas_l", "rojas_l"), "visita": ("amarillas_v", "rojas_v"), "linea": 4.5,
                        "arbitro": True}}
N_EQUIPO, K_EQUIPO = 34, 10.0        # últimos 34 partidos del equipo (2 torneos), encogidos con 10 de liga
N_LIGA = 612                         # partidos (4 torneos) para medias, dispersión y frecuencia base de liga
N_ARBITRO, K_ARBITRO = 30, 10.0      # últimos 30 partidos del árbitro, encogidos con 10 de liga
MIN_LIGA = 300                       # sin tantos partidos de liga con estadísticas no se pronostica


class ModeloConteo:
    """
    Total de córners o de tarjetas (amarillas + rojas del boxscore) de un partido: binomial negativa con
        mu = mH · F_local · C_visita + mV · F_visita · C_local   (· factor del árbitro, sólo tarjetas)
    mH, mV = medias de liga del local y de la visita; F y C = tasas a favor y en contra del equipo en sus
    últimos 34 partidos relativas a la media de liga, encogidas hacia 1 con 10 partidos; el árbitro, si
    está designado, multiplica por su media de tarjetas (30 partidos, encogida con 10) entre la de liga.
    Dispersión por momentos sobre los totales de liga recientes: Var = mu + mu^2 / r.
    Todos los números de arriba se fijaron de antemano (no se ajustaron mirando resultados).
    Uso: `ingerir` partidos en orden cronológico y `predecir` antes de ingerir el que se pronostica.
    """

    def __init__(self, que: str):
        from collections import deque
        if que not in CONTEOS:
            raise ValueError(f"que debe ser uno de {sorted(CONTEOS)}")
        self.que, self.cfg = que, CONTEOS[que]
        self.linea = self.cfg["linea"]
        self._deque = deque
        self.liga = deque(maxlen=N_LIGA)                  # (local, visita)
        self.eq: dict = {}                                # equipo -> deque[(a favor, en contra)]
        self.arb: dict = {}                               # árbitro -> deque[total]

    def ingerir(self, local: str, visitante: str, yl: float, yv: float, arbitro: str = "") -> None:
        self.liga.append((yl, yv))
        self.eq.setdefault(local, self._deque(maxlen=N_EQUIPO)).append((yl, yv))
        self.eq.setdefault(visitante, self._deque(maxlen=N_EQUIPO)).append((yv, yl))
        if arbitro:
            self.arb.setdefault(arbitro, self._deque(maxlen=N_ARBITRO)).append(yl + yv)

    def ingerir_historia(self, hist: pd.DataFrame) -> "ModeloConteo":
        """Ingiere, en orden, los partidos evaluables con estadísticas de `hist`."""
        h = hist[hist["evaluable"] & (hist["tiene_stats"] == 1)].sort_values(["fecha_utc", "id"])
        yl = h[list(self.cfg["local"])].sum(axis=1).to_numpy()
        yv = h[list(self.cfg["visita"])].sum(axis=1).to_numpy()
        for a, b, c, d, e in zip(h["local"], h["visitante"], yl, yv, h["arbitro"].fillna("")):
            self.ingerir(a, b, float(c), float(d), e)
        return self

    def predecir(self, local: str, visitante: str, arbitro: str = "") -> dict | None:
        """{"mu", "r", "linea", "p_mas", "p_menos", "p_mas_liga", "con_arbitro"}; None si falta historia de liga."""
        from scipy.stats import nbinom, poisson
        if len(self.liga) < MIN_LIGA:
            return None
        L = np.array(self.liga, float)
        mH, mV = L[:, 0].mean(), L[:, 1].mean()
        tot = L.sum(axis=1)
        m, var = tot.mean(), tot.var(ddof=1)
        mm = m / 2.0

        def tasas(eq):
            d = self.eq.get(eq)
            if not d:
                return 1.0, 1.0
            a = np.array(d, float)
            return ((a[:, 0].sum() + K_EQUIPO * mm) / (len(a) + K_EQUIPO) / mm,
                    (a[:, 1].sum() + K_EQUIPO * mm) / (len(a) + K_EQUIPO) / mm)

        (fl, cl), (fv, cv) = tasas(local), tasas(visitante)
        mu = mH * fl * cv + mV * fv * cl
        con_arb = bool(self.cfg["arbitro"] and arbitro and arbitro in self.arb)
        if con_arb:
            t = self.arb[arbitro]
            mu *= (sum(t) + K_ARBITRO * m) / (len(t) + K_ARBITRO) / m
        k = math.floor(self.linea)
        if var > m:
            r = m * m / (var - m)
            p_menos = float(nbinom.cdf(k, r, r / (r + mu)))
        else:
            r = math.inf
            p_menos = float(poisson.cdf(k, mu))
        p_liga = float(((tot > self.linea).sum() + 1.0) / (len(tot) + 2.0))
        return {"mu": float(mu), "r": float(r), "linea": self.linea, "p_mas": 1.0 - p_menos, "p_menos": p_menos,
                "p_mas_liga": p_liga, "con_arbitro": con_arb}


def validar_conteos(que: str) -> dict:
    """
    Walk-forward por bloque sobre todos los partidos con estadísticas; califica DESARROLLO: log-loss de
    más/menos la línea típica del modelo contra la frecuencia de liga de los últimos 612 partidos.
    d_ll < 0 = el modelo gana; sólo se usa en producción si gana por más de 2 errores estándar.
    """
    df = datos.cargar()
    h = df[df["evaluable"] & (df["tiene_stats"] == 1) & (df["periodo"] != "prueba")].sort_values(["fecha_utc", "id"])
    mod = ModeloConteo(que)
    cfg = CONTEOS[que]
    yl = h[list(cfg["local"])].sum(axis=1).to_numpy(float)
    yv = h[list(cfg["visita"])].sum(axis=1).to_numpy(float)
    arb = h["arbitro"].fillna("").to_numpy()
    loc, vis, per, blo = h["local"].to_numpy(), h["visitante"].to_numpy(), h["periodo"].to_numpy(), h["bloque"].to_numpy()
    filas, i, n = [], 0, len(h)
    while i < n:
        j = i
        while j < n and blo[j] == blo[i]:
            j += 1
        for k in range(i, j):                             # se pronostica todo el bloque antes de ingerirlo
            if per[k] == "desarrollo":
                pr = mod.predecir(loc[k], vis[k], arb[k])
                if pr is not None:
                    filas.append({"bloque": blo[k], "y": float(yl[k] + yv[k] > mod.linea), "total": yl[k] + yv[k], **pr})
        for k in range(i, j):
            mod.ingerir(loc[k], vis[k], yl[k], yv[k], arb[k])
        i = j
    t = pd.DataFrame(filas)
    y = t["y"].to_numpy()
    ll = lambda p: -(y * np.log(np.clip(p, 1e-9, 1)) + (1 - y) * np.log(np.clip(1 - p, 1e-9, 1)))   # noqa: E731
    d = metricas.diferencia_pareada(ll(t["p_mas"].to_numpy()), ll(t["p_mas_liga"].to_numpy()), t["bloque"])
    return {"que": que, "linea": mod.linea, "n": int(len(t)), "media_total": float(t["total"].mean()),
            "media_mu": float(t["mu"].mean()), "obs_mas": float(y.mean()), "pron_mas": float(t["p_mas"].mean()),
            "logloss": float(ll(t["p_mas"].to_numpy()).mean()), "logloss_liga": float(ll(t["p_mas_liga"].to_numpy()).mean()),
            "d_ll": d["dif"], "ee": d["ee"], "z": d["z"], "con_arbitro": float(t["con_arbitro"].mean()),
            "pendiente": _pendiente_logit(np.clip(t["p_mas"].to_numpy(), 1e-6, 1 - 1e-6), y),
            "deciles": tabla_deciles(t["p_mas"].to_numpy(), y)}


def _md(t: pd.DataFrame, dec: int = 3) -> str:
    """Tabla en Markdown con números a `dec` decimales."""
    cols = list(t.columns)
    lin = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" if t[c].dtype == object else "---:" for c in cols) + "|"]
    for r in t.itertuples(index=False):
        lin.append("| " + " | ".join(f"{v:.{dec}f}" if isinstance(v, float) else str(v) for v in r) + " |")
    return "\n".join(lin)


def _main(argv=None) -> int:
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "conteos":
        for que in CONTEOS:
            v = validar_conteos(que)
            print({k: (round(x, 4) if isinstance(x, float) else x) for k, x in v.items() if k != "deciles"})
            print(_md(v["deciles"]))
        return 0
    if not argv or argv[0] != "validar":
        print("uso: python3 -m produccion.mercados validar [nombre_pred] | conteos")
        return 2
    v = validar_desarrollo(argv[1] if len(argv) > 1 else "poisson_simple")
    print(f"partidos: {v['n']} (sin medio tiempo coherente: {v['n_sin_descanso']})  p1: {v['p1']}")
    r = v["resumen"].reset_index()
    print(_md(r[["clave", "n", "pronosticado", "observado", "dif", "z_dif", "ece", "pendiente", "logloss",
                 "logloss_cte", "d_ll", "ee_d_ll"]], 4))
    for c in ("G1T_SI", "O25", "AA_SI", "D_1", "D_X", "D_2"):
        print(f"\n### {c}\n" + _md(v["deciles"][c]))
    d = v["descanso_1x2"]
    print("\n### 1X2 al descanso (tres clases)")
    print({k: d[k] for k in ("n", "logloss", "logloss_cte", "d_ll", "ee_d_ll", "frecuencias", "pronosticado")})
    print(_md(d["deciles_conjuntos"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
