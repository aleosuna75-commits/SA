# -*- coding: utf-8 -*-
"""
API de pronóstico de producción de Cerebro Liga MX.

    from modelo.pronostico import Pronosticador
    p = Pronosticador()                        # campeón de modelo/campeon.json con todo lo jugado hasta ahora
    p.partidos(datos.pendientes())             # por partido: lam_l, lam_v, rho y la explicación por factores
    p.malla(n=2000, fase="liguilla")           # goles esperados 18 x 18 con muestras de incertidumbre
    p.fuerzas()                                # ataque, defensa, rating y ventaja de local por equipo
    Pronosticador(corte="2025-03-07", modelo="dc")   # cualquier retador, con el historial cortado en una fecha

Cómo se ajusta (igual que en el walk-forward del arnés, para que lo que se validó sea lo que se usa):
  1. El historial es todo partido jugado con fecha_utc < corte.
  2. El modelo se ajusta dos veces seguidas: primero en el primer corte de bloque del torneo en curso (ahí
     se fijan los coeficientes que el arnés sólo reajusta al inicio de cada torneo: la corrección de
     `ajuste`, la conversión a goles de `elo`) y después en `corte` (fuerzas de los equipos al día).
  3. Las variables de los partidos a pronosticar (tiros de los últimos 10, viaje, rotación...) se calculan
     con modelo/variables.py truncando físicamente el historial en `corte` (parámetro `hasta`): nada posterior.

Incertidumbre de los parámetros (malla con n > 1 y errores estándar de fuerzas): aproximación normal de
Laplace. Los parámetros del Dixon-Coles (constante, ventaja de local, ataque y defensa) se muestrean de
N(estimación, H^-1), con H la hessiana de la verosimilitud de Poisson ponderada y penalizada en el óptimo;
los coeficientes de la corrección de `ajuste`, de la suya. `rho` se deja fijo en su estimación. Para un
modelo sin verosimilitud propia (elo, ensamble) la dispersión relativa se toma prestada de un `dc` ajustado
con el mismo historial (atributo `incertidumbre`). Verificación del ancho: modelo/RESULTADOS.md.
"""
from __future__ import annotations

import contextlib
import json
import math

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.linalg import cholesky, solve_triangular

from . import arnes, base, datos
from . import variables as V
from .arnes import Modelo
from .familias import candidatos as C

RUTA_CAMPEON = arnes.DIR_MODELO / "campeon.json"
COLS_VARIABLES = [c for g in C.GRUPOS_AJUSTE.values() for c in g]     # las que puede pedir un Ajuste
ID_SINTETICO = 9_000_000_000            # ids de los cruces hipotéticos de la malla (no chocan con ESPN)
CAMPEON_POR_OMISION = "ajuste"


# ==================================================================================================
# Modelos por nombre
# ==================================================================================================
def leer_campeon() -> dict:
    """Contenido de modelo/campeon.json ({} si aún no existe)."""
    if RUTA_CAMPEON.is_file():
        return json.loads(RUTA_CAMPEON.read_text(encoding="utf-8"))
    return {}


def crear_modelo(nombre: str) -> Modelo:
    """Instancia nueva de un finalista (dc, dc2, elo, tiros, ajuste, ensamble) o de poisson_simple."""
    f = C.finalistas()
    if nombre in f:
        return f[nombre]
    if nombre == "poisson_simple":
        return base.PoissonSimple()
    raise ValueError(f"modelo desconocido: {nombre!r} (disponibles: {sorted(f) + ['poisson_simple']})")


def _a_corte(corte) -> pd.Timestamp:
    """Instante UTC del corte. None = ahora; una fecha sin zona se toma como hora de la Ciudad de México."""
    if corte is None:
        return pd.Timestamp.now(tz="UTC")
    t = pd.Timestamp(corte)
    t = t.tz_localize(datos.ZONA) if t.tzinfo is None else t
    return t.tz_convert("UTC")


@contextlib.contextmanager
def variables_inyectadas(d: pd.DataFrame):
    """
    Mientras dura el bloque, las tablas de variables que leen los Ajuste (candidatos.tabla_variables)
    incluyen las filas de `d` (columnas COLS_VARIABLES, por id), con prioridad sobre lo que hubiera.
    Es la vía para dar al modelo las variables calculadas al corte de partidos reales o hipotéticos
    (la alternativa de pasarlas como columnas a Ajuste.predecir falla al escribir en un arreglo de
    sólo lectura con esta versión de pandas).
    """
    nuevas = d.set_index("id")[COLS_VARIABLES].astype(float)
    previas = {}
    for k in C.RUTA_VARIABLES:
        t = C.tabla_variables(k)
        previas[k] = t
        C._tablas_variables[k] = pd.concat([t[~t.index.isin(nuevas.index)], nuevas[t.columns]])
    try:
        yield
    finally:
        C._tablas_variables.update(previas)


def _pct(x: float) -> str:
    return f"{(x - 1.0) * 100:+.0f}%"


# ==================================================================================================
# Aproximación de Laplace
# ==================================================================================================
def laplace_dc(dc: C.DixonColes, hist: pd.DataFrame, corte: pd.Timestamp) -> dict:
    """
    Hessiana de la verosimilitud de Poisson ponderada y penalizada de un DixonColes YA ajustado con
    (hist, corte), evaluada en su óptimo. Reconstruye la misma matriz de diseño que DixonColes.ajustar.
    Devuelve equipos, desplazamientos de cada bloque de parámetros, theta, H y el gradiente (debe ser ~0).
    """
    f_ns = hist["fecha_utc"].to_numpy(dtype="datetime64[ns]").astype("int64")
    edad = (corte.value - f_ns) / 86400e9
    ok = hist["evaluable"].to_numpy() & (edad <= dc.ventana_dias)
    loc, vis = hist["local"].to_numpy()[ok], hist["visitante"].to_numpy()[ok]
    n = len(loc)
    cod, equipos = pd.factorize(np.concatenate([loc, vis]))
    il, iv, ne = cod[:n], cod[n:], len(equipos)
    lig = (hist["fase"].to_numpy()[ok] != "regular").astype(float)
    w = 0.5 ** (edad[ok] / dc.vida_media)
    if dc.peso_liguilla != 1.0:
        w = w * np.where(lig > 0, dc.peso_liguilla, 1.0)
    if dc.olvido_torneo != 1.0:
        cambios = C.orden_de_corte(corte) - C.orden_de_fechas(hist["fecha_local"])[ok]
        w = w * dc.olvido_torneo ** np.clip(cambios, 0, None)
    yl, yv, _, _ = dc._objetivo(hist, ok, w)

    r = np.arange(n)
    con_local, con_fase = dc.ridge_local is not None, bool(dc.fase)
    o_hl = 2 + 2 * ne
    o_f = o_hl + (ne if con_local else 0)
    p = o_f + (2 if con_fase else 0)
    fil = [r, r, r, r, n + r, n + r, n + r]
    col = [np.zeros(n, int), np.ones(n, int), 2 + il, 2 + ne + iv, np.zeros(n, int), 2 + iv, 2 + ne + il]
    val = [np.ones(n)] * 7
    if con_local:
        fil.append(r), col.append(o_hl + il), val.append(np.ones(n))
    if con_fase:
        fil += [r, r, n + r]
        col += [np.full(n, o_f), np.full(n, o_f + 1), np.full(n, o_f)]
        val += [lig, lig, lig]
    X = sparse.csr_matrix((np.concatenate(val), (np.concatenate(fil), np.concatenate(col))), shape=(2 * n, p))
    pen = np.zeros(p)
    pen[2:2 + 2 * ne] = dc.ridge
    if con_local:
        pen[o_hl:o_hl + ne] = dc.ridge_local
    if con_fase:
        pen[o_f:o_f + 2] = dc.ridge_fase

    theta = np.zeros(p)
    theta[0], theta[1] = dc.c, dc.h
    theta[2:2 + ne] = [dc.atk.get(e, 0.0) for e in equipos]
    theta[2 + ne:2 + 2 * ne] = [dc.dfn.get(e, 0.0) for e in equipos]
    if con_local:
        theta[o_hl:o_hl + ne] = [dc.hl.get(e, 0.0) for e in equipos]
    if con_fase:
        theta[o_f], theta[o_f + 1] = dc.f_tot, dc.f_loc
    ww, y = np.concatenate([w, w]), np.concatenate([yl, yv])
    mu = np.exp(X @ theta)
    Xt = X.T.tocsr()
    H = (Xt.multiply(ww * mu) @ X).toarray()
    H[np.diag_indices(p)] += pen + 1e-10
    grad = Xt @ (ww * (y - mu)) - pen * theta
    return {"equipos": list(equipos), "ne": ne, "o_hl": o_hl if con_local else None,
            "o_f": o_f if con_fase else None, "theta": theta, "H": H, "grad": grad,
            "ridge": dc.ridge, "ridge_local": dc.ridge_local, "n": n, "peso_efectivo": float(w.sum())}


def laplace_ajuste(aj: C.Ajuste, hist_coef: pd.DataFrame) -> list[np.ndarray]:
    """
    Hessianas (goles del local, goles de la visita) de las dos regresiones de Poisson con compensación de
    un Ajuste, en sus coeficientes actuales. `hist_coef` es el historial con que se reajustaron.
    """
    h = hist_coef[hist_coef["evaluable"].to_numpy() & np.isin(hist_coef["id"].to_numpy(), list(aj._lam))]
    ids = h["id"].to_numpy()
    z = aj._z(ids)
    lam = np.array([aj._lam[int(i)] for i in ids])
    X = np.column_stack([np.ones(len(ids)), z])
    pen = np.r_[0.0, np.full(z.shape[1], aj.ridge)]
    Hs = []
    for j, b in ((0, aj.b_l), (1, aj.b_v)):
        mu = lam[:, j] * np.exp(X @ b)
        Hs.append((X.T * mu) @ X + np.diag(pen))
    return Hs


def _normales(H: np.ndarray, m: int, rng: np.random.Generator) -> np.ndarray:
    """m muestras de N(0, H^-1) por Cholesky de la precisión; forma (m, p)."""
    L = cholesky(H, lower=True)
    z = rng.standard_normal((H.shape[0], m))
    return solve_triangular(L.T, z, lower=False).T


# ==================================================================================================
# Pronosticador
# ==================================================================================================
class Pronosticador:
    """
    Modelo de producción ajustado con todo lo jugado antes de `corte`.

    corte    None = ahora; instante con zona, o fecha/hora sin zona en hora de la Ciudad de México.
    modelo   None = el campeón de modelo/campeon.json; nombre de un finalista ("dc", "elo", "ensamble"...)
             o una instancia de arnes.Modelo (cualquier retador).
    df       tabla de datos.cargar() (por omisión se lee de disco).

    Atributos: corte, nombre, modelo, torneo, equipos (los 18 del torneo en curso, en orden alfabético),
    incertidumbre ("propia" o "prestada de dc").
    """

    def __init__(self, corte=None, modelo=None, df: pd.DataFrame | None = None):
        self.corte = _a_corte(corte)
        if modelo is None:
            modelo = leer_campeon().get("modelo", CAMPEON_POR_OMISION)
        self.modelo: Modelo = crear_modelo(modelo) if isinstance(modelo, str) else modelo
        self.nombre = self.modelo.nombre
        C._tablas_variables.clear()                     # la caché de variables pudo cambiar en disco
        self._df = datos.cargar() if df is None else df
        jug = datos.jugados(self._df)
        f_ns = jug["fecha_utc"].to_numpy(dtype="datetime64[ns]").astype("int64")
        self._hist = jug.iloc[:int(np.searchsorted(f_ns, self.corte.value, side="left"))]
        if not len(self._hist):
            raise ValueError("no hay partidos jugados antes del corte")

        # torneo en curso (el del primer partido en o después del corte) y sus equipos
        vivos = self._df[self._df["estado"].isin(["jugado", "programado"])]
        futuros = vivos[vivos["fecha_utc"] >= self.corte]
        self.torneo = str(futuros["torneo"].iloc[0] if len(futuros) else self._hist["torneo"].iloc[-1])
        t = vivos[vivos["torneo"] == self.torneo]
        self.equipos: list[str] = sorted(set(t["local"]) | set(t["visitante"]))

        # ajuste en dos pasos, como el walk-forward: inicio del torneo en curso y luego el corte
        orden = C.orden_de_corte(self.corte)
        cb = vivos.loc[(vivos["corte_bloque"] < self.corte)
                       & (vivos["corte_bloque"] > self.corte - pd.Timedelta(days=220)), "corte_bloque"]
        previos = [c for c in sorted(cb.unique()) if C.orden_de_corte(pd.Timestamp(c)) == orden]
        self._hist_coef, self.corte_coeficientes = self._hist, self.corte
        if previos:
            c0 = pd.Timestamp(previos[0])
            h0 = jug.iloc[:int(np.searchsorted(f_ns, c0.value, side="left"))]
            if len(h0):
                self.modelo.ajustar(h0, c0)
                self._hist_coef, self.corte_coeficientes = h0, c0
        self.modelo.ajustar(self._hist, self.corte)
        self._aux_cache = None
        self._malla_cache = None
        self._lap = None
        self.incertidumbre = "propia" if self._dc_propio() is not None else "prestada de dc"

    # ------------------------------------------------------------------------------------------
    # Datos de entrada
    # ------------------------------------------------------------------------------------------
    def _aux(self):
        """Tablas en texto que necesita variables.construir (se leen una vez por instancia)."""
        if self._aux_cache is None:
            self._aux_cache = (V.leer_partidos(), V.leer_tarjetas(), V.leer_alineaciones(), V.leer_sedes())
        return self._aux_cache

    def _normalizar(self, df: pd.DataFrame) -> pd.DataFrame:
        """Partidos por jugar con los tipos y columnas previas al partido que espera un Modelo."""
        df = pd.DataFrame(df).reset_index(drop=True)
        falta = [c for c in ("id", "fecha_utc", "local", "visitante") if c not in df.columns]
        if falta:
            raise ValueError(f"faltan columnas en los partidos a pronosticar: {falta}")
        d = pd.DataFrame({"id": pd.to_numeric(df["id"]).astype("int64")})
        d["fecha_utc"] = pd.DatetimeIndex(pd.to_datetime(df["fecha_utc"], utc=True)).as_unit("ns")
        d = pd.concat([d, datos.asignar_bloques(d["fecha_utc"])], axis=1)
        d["local"], d["visitante"] = df["local"].astype(str), df["visitante"].astype(str)
        d["torneo"] = df["torneo"].astype(str) if "torneo" in df.columns else self.torneo
        fase = df["fase"].astype(str) if "fase" in df.columns else pd.Series("regular", index=df.index)
        d["fase"] = fase.where(fase.str.len() > 0, "regular")
        for c in datos.COLS_PREPARTIDO:
            if c not in d.columns:
                d[c] = df[c] if c in df.columns else (np.nan if c in datos.COLS_MOMIOS or c in ("pierna", "estadio_id") else "")
        for c in datos.COLS_MOMIOS + ["pierna", "estadio_id"]:
            d[c] = pd.to_numeric(d[c], errors="coerce")
        return d[datos.COLS_PREPARTIDO]

    def _variables(self, d: pd.DataFrame) -> pd.DataFrame:
        """
        Variables a la fecha de los partidos `d` (normalizados), con el historial truncado en el corte.
        Un partido que ya está en partidos.csv se toma de ahí (su sede y su fecha); uno hipotético (cruce
        de liguilla, malla) se agrega como programado: sin estadio_id se supone la sede habitual del local.
        """
        txt, tarjetas, alineaciones, sedes = self._aux()
        # con un corte pasado no hace falta calcular las filas de años posteriores: se conserva el
        # calendario hasta 30 días después del último partido pedido (las fechas ISO ordenan como texto)
        limite = (d["fecha_utc"].max() + pd.Timedelta(days=30)).strftime("%Y-%m-%dT%H:%MZ")
        txt = txt[(txt["fecha_utc"] <= limite) | txt["id"].isin(set(d["id"].astype(str)))]
        ids_txt = set(txt["id"])
        nuevos = d[~d["id"].astype(str).isin(ids_txt)]
        todos = txt
        if len(nuevos):
            filas = pd.DataFrame("", index=range(len(nuevos)), columns=txt.columns)
            filas["id"] = nuevos["id"].astype(str).to_numpy()
            filas["fecha_utc"] = nuevos["fecha_utc"].dt.strftime("%Y-%m-%dT%H:%MZ").to_numpy()
            for c in ("torneo", "local", "visitante"):
                filas[c] = nuevos[c].astype(str).to_numpy()
            filas["fase"] = "regular"            # las variables que usa el modelo no dependen de la fase
            filas["estadio_id"] = V._txt(nuevos["estadio_id"]).to_numpy()
            filas["estado"] = "programado"
            todos = pd.concat([txt, filas], ignore_index=True)
        tab = V.construir(todos, hasta=self.corte, corte="partido", tarjetas=tarjetas, alineaciones=alineaciones,
                          sedes=sedes, _calcular_desde=V._a_epoca(self.corte))
        return tab.set_index("id")[COLS_VARIABLES].reindex(d["id"].to_numpy())

    def _con_variables(self, d: pd.DataFrame) -> pd.DataFrame:
        d = d.copy()
        v = self._variables(d)
        for c in COLS_VARIABLES:
            d[c] = v[c].to_numpy()
        return d

    @staticmethod
    def _lambdas(pr: dict | None) -> tuple[float, float, float]:
        """(lam_l, lam_v, rho) de un pronóstico del modelo; NaN si el modelo no pronosticó."""
        if pr is None:
            return math.nan, math.nan, 0.0
        if "M" in pr:
            g = arnes.goles_esperados(np.asarray(pr["M"], float))
            return float(pr.get("lam_l", g[0])), float(pr.get("lam_v", g[1])), 0.0
        if "lam_l" not in pr:
            raise ValueError(f"el modelo {pr.keys()} sólo da 1X2: no sirve para marcadores ni simulación")
        return float(pr["lam_l"]), float(pr["lam_v"]), float(pr.get("rho", 0.0))

    # ------------------------------------------------------------------------------------------
    # Explicación por factores
    # ------------------------------------------------------------------------------------------
    def _dc_propio(self) -> C.DixonColes | None:
        """El DixonColes cuyos parámetros determinan el pronóstico (el modelo o la base de un Ajuste)."""
        m = self.modelo
        if isinstance(m, C.DixonColes):
            return m
        if isinstance(m, C.Ajuste) and isinstance(m.base, C.DixonColes):
            return m.base
        return None

    @staticmethod
    def _explica_dc(dc: C.DixonColes, loc: str, vis: str, liguilla: bool) -> list[dict]:
        e = math.exp
        a_l, a_v = dc.atk.get(loc, 0.0), dc.atk.get(vis, 0.0)
        d_l, d_v = dc.dfn.get(loc, 0.0), dc.dfn.get(vis, 0.0)
        h = dc.h + dc.hl.get(loc, 0.0)
        out = [
            {"factor": "media de la liga", "efecto_l": e(dc.c), "efecto_v": e(dc.c),
             "detalle": f"un equipo promedio le anota {e(dc.c):.2f} goles a otro promedio sin ventaja de local"},
            {"factor": f"ataque de {loc}", "efecto_l": e(a_l), "efecto_v": 1.0,
             "detalle": f"{loc} anota {_pct(e(a_l))} respecto del promedio"},
            {"factor": f"defensa de {vis}", "efecto_l": e(d_v), "efecto_v": 1.0,
             "detalle": f"{vis} concede {_pct(e(d_v))} respecto del promedio"},
            {"factor": f"ataque de {vis}", "efecto_l": 1.0, "efecto_v": e(a_v),
             "detalle": f"{vis} anota {_pct(e(a_v))} respecto del promedio"},
            {"factor": f"defensa de {loc}", "efecto_l": 1.0, "efecto_v": e(d_l),
             "detalle": f"{loc} concede {_pct(e(d_l))} respecto del promedio"},
            {"factor": "ventaja de local", "efecto_l": e(h), "efecto_v": 1.0,
             "detalle": f"jugar en casa sube los goles del local {_pct(e(h))}"
                        + (" (ventaja propia de este equipo)" if dc.hl else " (igual para todos los equipos)")},
        ]
        if liguilla and dc.fase:
            out.append({"factor": "liguilla", "efecto_l": e(dc.f_tot + dc.f_loc), "efecto_v": e(dc.f_tot),
                        "detalle": "efecto estimado de la fase final sobre el total de goles y la localía"})
        return out

    def _explica_ajuste(self, aj: C.Ajuste, fila: pd.Series, loc: str, vis: str) -> list[dict]:
        z = aj._z(np.array([int(fila["id"])]))[0]              # dentro de variables_inyectadas
        crudo = {c: float(fila[c]) if c in fila.index else math.nan for c in aj.columnas}
        media = dict(zip(aj.columnas, aj.media))

        def v(c, dec=1):
            return "sin dato" if not np.isfinite(crudo[c]) else f"{crudo[c]:.{dec}f}"

        textos = {
            "tiros": lambda: (f"tiros por partido en los últimos 10: {loc} {v('juego10_tiros_f_l')} a favor y "
                              f"{v('juego10_tiros_c_l')} en contra; {vis} {v('juego10_tiros_f_v')} y "
                              f"{v('juego10_tiros_c_v')} (media histórica {media.get('juego10_tiros_f_l', math.nan):.1f})"),
            "viaje": lambda: (f"{vis} viaja {v('sede_viaje_km_v', 0)} km "
                              f"(media {media.get('sede_viaje_km_v', math.nan):.0f} km)"),
            "rotacion": lambda: (f"{vis} cambió {v('once_previa_cambios_v', 0)} titulares entre sus dos últimos "
                                 f"onces (media {media.get('once_previa_cambios_v', math.nan):.1f})"),
            "suspension": lambda: (f"ausencias por suspensión ponderadas: {loc} {v('susp_imp_l', 2)}, "
                                   f"{vis} {v('susp_imp_v', 2)}"),
            "altitud": lambda: f"{vis} juega {v('sede_alt_dif_v', 0)} m por encima de su sede",
        }
        nombres = {"tiros": "tiros de los últimos 10 partidos", "viaje": "viaje del visitante",
                   "rotacion": "rotación del once del visitante", "suspension": "suspendidos",
                   "altitud": "altitud"}
        out, k = [], 0
        for g in aj.grupos:
            idx = np.arange(k, k + len(C.GRUPOS_AJUSTE[g]))
            k += len(idx)
            out.append({"factor": nombres.get(g, g), "detalle": textos[g]() if g in textos else g,
                        "efecto_l": float(math.exp(z[idx] @ aj.b_l[1 + idx])),
                        "efecto_v": float(math.exp(z[idx] @ aj.b_v[1 + idx]))})
        out.append({"factor": "constante de la corrección", "efecto_l": float(math.exp(aj.b_l[0])),
                    "efecto_v": float(math.exp(aj.b_v[0])),
                    "detalle": "nivel medio de la corrección (casi 1): recentra las lambdas tras corregir"})
        return out

    def _explicar(self, fila: pd.Series, pr: dict | None, lam_l: float, lam_v: float) -> list[dict]:
        """Factores multiplicativos cuyo producto es la lambda de cada equipo (la fuerza base va primero)."""
        if pr is None:
            return []
        m, loc, vis = self.modelo, str(fila["local"]), str(fila["visitante"])
        lig = str(fila["fase"]) != "regular"
        if isinstance(m, C.DixonColes):
            return self._explica_dc(m, loc, vis, lig)
        if isinstance(m, C.Ajuste) and isinstance(m.base, C.DixonColes):
            return self._explica_dc(m.base, loc, vis, lig) + self._explica_ajuste(m, fila, loc, vis)
        if isinstance(m, C.Elo) and m.coef is not None and "x_elo_dif" in pr:
            al, bl, av, bv = m.coef
            x = pr["x_elo_dif"] / 400.0
            return [{"factor": "media de la liga", "efecto_l": math.exp(al), "efecto_v": math.exp(av),
                     "detalle": "goles de local y de visita entre dos equipos de igual Elo (incluye la ventaja de local)"},
                    {"factor": "diferencia de Elo", "efecto_l": math.exp(bl * x), "efecto_v": math.exp(bv * x),
                     "detalle": f"{loc} menos {vis}: {pr['x_elo_dif']:+.0f} puntos Elo"}]
        return [{"factor": "fuerza base", "efecto_l": lam_l, "efecto_v": lam_v,
                 "detalle": f"goles esperados del modelo {self.nombre} (sin desglose por factores)"}]

    # ------------------------------------------------------------------------------------------
    # Contrato
    # ------------------------------------------------------------------------------------------
    def partidos(self, df: pd.DataFrame) -> list[dict]:
        """
        Pronóstico de partidos por jugar. `df` trae columnas de partidos.csv (id, fecha_utc, torneo, fase,
        pierna, local, visitante, estadio_id...; mínimas: id, fecha_utc, local, visitante). Por partido:
        {"id", "local", "visitante", "lam_l", "lam_v", "rho", "explica": [{"factor", "detalle", "efecto_l",
        "efecto_v"}]}; el producto de efecto_l (efecto_v) es lam_l (lam_v). Si el modelo da una matriz de
        marcadores propia se agrega "M".
        """
        d = self._normalizar(df)
        if not len(d):
            return []
        if (d["fecha_utc"] < self.corte).any():
            raise ValueError("hay partidos anteriores al corte: un Pronosticador sólo pronostica hacia adelante")
        d = self._con_variables(d)
        out = []
        with variables_inyectadas(d):
            preds = self.modelo.predecir(d[datos.COLS_PREPARTIDO])
            for (_, fila), pr in zip(d.iterrows(), preds):
                lam_l, lam_v, rho = self._lambdas(pr)
                r = {"id": int(fila["id"]), "local": str(fila["local"]), "visitante": str(fila["visitante"]),
                     "lam_l": lam_l, "lam_v": lam_v, "rho": rho,
                     "explica": self._explicar(fila, pr, lam_l, lam_v)}
                if pr is not None and "M" in pr:
                    r["M"] = np.asarray(pr["M"], float)
                out.append(r)
        return out

    def _malla_base(self) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
        """Los 306 cruces (i recibe a j en la sede habitual de i) con sus variables al corte."""
        if self._malla_cache is None:
            ne = len(self.equipos)
            ii, jj = np.nonzero(~np.eye(ne, dtype=bool))
            d = pd.DataFrame({"id": ID_SINTETICO + 100 * ii + jj,
                              "fecha_utc": self.corte.floor("min") + pd.Timedelta(hours=4),
                              "torneo": self.torneo, "fase": "regular",
                              "local": [self.equipos[i] for i in ii], "visitante": [self.equipos[j] for j in jj]})
            self._malla_cache = (self._con_variables(self._normalizar(d)), ii, jj)
        return self._malla_cache

    def _laplace(self) -> dict:
        """Hessianas para muestrear (se calculan una vez). Sin DixonColes propio se ajusta uno de sombra."""
        if self._lap is None:
            dc = self._dc_propio()
            if dc is None:
                dc = C._dc()
                dc.ajustar(self._hist, self.corte)
            lap = laplace_dc(dc, self._hist, self.corte)
            m = self.modelo
            if isinstance(m, C.Ajuste) and self._dc_propio() is not None:
                lap["H_ajuste"] = laplace_ajuste(m, self._hist_coef)
            self._lap = lap
        return self._lap

    def _desvios(self, m: int, rng: np.random.Generator, liguilla: bool) -> tuple[np.ndarray, np.ndarray]:
        """m muestras del desvío de log lam_l y log lam_v, forma (m, 18, 18), alrededor de la estimación."""
        lap = self._laplace()
        ne = len(self.equipos)
        d = _normales(lap["H"], m, rng)
        pos = {e: k for k, e in enumerate(lap["equipos"])}
        idx = np.array([pos.get(e, -1) for e in self.equipos])
        nuevo = idx < 0                                 # equipo sin partidos en la ventana: sólo el prior

        def bloque(desplazamiento, ridge):
            x = d[:, desplazamiento + np.where(nuevo, 0, idx)]
            if nuevo.any():
                x[:, nuevo] = rng.standard_normal((m, int(nuevo.sum()))) / math.sqrt(ridge)
            return x

        atk, dfn = bloque(2, lap["ridge"]), bloque(2 + lap["ne"], lap["ridge"])
        comun = d[:, 0][:, None, None]
        dl = comun + d[:, 1][:, None, None] + atk[:, :, None] + dfn[:, None, :]
        dv = comun + atk[:, None, :] + dfn[:, :, None]
        if lap["o_hl"] is not None:
            dl = dl + bloque(lap["o_hl"], lap["ridge_local"])[:, :, None]
        if lap["o_f"] is not None and liguilla:
            dl = dl + (d[:, lap["o_f"]] + d[:, lap["o_f"] + 1])[:, None, None]
            dv = dv + d[:, lap["o_f"]][:, None, None]
        if "H_ajuste" in lap:
            dm, ii, jj = self._malla_base()
            with variables_inyectadas(dm):
                Z = self.modelo._z(dm["id"].to_numpy())
            for H, destino in zip(lap["H_ajuste"], (dl, dv)):
                b = _normales(H, m, rng)
                destino[:, ii, jj] += b[:, :1] + b[:, 1:] @ Z.T
        return dl, dv

    def malla(self, n: int = 1, fase: str = "regular", semilla: int = 0) -> dict:
        """
        Goles esperados de todos los cruces: {"equipos": [18], "lam_l": array[n, 18, 18], "lam_v": igual,
        "rho": float}. [k, i, j] = el equipo i recibe al j en la sede habitual de i (la diagonal es NaN).
        k = 0 es la estimación puntual (la misma de partidos()); k >= 1 son muestras de la incertidumbre de
        los parámetros (aproximación normal de Laplace, ver el encabezado), reproducibles con `semilla`.
        fase: "regular" o "liguilla".
        """
        if fase not in ("regular", "liguilla"):
            raise ValueError("fase debe ser 'regular' o 'liguilla'")
        n = int(n)
        if n < 1:
            raise ValueError("n debe ser al menos 1")
        dm, ii, jj = self._malla_base()
        d = dm.copy()
        d["fase"] = "regular" if fase == "regular" else "cuartos"
        ne = len(self.equipos)
        L, Vt = np.full((n, ne, ne), np.nan), np.full((n, ne, ne), np.nan)
        rhos = []
        with variables_inyectadas(d):
            preds = self.modelo.predecir(d[datos.COLS_PREPARTIDO])
        for i, j, pr in zip(ii, jj, preds):
            L[0, i, j], Vt[0, i, j], rho = self._lambdas(pr)
            rhos.append(rho)
        if n > 1:
            dl, dv = self._desvios(n - 1, np.random.default_rng(semilla), fase == "liguilla")
            L[1:] = L[0][None] * np.exp(dl)
            Vt[1:] = Vt[0][None] * np.exp(dv)
        return {"equipos": list(self.equipos), "lam_l": L, "lam_v": Vt, "rho": float(np.mean(rhos))}

    def fuerzas(self, n: int = 400, semilla: int = 0) -> pd.DataFrame:
        """
        Fuerza de cada equipo, en goles y frente a un rival promedio (media sobre los otros 17):
          ataque         goles esperados a favor en cancha neutral
          defensa        goles esperados en contra en cancha neutral (menos es mejor)
          rating         ataque - defensa
          ventaja_local  diferencia de goles esperada en casa menos la de cancha neutral
        Cancha neutral = media geométrica de lo que el equipo haría de local y de visita contra ese rival.
        ee_* = desviación estándar de cada cifra sobre `n` muestras de la incertidumbre de los parámetros.
        Ordenado por rating.
        """
        m = self.malla(n + 1, "regular", semilla)
        L, Vt = m["lam_l"], m["lam_v"]
        Lt, Vtt = L.transpose(0, 2, 1), Vt.transpose(0, 2, 1)
        with np.errstate(invalid="ignore"):
            ataque = np.nanmean(np.sqrt(L * Vtt), axis=2)       # i anota: de local ante j y de visita en casa de j
            defensa = np.nanmean(np.sqrt(Vt * Lt), axis=2)      # i recibe: de local ante j y de visita en casa de j
            casa = np.nanmean(L - Vt, axis=2)
        rating = ataque - defensa
        ventaja = casa - rating
        out = pd.DataFrame({"equipo": m["equipos"]})
        for nombre, x in (("ataque", ataque), ("defensa", defensa), ("rating", rating), ("ventaja_local", ventaja)):
            out[nombre] = x[0]
        for nombre, x in (("ataque", ataque), ("defensa", defensa), ("rating", rating), ("ventaja_local", ventaja)):
            out[f"ee_{nombre}"] = x[1:].std(axis=0, ddof=1)
        return out.sort_values("rating", ascending=False).reset_index(drop=True)


# ==================================================================================================
# Tabla lista para publicar
# ==================================================================================================
def tabla_pronosticos(pro: Pronosticador, df: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Una fila por partido de `df` (por omisión, los pendientes): lambdas, rho, 1X2, marcador más probable,
    P(más de 2.5 goles) y P(ambos anotan), derivados de la matriz Dixon-Coles del pronóstico.
    """
    df = datos.pendientes(pro._df) if df is None else df
    filas = []
    for r in pro.partidos(df):
        M = r["M"] if "M" in r else arnes.matriz_marcadores(r["lam_l"], r["lam_v"], r["rho"])
        p = arnes.p1x2(M)
        gl, gv, pm = arnes.marcador_mas_probable(M)
        filas.append({"id": r["id"], "local": r["local"], "visitante": r["visitante"], "lam_l": r["lam_l"],
                      "lam_v": r["lam_v"], "rho": r["rho"], "p_l": float(p[0]), "p_e": float(p[1]),
                      "p_v": float(p[2]), "marcador": f"{int(gl)}-{int(gv)}", "p_marcador": float(pm),
                      "p_over25": float(arnes.p_over(M, 2.5)), "p_ambos": float(arnes.p_ambos_anotan(M))})
    return pd.DataFrame(filas)


if __name__ == "__main__":
    import time
    t0 = time.time()
    pro_ = Pronosticador()
    print(f"modelo {pro_.nombre} · corte {pro_.corte:%Y-%m-%d %H:%M} UTC · {pro_.torneo} · "
          f"ajustado en {time.time() - t0:.1f} s")
    with pd.option_context("display.width", 200, "display.float_format", "{:.3f}".format):
        print(tabla_pronosticos(pro_).drop(columns="id").to_string(index=False))
        print(pro_.fuerzas().to_string(index=False))
