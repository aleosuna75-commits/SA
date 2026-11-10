# -*- coding: utf-8 -*-
"""
Combinadas.

combinada_partido / combinadas_partido: 4 picks del MISMO partido con su probabilidad CONJUNTA exacta
(suma de la distribución por mitades sobre la intersección de las máscaras; nunca el producto de las
marginales). Reglas:
  1. los 4 picks son de familias distintas (mercados.Mercado.familia);
  2. ningún par se implica (A dentro de B) ni se excluye (A y B sin celdas comunes): se comprueba con
     las máscaras, y equivale a P(A y B) = P(A), = P(B) o = 0;
  3. ningún par es casi redundante: P(A|B) <= 0.97 y P(B|A) <= 0.97;
  4. ningún pick queda casi decidido por los OTROS TRES: P(pick | los otros tres) <= 0.97 (cubre las
     implicaciones de conjunto, p. ej. "local o empate" + "más de 1.5" implica "el local anota");
  5. la probabilidad marginal de cada pick cae en la banda de la variante.
Variantes: "segura" (0.55-0.85, máxima conjunta), "equilibrada" (0.45-0.75, máxima conjunta x momio
ingenuo acotado) y "atrevida" (0.30-0.60, máxima conjunta). La búsqueda es exhaustiva y vectorizada:
se arman todos los pares válidos y se cruzan par contra par (cada cuarteta aparece una sola vez).

combinada_jornada: un pick por partido (los más confiables), probabilidad = producto entre partidos.
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

from modelo import arnes
from . import mercados as mk

BANDAS = {"segura": (0.55, 0.85), "equilibrada": (0.45, 0.75), "atrevida": (0.30, 0.60)}
MAX_CONDICIONAL = 0.97          # reglas 3 y 4
TOPE_MOMIO_INGENUO = 8.0        # "equilibrada": tope del momio ingenuo (producto de 1/p de los picks)
PASO_AMPLIAR, MAX_AMPLIAR = 0.05, 3   # si la banda no alcanza para 4 picks válidos se ensancha (se avisa)
BANDA_JORNADA = (0.58, 0.85)    # la del proyecto anterior
PISOS_JORNADA = {"segura": 0.45, "atrevida": 0.18}   # pisos de probabilidad conjunta del proyecto anterior


@lru_cache(maxsize=1)
def _estructura():
    """Mercados combinables: lista, máscaras (K, celdas) y matriz de pares estructuralmente válidos."""
    cat = [m for m in mk.catalogo() if m.combinable]
    B = np.array([m.mascara for m in cat], dtype=bool)
    Bf = B.astype(np.float64)
    inter = Bf @ Bf.T
    tam = B.sum(axis=1).astype(float)
    implica = inter == np.minimum(tam[:, None], tam[None, :])        # una máscara contiene a la otra
    excluye = inter == 0
    fam = np.array([m.familia for m in cat])
    valido = (fam[:, None] != fam[None, :]) & ~implica & ~excluye
    return cat, B, Bf, valido


def relacion(clave_a: str, clave_b: str) -> str:
    """'implica', 'excluye', 'misma_familia' o 'libre' entre dos mercados combinables (por máscaras)."""
    cat, B, _, _ = _estructura()
    ix = {m.clave: i for i, m in enumerate(cat)}
    a, b = ix[clave_a], ix[clave_b]
    n = int((B[a] & B[b]).sum())
    if n == 0:
        return "excluye"
    if n == min(int(B[a].sum()), int(B[b].sum())):
        return "implica"
    return "misma_familia" if cat[a].familia == cat[b].familia else "libre"


def prob_conjunta(q, claves) -> float:
    """P(todos los picks) exacta: suma de q sobre la intersección de las máscaras."""
    cat, B, _, _ = _estructura()
    ix = {m.clave: i for i, m in enumerate(cat)}
    m = np.ones(mk.N_CELDAS, bool)
    for c in claves:
        m &= B[ix[c]]
    return float(np.asarray(q, float)[m].sum())


def _buscar(q: np.ndarray, lo: float, hi: float, objetivo: str, excluir: frozenset = frozenset()):
    """Mejor cuarteta válida con marginales en [lo, hi]; None si no hay. Devuelve (índices, P4, n_eval)."""
    cat, B, Bf, valido = _estructura()
    p = Bf @ q
    cand = np.flatnonzero((p >= lo) & (p <= hi) & np.array([m.clave not in excluir for m in cat]))
    if len(cand) < 4:
        return None, 0.0, 0, len(cand)
    pc, Bc = p[cand], Bf[cand]
    P2 = (Bc * q) @ Bc.T
    ok = valido[np.ix_(cand, cand)] & (P2 <= MAX_CONDICIONAL * np.minimum(pc[:, None], pc[None, :]))
    pi, pj = np.nonzero(np.triu(ok, 1))                              # pares i < j
    if len(pi) < 2:
        return None, 0.0, 0, len(cand)
    BP = Bc[pi] * Bc[pj]                                             # máscara del par
    W = BP * q
    P4 = W @ BP.T                                                    # par a = (i, j) contra par b = (k, l)
    P3 = W @ Bc.T                                                    # P(i, j, m)
    ia, ja, ib, jb = pi[:, None], pj[:, None], pi[None, :], pj[None, :]
    val = (ja < ib) & ok[ia, ib] & ok[ia, jb] & ok[ja, ib] & ok[ja, jb]
    a_idx, b_idx = np.arange(len(pi))[:, None], np.arange(len(pi))[None, :]
    min3 = np.minimum(np.minimum(P3[a_idx, ib], P3[a_idx, jb]), np.minimum(P3[b_idx, ia], P3[b_idx, ja]))
    val &= P4 <= MAX_CONDICIONAL * min3                              # regla 4
    n_eval = int(val.sum())
    if n_eval == 0:
        return None, 0.0, 0, len(cand)
    if objetivo == "conjunta":
        punt = P4
    else:                                                            # conjunta x momio ingenuo acotado
        ingenuo = 1.0 / (pc[ia] * pc[ja] * pc[ib] * pc[jb])
        punt = P4 * np.minimum(ingenuo, TOPE_MOMIO_INGENUO)
    punt = np.where(val, punt, -1.0)
    a, b = np.unravel_index(int(np.argmax(punt)), punt.shape)
    idx = cand[[pi[a], pj[a], pi[b], pj[b]]]
    return idx, float(P4[a, b]), n_eval, len(cand)


def combinada_partido(q, variante: str = "segura", local: str = "Local", visitante: str = "Visita",
                      excluir=()) -> dict | None:
    """
    La combinada de 4 picks de un partido para una variante. `q` = vector de celdas (mercados.celdas).
    Devuelve None si ni ensanchando la banda hay cuatro picks compatibles. Claves del resultado:
      picks [{clave, etiqueta, familia, tipo, prob}] (de mayor a menor probabilidad), prob_conjunta,
      momio_justo (1 / conjunta), prob_ingenua (producto de marginales), correlacion (conjunta /
      ingenua: cuántas veces más probable es que lo que diría el producto), banda, banda_ampliada,
      n_candidatos y n_evaluadas (cuartetas válidas comparadas).
    """
    if variante not in BANDAS:
        raise ValueError(f"variante debe ser una de {sorted(BANDAS)}")
    q = np.asarray(q, float)
    lo0, hi0 = BANDAS[variante]
    objetivo = "valor" if variante == "equilibrada" else "conjunta"
    cat = _estructura()[0]
    for paso in range(MAX_AMPLIAR + 1):
        lo, hi = lo0 - paso * PASO_AMPLIAR, hi0 + paso * PASO_AMPLIAR
        idx, p4, n_eval, n_cand = _buscar(q, lo, hi, objetivo, frozenset(excluir))
        if idx is not None:
            break
    else:
        return None
    Bf = _estructura()[2]
    picks = []
    for i in idx:
        m = cat[int(i)]
        picks.append({"clave": m.clave, "etiqueta": mk.etiqueta(m, local, visitante), "familia": m.familia,
                      "tipo": m.tipo.format(L=local, V=visitante), "prob": float(Bf[int(i)] @ q)})
    picks.sort(key=lambda d: (-d["prob"], d["clave"]))
    ingenua = float(np.prod([d["prob"] for d in picks]))
    return {"variante": variante, "picks": picks, "prob_conjunta": p4,
            "momio_justo": (1.0 / p4) if p4 > 0 else math.inf, "prob_ingenua": ingenua,
            "correlacion": p4 / ingenua, "banda": [round(lo, 2), round(hi, 2)], "banda_ampliada": paso > 0,
            "n_candidatos": n_cand, "n_evaluadas": n_eval}


def combinadas_partido(lam_l: float, lam_v: float, rho: float = 0.0, p1_l: float | None = None,
                       p1_v: float | None = None, local: str = "Local", visitante: str = "Visita") -> dict:
    """Las tres variantes de un partido a partir de sus lambdas: {"segura", "equilibrada", "atrevida"}."""
    if p1_l is None or p1_v is None:
        p1_l, p1_v = mk.proporcion_1t()[:2]
    q = mk.celdas(arnes.matriz_marcadores(lam_l, lam_v, rho), p1_l, p1_v)
    return {v: combinada_partido(q, v, local, visitante) for v in BANDAS}


# ==================================================================================================
# Combinada de jornada: un pick por partido
# ==================================================================================================
def combinada_jornada(partidos: list[dict], banda: tuple[float, float] = BANDA_JORNADA,
                      max_repetidos: int = 3) -> dict:
    """
    Un pick por partido, el más confiable dentro de la banda (por omisión 0.58-0.85, la del proyecto
    anterior), sin repetir el mismo tipo de mercado (Hándicap, Total de goles...) más de
    `max_repetidos` veces. Entre partidos distintos la
    probabilidad conjunta es el producto (se suponen independientes).

    partidos: [{"id", "local", "visitante", "q"}] (q = mercados.celdas) o con "lam_l", "lam_v", "rho",
    "p1_l", "p1_v" en lugar de q.
    Devuelve {"candidatos": un pick por partido ordenados de más a menos probable, y tres variantes:
      "equilibrada": los n primeros que maximizan n x P(todos) (criterio del proyecto anterior);
      "segura" / "atrevida": se agregan picks mientras P(todos) >= 0.45 / 0.18}.
    """
    cat, _, Bf, _ = _estructura()
    lo, hi = banda
    opciones = []
    for d in partidos:
        q = d.get("q")
        if q is None:
            q = mk.celdas(arnes.matriz_marcadores(d["lam_l"], d["lam_v"], d.get("rho", 0.0)), d["p1_l"], d["p1_v"])
        p = Bf @ np.asarray(q, float)
        orden = [int(i) for i in np.argsort(-p, kind="mergesort") if lo <= p[i] <= hi]
        opciones.append((d, p, orden))
    # voraz: en cada vuelta toma, entre los partidos sin pick, el pick disponible más probable
    usados: dict[str, int] = {}
    elegidos, libres = [], list(range(len(opciones)))
    while libres:
        mejor = None
        for k in libres:
            d, p, orden = opciones[k]
            i = next((i for i in orden if usados.get(cat[i].tipo, 0) < max_repetidos), None)
            if i is not None and (mejor is None or p[i] > mejor[2]):
                mejor = (k, i, float(p[i]))
        if mejor is None:
            break
        k, i, pr = mejor
        d, m = opciones[k][0], cat[i]
        usados[m.tipo] = usados.get(m.tipo, 0) + 1
        libres.remove(k)
        loc, vis = d.get("local", "Local"), d.get("visitante", "Visita")
        elegidos.append({"id": d.get("id"), "partido": f"{loc} vs {vis}", "clave": m.clave,
                         "etiqueta": mk.etiqueta(m, loc, vis), "familia": m.familia, "prob": pr})
    acum = np.cumprod([e["prob"] for e in elegidos]) if elegidos else np.array([])

    def variante(n: int) -> dict:
        pc = float(acum[n - 1]) if n else 1.0
        return {"n": n, "picks": elegidos[:n], "prob_conjunta": pc if n else None,
                "momio_justo": (1.0 / pc) if n else None}

    n_eq = int(np.argmax(np.arange(1, len(acum) + 1) * acum)) + 1 if len(acum) else 0
    out = {"candidatos": elegidos, "banda": list(banda), "sin_pick": [opciones[k][0].get("id") for k in libres],
           "equilibrada": variante(n_eq)}
    for nombre, piso in PISOS_JORNADA.items():
        out[nombre] = variante(int((acum >= piso).sum()))
    return out


# ==================================================================================================
# Todo junto, consumiendo sólo el contrato del Pronosticador
# ==================================================================================================
def paquete_partidos(pron, df, p1: tuple[float, float] | None = None, con_jornada: bool = True) -> dict:
    """
    Mercados y combinadas de los partidos de `df` (columnas de partidos.csv de partidos por jugar) con
    un Pronosticador que cumpla el contrato (`pron.partidos(df)`; el corte se toma de `pron.corte` si
    existe). Devuelve {"p1_l", "p1_v", "partidos": [{id, local, visitante, lam_l, lam_v, rho, explica,
    matriz (11x11), mercados, marcadores, combinadas}], "jornada"}; todo serializable a JSON.
    """
    if p1 is None:
        p1 = mk.proporcion_1t(getattr(pron, "corte", None))[:2]
    salida, para_jornada = [], []
    for d, loc, vis in zip(pron.partidos(df), df["local"], df["visitante"]):
        r = mk.mercados_partido(d["lam_l"], d["lam_v"], d.get("rho", 0.0), p1[0], p1[1], loc, vis)
        q = r["q"]
        salida.append({"id": d["id"], "local": loc, "visitante": vis, "lam_l": r["lam_l"], "lam_v": r["lam_v"],
                       "rho": r["rho"], "explica": d.get("explica", []), "matriz": np.round(r["M"], 6).tolist(),
                       "mercados": r["mercados"], "marcadores": r["marcadores"],
                       "combinadas": {v: combinada_partido(q, v, loc, vis) for v in BANDAS}})
        para_jornada.append({"id": d["id"], "local": loc, "visitante": vis, "q": q})
    return {"p1_l": float(p1[0]), "p1_v": float(p1[1]), "partidos": salida,
            "jornada": combinada_jornada(para_jornada) if con_jornada and para_jornada else None}


# ==================================================================================================
# Validación con datos: ¿la probabilidad conjunta que se anuncia se cumple?
# ==================================================================================================
def validar_desarrollo(nombre: str = "poisson_simple", anios: float = mk.ANIOS_P1) -> dict:
    """
    Recorre DESARROLLO con las lambdas guardadas en modelo/pred/<nombre>.parquet (proporción del primer
    tiempo sólo con el pasado de cada corte), arma las tres combinadas de cada partido y compara la
    probabilidad conjunta anunciada con la frecuencia con que se cumplieron los cuatro picks.
    Elegir la cuarteta de mayor probabilidad sesga hacia arriba lo anunciado (maldición del ganador):
    esta tabla mide cuánto. Devuelve {"resumen": DataFrame por variante, "quintiles": {variante: tabla},
    "picks": frecuencia de cada mercado elegido}.
    """
    import pandas as pd
    from modelo import datos, metricas
    pred = arnes.leer_pred(nombre)
    df = datos.cargar()
    pred = pred.merge(df[["id", "gl_ht", "gv_ht"]], on="id", how="left")
    pred = pred[pred["lam_l"].notna() & pred["gl_ht"].notna()].reset_index(drop=True)
    p1 = mk.proporciones_1t_cortes(pred["corte"], anios, df)
    rho = pred["x_rho"].to_numpy(float) if "x_rho" in pred.columns else 0.0
    Q = mk.celdas(arnes.matrices_marcadores(pred["lam_l"].to_numpy(), pred["lam_v"].to_numpy(), rho),
                  p1["p1_l"].to_numpy(), p1["p1_v"].to_numpy())
    obs = mk.resultado_en_celdas(pred["gl"], pred["gv"], pred["gl_ht"], pred["gv_ht"])
    cat = {m.clave: m for m in mk.catalogo()}
    filas, uso = [], {}
    for i in np.flatnonzero(obs >= 0):
        for v in BANDAS:
            c = combinada_partido(Q[i], v)
            if c is None:
                continue
            aciertos = [bool(cat[p["clave"]].mascara[obs[i]]) for p in c["picks"]]
            for p in c["picks"]:
                uso[(v, p["clave"])] = uso.get((v, p["clave"]), 0) + 1
            filas.append({"variante": v, "bloque": pred["bloque"].iloc[i], "conjunta": c["prob_conjunta"],
                          "ingenua": c["prob_ingenua"], "ampliada": c["banda_ampliada"],
                          "acierta": float(all(aciertos)), "picks_acertados": float(sum(aciertos))})
    t = pd.DataFrame(filas)
    res, quint = [], {}
    for v, g in t.groupby("variante", sort=False):
        b = metricas.bootstrap_bloques(g["acierta"] - g["conjunta"], g["bloque"])
        p = np.clip(g["conjunta"].to_numpy(), 1e-9, 1 - 1e-9)
        pi = np.clip(g["ingenua"].to_numpy(), 1e-9, 1 - 1e-9)
        y = g["acierta"].to_numpy()
        ll = lambda pr: float(-(y * np.log(pr) + (1 - y) * np.log(1 - pr)).mean())   # noqa: E731
        res.append({"variante": v, "n": len(g), "conjunta_anunciada": g["conjunta"].mean(),
                    "frecuencia_observada": g["acierta"].mean(), "dif": b["media"], "ee": b["ee"],
                    "z": b["media"] / b["ee"], "producto_ingenuo": g["ingenua"].mean(),
                    "momio_justo_medio": (1 / g["conjunta"]).mean(), "picks_acertados_de_4": g["picks_acertados"].mean(),
                    "logloss_conjunta": ll(p), "logloss_ingenua": ll(pi), "banda_ampliada": int(g["ampliada"].sum())})
        quint[v] = mk.tabla_deciles(g["conjunta"].to_numpy(), y, 5).rename(columns={"decil": "quintil"})
    picks = pd.Series(uso).rename_axis(["variante", "clave"]).rename("veces").reset_index()
    return {"resumen": pd.DataFrame(res), "quintiles": quint, "picks": picks}


def _main(argv=None) -> int:
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] != "validar":
        print("uso: python3 -m produccion.combinada validar [nombre_pred]")
        return 2
    v = validar_desarrollo(argv[1] if len(argv) > 1 else "poisson_simple")
    print(mk._md(v["resumen"], 4))
    for k, t in v["quintiles"].items():
        print(f"\n### {k}\n" + mk._md(t))
    p = v["picks"].sort_values(["variante", "veces"], ascending=[True, False])
    for k, g in p.groupby("variante"):
        print(f"\n{k}: " + ", ".join(f"{c} {n}" for c, n in zip(g["clave"].head(12), g["veces"].head(12))))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
