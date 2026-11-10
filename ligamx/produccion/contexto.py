# -*- coding: utf-8 -*-
"""
Contexto DESCRIPTIVO de cada partido a una fecha (para explicar el partido en la página).
Nada de aquí altera el pronóstico: son hechos contados sobre lo ya jugado.

    ctx = Contexto(fecha)               # sólo usa partidos JUGADOS con fecha_utc < fecha
    ctx.partido(fila)                   # todo lo de un partido por jugar (fila con id, fecha_utc, local,
                                        # visitante, fase, estadio_id...)
    ctx.tabla(), ctx.equipo("Toluca"), ctx.historial("América", "Cruz Azul")
    ctx.dominios_liguilla(), ctx.balance_estadios()

Sin fugas: `self.hist` (jugados antes de la fecha) es la única fuente de resultados; de los partidos
posteriores sólo se conserva la agenda (fecha, equipos y sede: se conocen de antemano) para contar el
descanso y saber si una suspensión se cumple antes. Las tarjetas se filtran por los ids de `self.hist`.

Límites: sólo hay partidos de Liga MX (el descanso no ve Copa ni Concacaf); las suspensiones se deducen
de tarjetas.csv (roja en el último partido = al menos un partido fuera; quinta amarilla del torneo) y
no conocen castigos de más de un partido ni apelaciones; los lesionados sólo salen si existe
config/actualidad.json.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from modelo import datos
from modelo import variables as V

RAIZ = datos.RAIZ
RUTA_MEDIOS = RAIZ / "web" / "medios.json"
RUTA_ACTUALIDAD = RAIZ / "config" / "actualidad.json"
RUTA_SEDES = datos.DIR_DATOS / "estadios_sedes.csv"
LIGUILLA = ("repechaje", "cuartos", "semifinal", "final")
_COLS_AGENDA = ["id", "fecha_utc", "torneo", "fase", "pierna", "local", "visitante", "estadio_id",
                "estadio", "ciudad", "arbitro"]
_OT_AMARILLAS = V.orden_torneo("Apertura 2021")           # desde aquí 5 amarillas = un partido de suspensión
# Finales que los datos no deciden (ESPN no trae el marcador de los tiempos extra): hecho histórico.
# Clausura 2009: global 2-2 a 90 minutos y Pumas ganó en tiempos extra (3-2 global).
GANADOR_MANUAL = {**V.GANADOR_MANUAL, ("Clausura 2009", "final", "Pachuca", "Pumas"): "Pumas"}


def _a_utc(fecha) -> pd.Timestamp:
    """Instante UTC; None = ahora; sin zona = hora de la Ciudad de México."""
    if fecha is None:
        return pd.Timestamp.now(tz="UTC")
    t = pd.Timestamp(fecha)
    return (t.tz_localize(datos.ZONA) if t.tzinfo is None else t).tz_convert("UTC")


def _id_estadio(x) -> str:
    try:
        return "" if x is None or x != x or x == "" else str(int(float(x)))
    except (TypeError, ValueError):
        return ""


def _balance(gf, gc) -> dict:
    """PJ, G, E, P, GF, GC y porcentaje de puntos a partir de goles a favor y en contra."""
    gf, gc = np.asarray(gf, float), np.asarray(gc, float)
    n, g, e = len(gf), int((gf > gc).sum()), int((gf == gc).sum())
    return {"pj": n, "g": g, "e": e, "p": n - g - e, "gf": int(gf.sum()), "gc": int(gc.sum()),
            "pct_puntos": round((3 * g + e) / (3 * n), 4) if n else None}


def _dia(t) -> str:
    return pd.Timestamp(t).tz_convert(datos.ZONA).strftime("%Y-%m-%d")


class Contexto:
    """Hechos a la fecha (ver el docstring del módulo). Las salidas son dicts/listas serializables a JSON."""

    def __init__(self, fecha=None, partidos: pd.DataFrame | None = None):
        df = datos.cargar() if partidos is None else partidos
        self.fecha = _a_utc(fecha)
        antes = df["fecha_utc"] < self.fecha
        self.hist = df[(df["estado"] == "jugado") & antes].sort_values(["fecha_utc", "id"]).reset_index(drop=True)
        self.agenda = df.loc[~antes & df["estado"].isin(["programado", "jugado", "en_juego"]), _COLS_AGENDA] \
            .sort_values(["fecha_utc", "id"]).reset_index(drop=True)
        if self.hist.empty:
            raise ValueError("Contexto: no hay partidos jugados antes de la fecha")
        self.torneo = str(self.agenda["torneo"].iloc[0]) if len(self.agenda) else str(self.hist["torneo"].iloc[-1])
        self._sedes()
        h = self.hist
        h["sede"] = [self._sede_de_id(i, e, l, f) for i, e, l, f in
                     zip(h["id"], h["estadio_id"], h["local"], h["fecha_utc"])]
        # formato largo: una fila por equipo y partido
        base = ["id", "fecha_utc", "torneo", "fase", "pierna", "sede"]
        a = h[base].assign(equipo=h["local"], rival=h["visitante"], cond="L", gf=h["gl"], gc=h["gv"])
        b = h[base].assign(equipo=h["visitante"], rival=h["local"], cond="V", gf=h["gv"], gc=h["gl"])
        self.largo = pd.concat([a, b]).sort_values(["fecha_utc", "id"], kind="mergesort").reset_index(drop=True)
        self._tar = None
        self._series = None
        self._tablas: dict = {}
        reg = df[(df["torneo"] == self.torneo) & (df["fase"] == "regular") & (df["estado"] != "cancelado")]
        self.equipos = sorted(set(reg["local"]) | set(reg["visitante"]))

    # ---------------------------------------------------------------------------------------------
    # sedes
    # ---------------------------------------------------------------------------------------------
    def _sedes(self) -> None:
        s = pd.read_csv(RUTA_SEDES, dtype=str, keep_default_na=False, encoding="utf-8")
        self._id_sede = {str(r["estadio_id"]): r["sede"] for r in s.to_dict("records") if r["sede"]}
        self._info_sede = {}
        for r in s.to_dict("records"):
            if r["sede"] and r["sede"] not in self._info_sede:
                def f(x):
                    try:
                        return float(x)
                    except (TypeError, ValueError):
                        return None
                self._info_sede[r["sede"]] = {"sede": r["sede"], "nombre": r["nombre"], "ciudad": r["ciudad"],
                                              "lat": f(r["lat"]), "lon": f(r["lon"]), "altitud_m": f(r["altitud_m"]),
                                              "superficie": r["superficie"] or None, "aforo": None}
        self._no_antes = {k: pd.Timestamp(v, tz=datos.ZONA).tz_convert("UTC") for k, v in V.SEDE_NO_ANTES.items()}
        try:
            self._medios = json.loads(RUTA_MEDIOS.read_text(encoding="utf-8")).get("estadios", [])
        except (OSError, ValueError):
            self._medios = []

    def _sede_de_id(self, pid, estadio_id, local, fecha_utc) -> str | None:
        """Sede (clave de estadios_sedes.csv) de un partido, con las correcciones conocidas de ESPN."""
        e = _id_estadio(estadio_id)
        s = V.SEDE_CORREGIDA_PARTIDO.get(str(pid)) or V.SEDE_CORREGIDA_LOCAL.get((e, local)) or self._id_sede.get(e)
        if s and s in self._no_antes and fecha_utc < self._no_antes[s]:
            return None
        return s or None

    def sede_habitual(self, equipo: str) -> str | None:
        """La sede más frecuente en sus últimos 6 partidos de local del último año (empate: la más reciente)."""
        t = self.largo[(self.largo["equipo"] == equipo) & (self.largo["cond"] == "L") & self.largo["sede"].notna()
                       & (self.largo["fecha_utc"] >= self.fecha - pd.Timedelta(days=365))].tail(V.VENTANA_HABITUAL)
        if t.empty:
            return None
        cuenta = t["sede"].value_counts()
        mejores = set(cuenta[cuenta == cuenta.max()].index)
        return next(s for s in reversed(t["sede"].tolist()) if s in mejores)

    def info_sede(self, sede: str | None) -> dict | None:
        """Nombre, ciudad, altitud, aforo y superficie: de web/medios.json si el estadio está ahí (a menos de 3 km)."""
        if sede is None or sede not in self._info_sede:
            return None
        d = dict(self._info_sede[sede])
        d["fuente"] = "datos/estadios_sedes.csv"
        if d["lat"] is not None:
            mejor = None
            for m in self._medios:
                try:
                    km = V._haversine(d["lat"], d["lon"], float(m["lat"]), float(m["lon"]))
                except (KeyError, TypeError, ValueError):
                    continue
                if km <= 3.0 and (mejor is None or km < mejor[0]):
                    mejor = (km, m)
            if mejor:
                m = mejor[1]
                d.update({"nombre": m.get("nombre", d["nombre"]), "ciudad": m.get("ciudad", d["ciudad"]),
                          "altitud_m": m.get("altitud_m", d["altitud_m"]), "aforo": m.get("capacidad"),
                          "superficie": m.get("superficie", d["superficie"]), "slug_medios": m.get("slug"),
                          "apodo": m.get("apodo"), "fuente": "web/medios.json"})
        return d

    # ---------------------------------------------------------------------------------------------
    # tabla y equipo
    # ---------------------------------------------------------------------------------------------
    def tabla(self, torneo: str | None = None) -> pd.DataFrame:
        """
        Tabla general de la fase regular con lo jugado antes de la fecha: pos, equipo, PJ, G, E, P, GF,
        GC, DG, PTS. Orden: puntos, diferencia de goles, goles a favor y nombre (los criterios
        posteriores del reglamento y la resta por regla de menores no se aplican aquí).
        """
        torneo = torneo or self.torneo
        if torneo in self._tablas:
            return self._tablas[torneo].copy()
        t = self.largo[(self.largo["torneo"] == torneo) & (self.largo["fase"] == "regular")]
        g = t.assign(G=(t.gf > t.gc).astype(int), E=(t.gf == t.gc).astype(int), P=(t.gf < t.gc).astype(int))
        r = g.groupby("equipo").agg(PJ=("id", "size"), G=("G", "sum"), E=("E", "sum"), P=("P", "sum"),
                                    GF=("gf", "sum"), GC=("gc", "sum"))
        if torneo == self.torneo:
            r = r.reindex(self.equipos, fill_value=0)
        r[["GF", "GC"]] = r[["GF", "GC"]].astype(int)
        r["DG"], r["PTS"] = r["GF"] - r["GC"], 3 * r["G"] + r["E"]
        r = r.reset_index().sort_values(["PTS", "DG", "GF", "equipo"], ascending=[False, False, False, True],
                                        kind="mergesort").reset_index(drop=True)
        r.insert(0, "pos", np.arange(1, len(r) + 1))
        self._tablas[torneo] = r
        return r.copy()

    def forma(self, equipo: str, n: int = 5) -> list[dict]:
        """Últimos n partidos (del más reciente al más antiguo): resultado G/E/P, rival, condición y marcador."""
        t = self.largo[self.largo["equipo"] == equipo].tail(n).iloc[::-1]
        return [{"fecha": _dia(r.fecha_utc), "torneo": r.torneo, "fase": r.fase, "rival": r.rival,
                 "condicion": "local" if r.cond == "L" else "visita",
                 "resultado": "G" if r.gf > r.gc else ("E" if r.gf == r.gc else "P"),
                 "gf": int(r.gf), "gc": int(r.gc), "marcador": f"{int(r.gf)}-{int(r.gc)}"} for r in t.itertuples()]

    def rachas(self, equipo: str, minimo: int = 2) -> list[dict]:
        """Rachas VIGENTES (partidos seguidos hasta el último jugado), de `minimo` partidos o más."""
        t = self.largo[self.largo["equipo"] == equipo].tail(80).iloc[::-1]
        gf, gc, cond = t["gf"].to_numpy(), t["gc"].to_numpy(), t["cond"].to_numpy()

        def cuenta(ok):
            n = 0
            for v in ok:
                if not v:
                    break
                n += 1
            return n

        defs = [("victorias seguidas", gf > gc), ("partidos sin perder", gf >= gc), ("partidos sin ganar", gf <= gc),
                ("derrotas seguidas", gf < gc), ("empates seguidos", gf == gc), ("partidos anotando", gf > 0),
                ("partidos sin anotar", gf == 0), ("partidos sin recibir gol", gc == 0),
                ("partidos recibiendo gol", gc > 0)]
        out = [{"racha": nom, "partidos": cuenta(ok)} for nom, ok in defs]
        for c, nom in (("L", "de local"), ("V", "de visita")):
            m = cond == c
            out.append({"racha": f"partidos sin perder {nom}", "partidos": cuenta((gf >= gc)[m])})
            out.append({"racha": f"victorias seguidas {nom}", "partidos": cuenta((gf > gc)[m])})
            out.append({"racha": f"partidos sin ganar {nom}", "partidos": cuenta((gf <= gc)[m])})
        out = [d for d in out if d["partidos"] >= minimo]
        return sorted(out, key=lambda d: -d["partidos"])

    def equipo(self, equipo: str, torneo: str | None = None) -> dict:
        """Forma, rachas, balance de local y de visita en el torneo, goles y posición en la tabla."""
        torneo = torneo or self.torneo
        t = self.largo[(self.largo["equipo"] == equipo) & (self.largo["torneo"] == torneo) &
                       (self.largo["fase"] == "regular")]
        tab = self.tabla(torneo)
        fila = tab[tab["equipo"] == equipo]
        return {"equipo": equipo, "torneo": torneo,
                "posicion": int(fila["pos"].iloc[0]) if len(fila) else None,
                "puntos": int(fila["PTS"].iloc[0]) if len(fila) else None,
                "balance": _balance(t["gf"], t["gc"]),
                "balance_local": _balance(t.loc[t.cond == "L", "gf"], t.loc[t.cond == "L", "gc"]),
                "balance_visita": _balance(t.loc[t.cond == "V", "gf"], t.loc[t.cond == "V", "gc"]),
                "forma": self.forma(equipo), "rachas": self.rachas(equipo)}

    # ---------------------------------------------------------------------------------------------
    # historial directo y series
    # ---------------------------------------------------------------------------------------------
    @staticmethod
    def _lista(t: pd.DataFrame) -> list[dict]:
        return [{"fecha": _dia(r.fecha_utc), "torneo": r.torneo, "fase": r.fase, "local": r.local,
                 "visitante": r.visitante, "gl": int(r.gl), "gv": int(r.gv), "sede": r.sede}
                for r in t.iloc[::-1].itertuples()]

    def historial(self, local: str, visitante: str, sede: str | None = None, n: int = 10) -> dict:
        """
        Enfrentamientos entre los dos equipos. Los balances se cuentan desde el punto de vista de
        `local` (g = victorias suyas). Bloques: ultimos (n más recientes), en_sede (con `local` de
        local en esa sede), liguilla (partidos de fase final), finales, y series (eliminatorias
        completas con su ganador).
        """
        h = self.hist
        t = h[((h["local"] == local) & (h["visitante"] == visitante)) |
              ((h["local"] == visitante) & (h["visitante"] == local))]

        def bloque(x, lista=True):
            gf = np.where(x["local"] == local, x["gl"], x["gv"])
            gc = np.where(x["local"] == local, x["gv"], x["gl"])
            d = {"balance": _balance(gf, gc)}
            if lista:
                d["partidos"] = self._lista(x)
            return d

        out = {"local": local, "visitante": visitante, "total": bloque(t, lista=False), "ultimos": bloque(t.tail(n))}
        if sede is not None:
            out["en_sede"] = bloque(t[(t["local"] == local) & (t["sede"] == sede)].tail(n))
            out["en_sede"]["sede"] = sede
        out["liguilla"] = bloque(t[t["fase"].isin(LIGUILLA)])
        out["finales"] = bloque(t[t["fase"] == "final"])
        s = self.series()
        a, b = sorted((local, visitante))
        s = s[(s["a"] == a) & (s["b"] == b)]
        out["series"] = {"n": int(len(s)), "gana_local": int((s["ganador"] == local).sum()),
                         "gana_visitante": int((s["ganador"] == visitante).sum()),
                         "finales": int((s["fase"] == "final").sum()),
                         "lista": s[["torneo", "fase", "ganador", "global"]].iloc[::-1].to_dict("records")}
        return out

    def series(self) -> pd.DataFrame:
        """
        Eliminatorias COMPLETAS jugadas antes de la fecha: torneo, fase, a, b (orden alfabético),
        ganador (None si los datos no alcanzan a decidir) y global a 90 minutos. Regla del ganador:
        global; en la final, tiempos extra y penales; en las demás, penales si hubo, gol de visitante
        cuando regía (Apertura 2012 a Clausura 2021) y, al final, la mejor posición en la tabla.
        """
        if self._series is not None:
            return self._series
        h = self.hist[self.hist["fase"].isin(LIGUILLA)]
        filas = []
        for (tor, fase, a, b), g in h.assign(a=np.minimum(h["local"], h["visitante"]),
                                             b=np.maximum(h["local"], h["visitante"])) \
                .groupby(["torneo", "fase", "a", "b"], sort=False):
            g = g.sort_values("fecha_utc")
            ult = g.iloc[-1]
            if not (pd.isna(ult["pierna"]) or ult["pierna"] == 2):
                continue                                  # sólo se conoce la ida
            L, Vv = ult["local"], ult["visitante"]        # L = local de la última pierna
            gl = float(g.loc[g.local == L, "gl"].sum() + g.loc[g.local != L, "gv"].sum())
            gv = float(g.loc[g.local == L, "gv"].sum() + g.loc[g.local != L, "gl"].sum())
            visita_L = float(g.loc[g.local != L, "gv"].sum())
            visita_V = float(g.loc[g.local == L, "gv"].sum())
            gan = None
            if gl != gv:
                gan = L if gl > gv else Vv
            elif pd.notna(ult["gl_et"]) and pd.notna(ult["gv_et"]) and ult["gl_et"] != ult["gv_et"]:
                gan = L if ult["gl_et"] > ult["gv_et"] else Vv
            elif pd.notna(ult["pen_l"]) and pd.notna(ult["pen_v"]) and ult["pen_l"] != ult["pen_v"]:
                gan = L if ult["pen_l"] > ult["pen_v"] else Vv
            elif (tor, fase, a, b) in GANADOR_MANUAL:
                gan = GANADOR_MANUAL[(tor, fase, a, b)]
            elif fase != "final":
                if V.formato_torneo(tor)["gol_visitante"] and len(g) == 2 and visita_L != visita_V:
                    gan = L if visita_L > visita_V else Vv
                else:
                    pos = self.tabla(tor).set_index("equipo")["pos"]
                    if L in pos.index and Vv in pos.index and pos[L] != pos[Vv]:
                        gan = L if pos[L] < pos[Vv] else Vv
            filas.append({"torneo": tor, "fase": fase, "a": a, "b": b, "ganador": gan,
                          "global": f"{L} {int(gl)}-{int(gv)} {Vv}", "fecha": ult["fecha_utc"]})
        cols = ["torneo", "fase", "a", "b", "ganador", "global", "fecha"]
        self._series = (pd.DataFrame(filas, columns=cols).sort_values("fecha").reset_index(drop=True)
                        if filas else pd.DataFrame(columns=cols))
        return self._series

    def dominios_liguilla(self, top: int = 15, min_series: int = 3) -> list[dict]:
        """
        Pares de equipos con más eliminatorias entre sí (cuartos, semifinal y final; el repechaje no
        cuenta) y su balance: series y finales ganadas por cada uno. Orden: series, finales.
        """
        s = self.series()
        s = s[s["fase"] != "repechaje"]
        out = []
        for (a, b), g in s.groupby(["a", "b"]):
            if len(g) < min_series:
                continue
            f = g[g["fase"] == "final"]
            out.append({"a": a, "b": b, "series": int(len(g)), "gana_a": int((g["ganador"] == a).sum()),
                        "gana_b": int((g["ganador"] == b).sum()), "sin_decidir": int(g["ganador"].isna().sum()),
                        "finales": int(len(f)), "finales_a": int((f["ganador"] == a).sum()),
                        "finales_b": int((f["ganador"] == b).sum()),
                        "ultima": f"{g.iloc[-1]['torneo']} ({g.iloc[-1]['fase']}): {g.iloc[-1]['global']}"})
        out.sort(key=lambda d: (-d["series"], -d["finales"], d["a"], d["b"]))
        return out[:top]

    # ---------------------------------------------------------------------------------------------
    # sede, descanso, viaje
    # ---------------------------------------------------------------------------------------------
    def balance_local_en_sede(self, local: str, sede: str | None, anios: float | None = 3.0) -> dict | None:
        """Balance de `local` jugando de local en `sede` (últimos `anios` años; None = toda la historia)."""
        if sede is None:
            return None
        t = self.largo[(self.largo["equipo"] == local) & (self.largo["cond"] == "L") & (self.largo["sede"] == sede)]
        if anios is not None:
            t = t[t["fecha_utc"] >= self.fecha - pd.Timedelta(days=365.25 * anios)]
        d = _balance(t["gf"], t["gc"])
        d["desde"] = _dia(t["fecha_utc"].iloc[0]) if len(t) else None
        return d

    def balance_estadios(self) -> list[dict]:
        """Por cada equipo del torneo: su sede habitual hoy y su balance histórico y de 3 años como local ahí."""
        out = []
        for eq in self.equipos:
            s = self.sede_habitual(eq)
            info = self.info_sede(s) or {}
            out.append({"equipo": eq, "sede": s, "estadio": info.get("nombre"), "altitud_m": info.get("altitud_m"),
                        "historico": self.balance_local_en_sede(eq, s, None),
                        "ultimos_3_anios": self.balance_local_en_sede(eq, s, 3.0)})
        out.sort(key=lambda d: -((d["historico"] or {}).get("pct_puntos") or 0))
        return out

    def descanso(self, equipo: str, fecha_partido) -> dict:
        """Días desde su partido anterior de Liga MX (jugado o, si aún no se juega, agendado antes de éste)."""
        f = _a_utc(fecha_partido)
        j = self.largo.loc[self.largo["equipo"] == equipo, "fecha_utc"]
        a = self.agenda[((self.agenda["local"] == equipo) | (self.agenda["visitante"] == equipo)) &
                        (self.agenda["fecha_utc"] < f)]["fecha_utc"]
        previo = a.max() if len(a) else (j.max() if len(j) else None)
        if previo is None or pd.isna(previo):
            return {"dias": None, "previo": None, "previo_pendiente": False}
        return {"dias": round((f - previo).total_seconds() / 86400.0, 1), "previo": _dia(previo),
                "previo_pendiente": bool(len(a))}

    def viaje_km(self, visitante: str, sede: str | None) -> float | None:
        """Distancia en línea recta (km) de la sede habitual del visitante a la sede del partido."""
        a, b = self.info_sede(self.sede_habitual(visitante)), self.info_sede(sede)
        if not a or not b or a["lat"] is None or b["lat"] is None:
            return None
        return round(V._haversine(a["lat"], a["lon"], b["lat"], b["lon"]), 0)

    # ---------------------------------------------------------------------------------------------
    # disciplina y actualidad
    # ---------------------------------------------------------------------------------------------
    def _tarjetas(self) -> pd.DataFrame:
        if self._tar is None:
            t = datos.tabla("tarjetas", self.hist)       # sólo partidos de self.hist
            t = t.merge(self.hist[["id", "fecha_utc", "torneo", "fase"]], left_on="partido_id", right_on="id")
            t["quien"] = np.where(t["jugador_id"].notna(), t["jugador_id"].astype(str), t["jugador"].astype(str))
            self._tar = t
        return self._tar

    def suspendidos(self, equipo: str, fecha_partido=None) -> dict:
        """
        Suspendidos deducidos de las tarjetas del ÚLTIMO partido jugado del equipo: expulsados (roja
        directa o doble amarilla) y quienes llegaron ahí a un múltiplo de 5 amarillas en el torneo (la
        cuenta de liguilla es aparte). `apercibidos`: a una amarilla de la suspensión. Si el equipo tiene
        otro partido agendado antes de `fecha_partido`, la sanción se cumple ahí y lo de este partido aún
        no se puede saber: conocido = False.
        """
        f = _a_utc(fecha_partido) if fecha_partido is not None else None
        out = {"equipo": equipo, "conocido": True, "suspendidos": [], "apercibidos": [], "nota": None}
        mios = self.largo[self.largo["equipo"] == equipo]
        if mios.empty:
            return out
        ult = mios.iloc[-1]
        out["ultimo_partido"] = f"{_dia(ult.fecha_utc)} vs {ult.rival}"
        if f is not None:
            a = self.agenda[((self.agenda["local"] == equipo) | (self.agenda["visitante"] == equipo)) &
                            (self.agenda["fecha_utc"] < f)]
            if len(a):
                out.update(conocido=False, nota="tiene un partido agendado antes: las sanciones se sabrán al jugarlo")
                return out
            if (f - ult.fecha_utc).days > V.CADUCA_SUSPENSION_DIAS:
                return out
        t = self._tarjetas()
        t = t[t["equipo"] == equipo]
        del_ult = t[t["partido_id"] == ult.id]
        if ult.id not in set(self.hist.loc[self.hist["tiene_tarjetas"] == 1, "id"]) and del_ult.empty:
            out["nota"] = "sin tarjetas con jugador en el último partido (pueden faltar datos)"
        dobles = set(del_ult.loc[del_ult["tipo"] == "segunda_amarilla", "quien"])
        vistos = set()
        for r in del_ult[del_ult["tipo"].isin(["roja", "segunda_amarilla"])].itertuples():
            if r.quien not in vistos:
                vistos.add(r.quien)
                out["suspendidos"].append({"jugador": r.jugador, "motivo": "expulsado en su último partido "
                                           + ("(doble amarilla)" if r.tipo == "segunda_amarilla" else "(roja)")})
        if V.orden_torneo(ult.torneo) >= _OT_AMARILLAS:
            alcance = ult.fase == "regular"
            am = t[(t["torneo"] == ult.torneo) & ((t["fase"] == "regular") == alcance) & (t["tipo"] == "amarilla")]
            seg = t[(t["torneo"] == ult.torneo) & (t["tipo"] == "segunda_amarilla")][["partido_id", "quien"]]
            am = am.merge(seg.assign(doble=1), on=["partido_id", "quien"], how="left")
            am = am[am["doble"].isna()]                   # la amarilla de una doble amarilla no acumula
            cuenta = am.groupby("quien").size()
            nombres = am.groupby("quien")["jugador"].last()
            hoy = set(am.loc[am["partido_id"] == ult.id, "quien"])
            for quien, n in cuenta.items():
                if quien in vistos:
                    continue
                if n % 5 == 0 and quien in hoy and quien not in dobles:
                    out["suspendidos"].append({"jugador": nombres[quien], "motivo": f"llegó a {n} amarillas en el torneo"})
                elif n % 5 == 4:
                    out["apercibidos"].append({"jugador": nombres[quien], "amarillas": int(n)})
        return out

    @staticmethod
    def lesionados(equipo: str) -> list[dict] | None:
        """
        Bajas de config/actualidad.json si el archivo existe (None si no). Formatos aceptados:
        {"lesionados": [{"equipo", "jugador", ...}]}, {"equipos": {equipo: {"lesionados": [...]}}} o
        {equipo: {"lesionados": [...]}}. Lo edita una persona o un proceso aparte; aquí sólo se lee.
        """
        if not RUTA_ACTUALIDAD.exists():
            return None
        try:
            d = json.loads(RUTA_ACTUALIDAD.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if isinstance(d.get("lesionados"), list):
            return [x for x in d["lesionados"] if isinstance(x, dict) and x.get("equipo") == equipo]
        por_eq = d.get("equipos", d)
        x = por_eq.get(equipo) if isinstance(por_eq, dict) else None
        if isinstance(x, dict):
            x = x.get("lesionados", [])
        return list(x) if isinstance(x, list) else []

    # ---------------------------------------------------------------------------------------------
    # todo junto
    # ---------------------------------------------------------------------------------------------
    def partido(self, fila) -> dict:
        """
        Contexto completo de un partido por jugar. `fila`: dict o renglón con local, visitante, fecha_utc
        y, si se conocen, id, fase, pierna, estadio_id (sin sede se usa la habitual del local).
        """
        g = fila.get if isinstance(fila, dict) else (lambda k, d=None: getattr(fila, k, d))
        loc, vis, f = g("local"), g("visitante"), _a_utc(g("fecha_utc"))
        sede = self._sede_de_id(g("id"), g("estadio_id"), loc, f)
        imputada = sede is None
        if imputada:
            sede = self.sede_habitual(loc)
        info = self.info_sede(sede)
        return {
            "id": None if g("id") is None else int(g("id")), "fecha": _dia(f), "torneo": g("torneo", self.torneo),
            "fase": g("fase"), "local": loc, "visitante": vis, "a_la_fecha": self.fecha.isoformat(),
            "equipo_local": self.equipo(loc), "equipo_visitante": self.equipo(vis),
            "historial": self.historial(loc, vis, sede),
            "sede": {**(info or {}), "sede_imputada": imputada,
                     "balance_local_3_anios": self.balance_local_en_sede(loc, sede, 3.0)},
            "descanso_local": self.descanso(loc, f), "descanso_visitante": self.descanso(vis, f),
            "viaje_visitante_km": self.viaje_km(vis, sede),
            "suspendidos_local": self.suspendidos(loc, f), "suspendidos_visitante": self.suspendidos(vis, f),
            "lesionados_local": self.lesionados(loc), "lesionados_visitante": self.lesionados(vis),
        }
