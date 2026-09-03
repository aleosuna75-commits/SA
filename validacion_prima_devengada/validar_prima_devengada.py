# -*- coding: utf-8 -*-
"""
================================================================================
 validar_prima_devengada.py · Validación del FND (MEC) contra la prima devengada REAL
--------------------------------------------------------------------------------
 Planeación Financiera (BP&A) · Reaseguradora Patria (GPV)

 PREGUNTA QUE RESPONDE
   ¿La prima devengada que produce el modelo (RRC = PT · FND · IS + gastos + MR,
   IRR = BEL · %cesión) cuadra con la prima devengada REAL?

 DEFINICIÓN DEL REAL (misma que Integración Dim, hoja ER_2026)
   Prima devengada tomada     = Prima emitida  − Δ RRC bruta   (tomada)
   Prima devengada retenida   = Prima retenida − Δ RRC neta    (bruta − IRR)
   con los saldos de la base BEL-IRR-MR (BD_Montos_RRC_SONR, en USD).

 QUÉ AÍSLA
   Todo lo que NO es FND (índice de siniestralidad, gasto, MR, % cesión) se toma del
   REAL mes a mes; así la única diferencia modelo–real es el factor de devengamiento
   y la prima base. Ratio modelo/real de la RRC == ratio de prima no devengada.

 VARIANTES DE FND QUE SE RECONSTRUYEN (por registro de prima de la BD del MEC)
   NT_reg_m  : Nota Técnica (24-avos) por antigüedad de REGISTRO, cuentas mensuales
               (tabla xPND 'NA' de los reforecast); no proporcional -> prorrata por cohorte
   NT_reg_t  : idem con cuentas trimestrales para proporcional (xPND '3')
   MEC_pub   : TablaFND publicada del MEC v2 (PF+): vector por antigüedad desde INICIO
               DE VIGENCIA; Vida con vector propio, resto vector de cartera
   MEC_prop  : PF+ con vector propio de cada ramo
   MEC_reg   : curva PF+ de cartera aplicada sobre la antigüedad de REGISTRO
   CAL       : calibrado: FND = max(0, NT(k_reg) − δ_ramo) para proporcional/facultativo,
               prorrata por cohorte para no proporcional; δ_ramo ajustado por mínimos
               cuadrados contra la prima no devengada real (202301–202605)

 UNIDADES: todo en USD (la base BEL-IRR-MR está en USD; la prima MXN de la BD se
 convierte al TC de cierre del mes de registro). El TC de 2019–2021 es aproximado
 (promedios Banxico) y sólo afecta colas anteriores a 2023.
================================================================================
"""
from __future__ import annotations
import os, sys, json
import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
INS = os.path.join(BASE, "insumos")
OUT = os.path.join(BASE, "salidas")
os.makedirs(OUT, exist_ok=True)

T0, T1 = 202201, 202605          # ventana con RRC real disponible
CAL0 = 202301                    # ventana de calibración / reporte (evita la rampa 2022)
CAL0_GRUPO = {"CAT": 202401}     # CAT: el índice TEV/Hidro sólo es consistente desde 2024
H = 72                           # horizonte de los vectores MEC

# ----------------------------------------------------------------------------
# Catálogo: ramo BD-MEC -> grupo de validación -> columnas RAM_ de la base real
# (40=RC, 50=MyT, 90=Autos, 110=Diversos: mapeo del script RRC / ER real; el
#  NOMBRE_RAMO de generar_output_mec.py tiene esos cuatro nombres cruzados)
# ----------------------------------------------------------------------------
GRUPOS = {
    "Vida":     dict(ramo=10,  ram=["RAM_10"],                  er=["Vida"]),
    "AyE":      dict(ramo=30,  ram=["RAM_30", "RAM_34", "RAM_37"], er=["Acc Per.", "GMM", "Salud"]),
    "RC":       dict(ramo=40,  ram=["RAM_40"],                  er=["Resp. Civil"]),
    "MyT":      dict(ramo=50,  ram=["RAM_50"],                  er=["MyT"]),
    "Incendio": dict(ramo=60,  ram=["RAM_60"],                  er=["Incendio"]),
    "CAT":      dict(ramo=70,  ram=["RAM_71", "RAM_73"],        er=["Terremoto", "HyORH"]),
    "Agro":     dict(ramo=80,  ram=["RAM_80"],                  er=["Agropecuario"]),
    "Autos":    dict(ramo=90,  ram=["RAM_90"],                  er=["Autos"]),
    "Credito":  dict(ramo=100, ram=["RAM_100"],                 er=["Crédito"]),
    "Diversos": dict(ramo=110, ram=["RAM_110"],                 er=["Diversos"]),
}
RAMO2GRUPO = {v["ramo"]: g for g, v in GRUPOS.items()}
# códigos de índice de siniestralidad por columna RAM (prioridad por fecha)
IS_CODES = {"RAM_10": ["10"], "RAM_30": ["31", "30"], "RAM_34": ["35", "34", "30"],
            "RAM_37": ["39", "37", "30"], "RAM_40": ["40"], "RAM_50": ["50"], "RAM_60": ["60"],
            "RAM_71": ["TEV"], "RAM_73": ["Hidro"], "RAM_80": ["80"], "RAM_90": ["90"],
            "RAM_100": ["100"], "RAM_110": ["110"]}
IS_CAT_DESDE = {"RAM_71": 202401, "RAM_73": 202401}   # primer mes con índice CAT en base consistente

# Nota Técnica / tabla xPND de los reforecast (antigüedad de registro 0..11, cuentas mensuales)
NT_M = np.array([0.95890411, 0.876712329, 0.791780822, 0.706849315, 0.624657534, 0.539726027,
                 0.457534247, 0.37260274, 0.295890411, 0.210958904, 0.126027397, 0.043835616])
DESP_TRIM = (3 - 1) / 2 * 30 / 365          # regla M4: (t−1)/2 · 30/365 → 0.0822 (verificada vs xPND '3')

# TC aproximado 2019–2021 (promedio mensual Banxico FIX, redondeado). Sólo afecta
# prima registrada antes de 2022 → reservas de 2022 y colas multianuales (Vida).
TC_APROX = {
    2019: [19.16, 19.20, 19.26, 18.97, 19.14, 19.30, 19.05, 19.65, 19.60, 19.36, 19.34, 19.11],
    2020: [18.83, 18.89, 22.37, 24.16, 23.42, 22.29, 22.44, 22.11, 21.71, 21.30, 20.42, 19.93],
    2021: [19.90, 20.30, 20.72, 20.02, 19.94, 20.05, 19.93, 20.07, 20.03, 20.51, 20.87, 20.85],
}


def midx(aaaamm) -> np.ndarray:
    a = np.asarray(aaaamm, dtype=np.int64)
    return (a // 100) * 12 + (a % 100 - 1)


def aaaamm(m: int) -> int:
    return (m // 12) * 100 + (m % 12 + 1)


def meses(t0, t1):
    return [aaaamm(m) for m in range(int(midx(t0)), int(midx(t1)) + 1)]


# ============================================================================
# 1 · INSUMOS
# ============================================================================
def cargar_tc() -> pd.Series:
    tc = pd.read_csv(os.path.join(INS, "tc_mensual_bd.csv")).set_index("Periodo")["TC"]
    extra = {y * 100 + i + 1: v for y, vals in TC_APROX.items() for i, v in enumerate(vals)}
    tc = pd.concat([pd.Series(extra), tc]).sort_index()
    return tc


def cargar_input(tc: pd.Series) -> pd.DataFrame:
    df = pd.read_csv(os.path.join(INS, "input_mec_bd.csv"))
    df = df[(df["Fuente"] == "BD") & (df["Origen"] == "Real") & (df["Periodo"] <= T1)].copy()
    df = df[df["Ramo"].isin(RAMO2GRUPO)].copy()          # fianzas (130–170) sin RRC en la base
    df["Grupo"] = df["Ramo"].map(RAMO2GRUPO)
    df["TC"] = df["Periodo"].map(tc)
    if df["TC"].isna().any():
        faltan = sorted(df.loc[df["TC"].isna(), "Periodo"].unique())
        raise SystemExit(f"Sin TC para los periodos {faltan}")
    df["P_USD"] = df["PrimaDevMes"] / df["TC"]
    df["m_reg"] = midx(df["Periodo"])
    df["m_coh"] = midx(df["CohorteAAAAMM"])
    return df.reset_index(drop=True)


def cargar_real() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (real por grupo × mes, IS efectivo) con:
    BEL, GTO, MR, IRR, BRUTO, NETO (USD), PND_real = Σ_sub BEL/IS, IS_eff = BEL/PND_real,
    g=GTO/BEL, mr=MR/BEL, c=IRR/BEL."""
    r = pd.read_csv(os.path.join(INS, "real_rrc_long.csv"))
    r = r[(r["PERIODO"] >= T0) & (r["PERIODO"] <= T1)]
    is_ = pd.read_csv(os.path.join(INS, "is_rrc_real.csv")).set_index("Fecha")
    is_.columns = [str(c).strip() for c in is_.columns]
    per = sorted(r["PERIODO"].unique())
    is_ = is_.reindex(per)
    # IS por columna RAM: primer código disponible por fecha, luego ffill/bfill
    is_ram = {}
    for ram, codes in IS_CODES.items():
        s = pd.Series(np.nan, index=per, dtype=float)
        for c in codes:
            if c in is_.columns:
                s = s.fillna(pd.to_numeric(is_[c], errors="coerce"))
        if ram in IS_CAT_DESDE:
            # TEV/Hidro: antes de 2024 el 'Ind Sin RRC' de HParametros está en otra base
            # (valores 0.5–8.6 frente a 0.11–0.27 desde 2024); se descarta y se rellena
            # hacia atrás con el primer valor consistente. El índice implícito
            # BEL/PND_modelo de CAT es estable (~0.30–0.33 en 2022), lo que confirma que
            # el problema está en el índice y no en el devengamiento.
            s[s.index < IS_CAT_DESDE[ram]] = np.nan
        s = s.replace(0, np.nan).ffill().bfill()
        is_ram[ram] = s
    is_ram = pd.DataFrame(is_ram)
    r = r.merge(is_ram.stack().rename("IS").reset_index().rename(columns={"level_0": "PERIODO", "level_1": "RAM"}),
                on=["PERIODO", "RAM"], how="left")
    r["PND_sub"] = r["RRC BEL"] / r["IS"]
    r["Grupo"] = r["RAM"].map({ram: g for g, v in GRUPOS.items() for ram in v["ram"]})
    r = r.dropna(subset=["Grupo"])
    g = (r.groupby(["Grupo", "PERIODO"])
          .agg(BEL=("RRC BEL", "sum"), GTO=("RRC GTO", "sum"), MR=("RRC MR", "sum"),
               IRR=("RRC IRR", "sum"), BRUTO=("RRC BRUTO", "sum"), NETO=("RRC NETO", "sum"),
               PND_real=("PND_sub", "sum")).reset_index())
    g["IS_eff"] = g["BEL"] / g["PND_real"]
    g["g"] = g["GTO"] / g["BEL"]
    g["mr"] = g["MR"] / g["BEL"]
    g["c"] = g["IRR"] / g["BEL"]
    return g, is_ram


def cargar_vectores() -> tuple[dict, np.ndarray, list]:
    v = pd.read_csv(os.path.join(INS, "mec_vectores_h72.csv"), index_col=0)
    cart = v.loc["CARTERA"].to_numpy(dtype=float)
    vec = {str(k): v.loc[k].to_numpy(dtype=float) for k in v.index if k != "CARTERA"}
    abiertos = ["10"]                      # decisión M3 del MEC v2: sólo Vida abre
    return vec, cart, abiertos


def cargar_cesion_er() -> pd.DataFrame:
    """% de prima cedida por grupo y año (ER real): para construir la prima retenida."""
    er = pd.read_csv(os.path.join(INS, "er_real_primas.csv"))
    out = {}
    for per, anio in [(202312, 2023), (202412, 2024), (202510, 2025)]:
        e = er[er["Periodo"] == per].set_index("Concepto")
        for g, spec in GRUPOS.items():
            pe = e.loc["PRIMA EMITIDA", spec["er"]].sum()
            ced = e.loc["(-) PRIMA CEDIDA / RETROCEDIDA", spec["er"]].sum()
            out[(g, anio)] = ced / pe if pe else 0.0
    ces = pd.Series(out).rename("ces").reset_index()
    ces.columns = ["Grupo", "Anio", "ces"]
    return ces


# ============================================================================
# 2 · MOTOR: prima no devengada por variante
# ============================================================================
def _vec_lookup(vec: np.ndarray, k: np.ndarray) -> np.ndarray:
    """Valor del vector en la antigüedad k (k<0 → 0; k≥len → 0, la cola ya es ~0)."""
    out = np.zeros(len(k))
    ok = (k >= 0) & (k < len(vec))
    out[ok] = vec[k[ok]]
    return out


def nt_desp(desp: float) -> np.ndarray:
    """Regla M4 del MEC: FND_t(k) = NT(k) − desp, acotado a [0, 1] (δ<0 no puede pasar de 100%)."""
    return np.clip(NT_M - desp, 0.0, 1.0)


class Motor:
    def __init__(self, inp: pd.DataFrame, vec: dict, cart: np.ndarray, abiertos: list):
        self.inp = inp
        self.vec, self.cart, self.abiertos = vec, cart, abiertos
        self.P = inp["P_USD"].to_numpy()
        self.mreg = inp["m_reg"].to_numpy()
        self.mcoh = inp["m_coh"].to_numpy()
        self.tipo = inp["TipoRea"].to_numpy()
        self.ramo = inp["Ramo"].to_numpy().astype(str)
        self.grupo = inp["Grupo"].to_numpy()
        self.grupos = sorted(GRUPOS)
        self.gidx = np.array([self.grupos.index(g) for g in self.grupo])
        self.vec_pub = {r: (vec[r] if r in abiertos else cart) for r in vec}

    def fnd(self, variante: str, t: int, params: dict | None = None) -> np.ndarray:
        k_reg = int(midx(t)) - self.mreg
        k_coh = int(midx(t)) - self.mcoh
        prop = self.tipo != 2                    # proporcional (1) y facultativo (3)
        f = np.zeros(len(self.P))
        if variante in ("NT_reg_m", "NT_reg_t", "CAL"):
            if variante == "NT_reg_m":
                f[prop] = _vec_lookup(NT_M, k_reg[prop])
            elif variante == "NT_reg_t":
                t1 = self.tipo == 1
                f[t1] = _vec_lookup(nt_desp(DESP_TRIM), k_reg[t1])
                t3 = self.tipo == 3
                f[t3] = _vec_lookup(NT_M, k_reg[t3])
            else:                                # CAL: δ por grupo
                for gi, g in enumerate(self.grupos):
                    m = prop & (self.gidx == gi)
                    f[m] = _vec_lookup(nt_desp(params["delta"][g]), k_reg[m])
            np_ = ~prop                          # no proporcional: prorrata por fechas ≈ PF+ cartera por cohorte
            f[np_] = _vec_lookup(self.cart, k_coh[np_])
        elif variante == "MEC_pub":
            for r, v in self.vec_pub.items():
                m = self.ramo == r
                f[m] = _vec_lookup(v, k_coh[m])
        elif variante == "MEC_prop":
            for r, v in self.vec.items():
                m = self.ramo == r
                f[m] = _vec_lookup(v, k_coh[m])
        elif variante == "MEC_reg":
            f = _vec_lookup(self.cart, k_reg)
        elif variante == "NT_reg_susc":
            # Diagnóstico del filtro de reforecastRRC: «año(mes registro) <= Susc» (la prima
            # positiva registrada en un año posterior al de suscripción queda fuera de la RRC).
            # Proxy: año de suscripción ≈ año de inicio de vigencia (la BD del MEC no trae Susc).
            f[prop] = _vec_lookup(NT_M, k_reg[prop])
            f[~prop] = _vec_lookup(self.cart, k_coh[~prop])
            tarde = (self.mreg // 12 > self.mcoh // 12) & (self.P > 0)
            f[tarde] = 0.0
        else:
            raise ValueError(variante)
        f[k_reg < 0] = 0.0                       # prima aún no registrada a la fecha de valuación
        return f

    def pnd(self, variante: str, params: dict | None = None) -> pd.DataFrame:
        rows = []
        for t in meses(T0, T1):
            f = self.fnd(variante, t, params)
            s = np.bincount(self.gidx, weights=self.P * f, minlength=len(self.grupos))
            rows.append(pd.Series(s, index=self.grupos, name=t))
        df = pd.DataFrame(rows)
        df.index.name = "PERIODO"
        return df

    def prima_emitida(self) -> pd.DataFrame:
        pe = self.inp.pivot_table(index="Periodo", columns="Grupo", values="P_USD", aggfunc="sum")
        return pe.reindex(meses(T0, T1)).fillna(0.0)


# ============================================================================
# 3 · COMPARACIÓN
# ============================================================================
def largo(pnd: pd.DataFrame, nombre: str) -> pd.DataFrame:
    x = pnd.stack().rename(nombre).reset_index()
    x.columns = ["PERIODO", "Grupo", nombre]
    return x


def comparar(real: pd.DataFrame, pe: pd.DataFrame, pnds: dict, ces: pd.DataFrame, tc: pd.Series) -> pd.DataFrame:
    """Tabla larga por grupo × mes con real y cada variante: PND, RRC bruta/neta, PD tomada/retenida."""
    base = real[["Grupo", "PERIODO", "BEL", "BRUTO", "NETO", "IRR", "PND_real", "IS_eff", "g", "mr", "c"]].copy()
    base = base.merge(largo(pe, "PE"), on=["PERIODO", "Grupo"], how="left")
    base["TC"] = base["PERIODO"].map(tc)
    base["Anio"] = base["PERIODO"] // 100
    base = base.merge(ces, on=["Grupo", "Anio"], how="left")
    base["ces"] = base.groupby("Grupo")["ces"].transform(lambda s: s.ffill().bfill())
    base["PR"] = base["PE"] * (1 - base["ces"])
    base = base.sort_values(["Grupo", "PERIODO"])
    base["dBRUTO_real"] = base.groupby("Grupo")["BRUTO"].diff()
    base["dNETO_real"] = base.groupby("Grupo")["NETO"].diff()
    base["PD_tom_real"] = base["PE"] - base["dBRUTO_real"]
    base["PD_ret_real"] = base["PR"] - base["dNETO_real"]
    for v, pnd in pnds.items():
        base = base.merge(largo(pnd, f"PND_{v}"), on=["PERIODO", "Grupo"], how="left")
        bel = base[f"PND_{v}"] * base["IS_eff"]
        base[f"BRUTO_{v}"] = bel * (1 + base["g"] + base["mr"])
        base[f"NETO_{v}"] = base[f"BRUTO_{v}"] - bel * base["c"]
        base[f"dBRUTO_{v}"] = base.groupby("Grupo")[f"BRUTO_{v}"].diff()
        base[f"dNETO_{v}"] = base.groupby("Grupo")[f"NETO_{v}"].diff()
        base[f"PD_tom_{v}"] = base["PE"] - base[f"dBRUTO_{v}"]
        base[f"PD_ret_{v}"] = base["PR"] - base[f"dNETO_{v}"]
    return base


def resumen_anual(cmp: pd.DataFrame, variantes: list) -> pd.DataFrame:
    """Prima devengada tomada y retenida por grupo y año: real vs variantes, con error."""
    c = cmp[cmp["PERIODO"] >= CAL0].copy()
    c["Anio"] = c["PERIODO"] // 100
    # equivalentes en MXN: Δreserva del mes × TC de cierre del mes (así lo lleva el ER:
    # el efecto cambiario del saldo no pasa por la variación de reserva)
    c["PE_MXN"] = c["PE"] * c["TC"]
    c["PD_tom_real_MXN"] = c["PD_tom_real"] * c["TC"]
    c["PD_ret_real_MXN"] = c["PD_ret_real"] * c["TC"]
    agg = {"PE": "sum", "PR": "sum", "PD_tom_real": "sum", "PD_ret_real": "sum",
           "dBRUTO_real": "sum", "dNETO_real": "sum", "PE_MXN": "sum",
           "PD_tom_real_MXN": "sum", "PD_ret_real_MXN": "sum"}
    for v in variantes:
        c[f"PD_tom_{v}_MXN"] = c[f"PD_tom_{v}"] * c["TC"]
        c[f"PD_ret_{v}_MXN"] = c[f"PD_ret_{v}"] * c["TC"]
        agg[f"PD_tom_{v}"] = "sum"; agg[f"PD_ret_{v}"] = "sum"
        agg[f"dBRUTO_{v}"] = "sum"; agg[f"dNETO_{v}"] = "sum"
        agg[f"PD_tom_{v}_MXN"] = "sum"; agg[f"PD_ret_{v}_MXN"] = "sum"
    a = c.groupby(["Grupo", "Anio"]).agg(agg).reset_index()
    tot = c.groupby("Anio").agg(agg).reset_index(); tot["Grupo"] = "TOTAL"
    a = pd.concat([a, tot], ignore_index=True)
    for v in variantes:
        a[f"err_tom_{v}"] = a[f"PD_tom_{v}"] - a["PD_tom_real"]
        a[f"err%_tom_{v}"] = a[f"err_tom_{v}"] / a["PD_tom_real"]
        a[f"err_ret_{v}"] = a[f"PD_ret_{v}"] - a["PD_ret_real"]
        a[f"err%_ret_{v}"] = a[f"err_ret_{v}"] / a["PD_ret_real"]
    return a


def metricas_pnd(cmp: pd.DataFrame, variantes: list) -> pd.DataFrame:
    """Ajuste de la prima no devengada (== RRC) por grupo: ratio medio modelo/real,
    MAPE mensual y R² sobre 202301–202605."""
    c = cmp[cmp["PERIODO"] >= CAL0]
    rows = []
    for g, d in list(c.groupby("Grupo")) + [("TOTAL", c.groupby("PERIODO").sum(numeric_only=True).reset_index())]:
        if g in CAL0_GRUPO:
            d = d[d["PERIODO"] >= CAL0_GRUPO[g]]
        r = d["PND_real"].to_numpy()
        for v in variantes:
            m = d[f"PND_{v}"].to_numpy()
            ok = r > 0
            rows.append(dict(Grupo=g, Variante=v,
                             ratio=m[ok].sum() / r[ok].sum(),
                             MAPE=np.mean(np.abs(m[ok] / r[ok] - 1)),
                             R2=1 - np.sum((m[ok] - r[ok]) ** 2) / np.sum((r[ok] - r[ok].mean()) ** 2),
                             PND_real_prom=r[ok].mean(), PND_mod_prom=m[ok].mean()))
    return pd.DataFrame(rows)


# ============================================================================
# 4 · CALIBRACIÓN: δ por grupo (regla M4 del MEC sobre antigüedad de registro)
# ============================================================================
def calibrar_delta(motor: Motor, real: pd.DataFrame, grid=None) -> tuple[dict, pd.DataFrame]:
    """Para cada grupo elige δ que minimiza Σ_t (PND_model − PND_real)² en la ventana
    de calibración. Como la contribución no proporcional no depende de δ, se separa."""
    if grid is None:
        grid = np.round(np.arange(-0.30, 0.601, 0.005), 3)
    tt = [t for t in meses(T0, T1) if t >= CAL0]
    prop = motor.tipo != 2
    # PND no proporcional (fijo) y prima proporcional por antigüedad de registro, por grupo y t
    fixed = {g: np.zeros(len(tt)) for g in motor.grupos}
    Pk = {g: np.zeros((len(tt), 12)) for g in motor.grupos}     # prima prop. registrada hace k meses
    for i, t in enumerate(tt):
        k_reg = int(midx(t)) - motor.mreg
        k_coh = int(midx(t)) - motor.mcoh
        fnp = np.zeros(len(motor.P))
        fnp[~prop] = _vec_lookup(motor.cart, k_coh[~prop])
        fnp[k_reg < 0] = 0
        s = np.bincount(motor.gidx, weights=motor.P * fnp, minlength=len(motor.grupos))
        for gi, g in enumerate(motor.grupos):
            fixed[g][i] = s[gi]
            m = prop & (motor.gidx == gi) & (k_reg >= 0) & (k_reg < 12)
            Pk[g][i] = np.bincount(k_reg[m], weights=motor.P[m], minlength=12)[:12]
    rr = real.set_index(["Grupo", "PERIODO"])["PND_real"]
    delta, filas = {}, []
    for g in motor.grupos:
        y = np.array([rr.get((g, t), np.nan) for t in tt])
        ok = ~np.isnan(y) & (np.array(tt) >= CAL0_GRUPO.get(g, CAL0))
        best = None
        for d in grid:
            f = nt_desp(d)
            m = fixed[g] + Pk[g] @ f
            sse = np.sum((m[ok] - y[ok]) ** 2)
            if best is None or sse < best[1]:
                best = (d, sse, m)
        d, sse, m = best
        delta[g] = float(d)
        r2 = 1 - sse / np.sum((y[ok] - y[ok].mean()) ** 2)
        filas.append(dict(Grupo=g, delta=d, meses_equiv_cuentas=1 + 2 * d * 365 / 30,
                          ratio=m[ok].sum() / y[ok].sum(), MAPE=np.mean(np.abs(m[ok] / y[ok] - 1)), R2=r2,
                          PND_real_prom=y[ok].mean(), ventana_desde=CAL0_GRUPO.get(g, CAL0)))
    return delta, pd.DataFrame(filas)


def tabla_fnd_calibrada(delta: dict) -> pd.DataFrame:
    rows = {}
    rows["NT mensual (referencia)"] = NT_M
    rows["NT trimestral (referencia)"] = nt_desp(DESP_TRIM)
    for g, d in delta.items():
        rows[f"{g} (ramo {GRUPOS[g]['ramo']}) δ={d:+.3f}"] = nt_desp(d)
    t = pd.DataFrame(rows).T
    t.columns = [f"k={k}" for k in range(12)]
    return t


# ============================================================================
# 5 · SALIDAS
# ============================================================================
def main():
    tc = cargar_tc()
    inp = cargar_input(tc)
    real, is_ram = cargar_real()
    vec, cart, abiertos = cargar_vectores()
    ces = cargar_cesion_er()
    motor = Motor(inp, vec, cart, abiertos)

    variantes = ["NT_reg_m", "NT_reg_t", "NT_reg_susc", "MEC_pub", "MEC_prop", "MEC_reg"]
    pnds = {v: motor.pnd(v) for v in variantes}
    delta, cal = calibrar_delta(motor, real)
    pnds["CAL"] = motor.pnd("CAL", dict(delta=delta))
    variantes.append("CAL")

    pe = motor.prima_emitida()
    cmp = comparar(real, pe, pnds, ces, tc)
    anual = resumen_anual(cmp, variantes)
    met = metricas_pnd(cmp, variantes)
    tabla = tabla_fnd_calibrada(delta)

    # ---- consola ----
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60)
    pd.set_option("display.float_format", lambda x: f"{x:,.4f}")
    print("\n=== δ calibrado por grupo (FND = max(0, NT(k_reg) − δ)) ===")
    print(cal.to_string(index=False))
    print("\n=== Ajuste de la prima no devengada (== RRC) por variante · ventana 202301–202605 ===")
    piv = met.pivot(index="Grupo", columns="Variante", values="ratio")[variantes]
    print("ratio Σmodelo/Σreal:\n" + piv.to_string())
    piv2 = met.pivot(index="Grupo", columns="Variante", values="MAPE")[variantes]
    print("MAPE mensual:\n" + piv2.to_string())
    print("\n=== Prima devengada TOMADA por año (USD) · real vs variantes · TOTAL ===")
    cols = ["Anio", "PE", "PD_tom_real"] + [f"PD_tom_{v}" for v in variantes] + [f"err%_tom_{v}" for v in variantes]
    print(anual[anual["Grupo"] == "TOTAL"][cols].to_string(index=False))
    print("\n=== Prima devengada RETENIDA por año (USD) · TOTAL ===")
    cols = ["Anio", "PR", "PD_ret_real"] + [f"PD_ret_{v}" for v in variantes] + [f"err%_ret_{v}" for v in variantes]
    print(anual[anual["Grupo"] == "TOTAL"][cols].to_string(index=False))

    # ---- archivos ----
    cmp.to_csv(os.path.join(OUT, "comparacion_mensual.csv"), index=False)
    anual.to_csv(os.path.join(OUT, "prima_devengada_anual.csv"), index=False)
    met.to_csv(os.path.join(OUT, "metricas_pnd.csv"), index=False)
    cal.to_csv(os.path.join(OUT, "calibracion_delta.csv"), index=False)
    tabla.to_csv(os.path.join(OUT, "tabla_fnd_calibrada.csv"))
    with open(os.path.join(OUT, "delta_calibrado.json"), "w") as f:
        json.dump(delta, f, indent=2)
    escribir_excel(cmp, anual, met, cal, tabla, variantes, real, is_ram, delta)
    print(f"\nSalidas en {OUT}")
    return cmp, anual, met, cal, tabla


def escribir_excel(cmp, anual, met, cal, tabla, variantes, real, is_ram, delta):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter as GCL
    VERDE, VERDE2, BLANCO, GRIS, CLARO, ROJO = 'FF00573F', 'FF2E7D53', 'FFFFFFFF', 'FFF2F2EE', 'FFE8F1EA', 'FFA6192E'
    wb = Workbook(); wb.remove(wb.active)

    def hoja(nombre, titulo, sub, df, nf=None, ancho=14):
        ws = wb.create_sheet(nombre)
        n = max(len(df.columns), 4)
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n)
        c = ws.cell(1, 1, titulo); c.font = Font(bold=True, color=BLANCO, size=12); c.fill = PatternFill('solid', fgColor=VERDE)
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n)
        c = ws.cell(2, 1, sub); c.font = Font(italic=True, color=BLANCO, size=9); c.fill = PatternFill('solid', fgColor=VERDE2)
        for j, col in enumerate(df.columns, 1):
            c = ws.cell(3, j, str(col)); c.font = Font(bold=True, color=BLANCO); c.fill = PatternFill('solid', fgColor=VERDE)
            c.alignment = Alignment('center', 'center', wrap_text=True)
            ws.column_dimensions[GCL(j)].width = ancho
        ws.row_dimensions[3].height = 32
        for i, row in enumerate(df.itertuples(index=False), 4):
            for j, v in enumerate(row, 1):
                if isinstance(v, (float, np.floating)) and (np.isnan(v) or np.isinf(v)):
                    v = None
                c = ws.cell(i, j, v)
                col = str(df.columns[j - 1])
                if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool):
                    if col.startswith("err%") or col in ("ratio", "MAPE", "R2", "IS_eff", "g", "mr", "c", "ces") or col.startswith("k="):
                        c.number_format = '0.00%'
                    elif col == "delta":
                        c.number_format = '0.000'
                    elif col in ("PERIODO", "Anio"):
                        c.number_format = '0'
                    else:
                        c.number_format = '#,##0'
                    if col.startswith("err%") and abs(v) > 0.02:
                        c.font = Font(color=ROJO, bold=True)
                if i % 2 == 0:
                    c.fill = PatternFill('solid', fgColor=GRIS)
        ws.freeze_panes = 'A4'
        return ws

    # Resumen ejecutivo
    res = []
    tot = anual[anual["Grupo"] == "TOTAL"]
    for v in variantes:
        for lado, lab in [("tom", "Tomada"), ("ret", "Retenida")]:
            for _, r in tot.iterrows():
                res.append(dict(Variante=v, Lado=lab, Anio=int(r["Anio"]),
                                PD_real=r[f"PD_{lado}_real"], PD_modelo=r[f"PD_{lado}_{v}"],
                                error=r[f"err_{lado}_{v}"], **{"err%": r[f"err%_{lado}_{v}"]},
                                PD_real_MXN=r[f"PD_{lado}_real_MXN"], PD_modelo_MXN=r[f"PD_{lado}_{v}_MXN"]))
    res = pd.DataFrame(res)
    hoja("Resumen", "PRIMA DEVENGADA · REAL vs MODELO · TOTAL CARTERA (USD y MXN, sin fianzas)",
         "Real: prima emitida − ΔRRC bruta (tomada); prima retenida − ΔRRC neta (retenida), saldos base BEL-IRR-MR. "
         "Modelo: misma fórmula con RRC reconstruida = PND_modelo · IS · (1+g+mr) e IRR = BEL·c, con IS, g, mr, c reales. "
         "2026 = enero–mayo. MXN = Δ mensual × TC de cierre.",
         res)
    # Gráficas (openpyxl nativo) sobre los totales mensuales
    from openpyxl.chart import LineChart, Reference, Series
    from openpyxl.drawing.line import LineProperties
    tt = cmp[cmp["PERIODO"] >= CAL0].groupby("PERIODO")[["PND_real", "PND_NT_reg_m", "PND_MEC_pub", "PND_CAL", "BRUTO", "BRUTO_CAL", "BRUTO_MEC_pub"]].sum().reset_index()
    tt.columns = ["PERIODO", "PND real (BEL/IS)", "PND NT registro mensual", "PND MEC publicado (cohorte vigencia)", "PND calibrado δ",
                  "RRC bruta real", "RRC bruta calibrado δ", "RRC bruta MEC publicado"]
    ws = hoja("Graficas", "SERIES MENSUALES · TOTAL CARTERA (USD)", "Prima no devengada implícita y RRC bruta: real vs variantes", tt, ancho=16)
    n = len(tt) + 3
    for (c1, c2, titulo, anchor) in [(2, 5, "Prima no devengada: real vs modelo", "K4"), (6, 8, "RRC bruta: real vs modelo", "K26")]:
        ch = LineChart(); ch.title = titulo; ch.height = 10; ch.width = 22
        ch.y_axis.numFmt = '#,##0'; ch.x_axis.delete = False; ch.y_axis.delete = False
        for col, color in zip(range(c1, c2 + 1), ["1F4E79", "C9A961", "A6192E", "00573F", "5B2C6F"]):
            sr = Series(Reference(ws, min_col=col, min_row=3, max_row=n), title_from_data=True)
            sr.graphicalProperties.line = LineProperties(solidFill=color, w=20000); sr.smooth = False
            ch.series.append(sr)
        ch.set_categories(Reference(ws, min_col=1, min_row=4, max_row=n))
        ws.add_chart(ch, anchor)
    hoja("PD_anual_por_ramo", "PRIMA DEVENGADA POR RAMO Y AÑO · REAL vs VARIANTES (USD)",
         "err% = (modelo − real) / real. 2026 = enero–mayo.", anual, ancho=15)
    hoja("Ajuste_PND", "AJUSTE DE LA PRIMA NO DEVENGADA (≡ RRC) POR VARIANTE · 202301–202605",
         "ratio = Σ PND modelo / Σ PND real · MAPE = error absoluto medio mensual · R² sobre la serie mensual", met)
    hoja("Calibracion", "CALIBRACIÓN δ POR RAMO · FND = max(0, NT(k_registro) − δ) para proporcional/facultativo",
         "δ es el desplazamiento de la regla M4 del MEC (frecuencia de cuentas): δ = (t−1)/2·30/365 → t = 1 + 2δ·365/30 meses equivalentes",
         cal)
    t2 = tabla.reset_index().rename(columns={"index": "Vector"})
    hoja("TablaFND_calibrada", "TABLA FND CALIBRADA · % NO DEVENGADO POR ANTIGÜEDAD DE REGISTRO (k=0 mes de registro)",
         "Se aplica a proporcional y facultativo; el no proporcional sigue con prorrata exacta por fechas de vigencia.", t2, ancho=11)
    cols = ["Grupo", "PERIODO", "PE", "PR", "PND_real", "BRUTO", "NETO"] + [f"PND_{v}" for v in variantes] + \
           [f"BRUTO_{v}" for v in variantes] + ["PD_tom_real", "PD_ret_real"] + [f"PD_tom_{v}" for v in variantes] + [f"PD_ret_{v}" for v in variantes]
    hoja("Mensual", "DETALLE MENSUAL POR RAMO (USD)", "PND = prima no devengada implícita (BEL/IS real) vs modelo; BRUTO = RRC bruta; PD = prima devengada", cmp[cols], ancho=13)
    hoja("Real_parametros", "PARÁMETROS REALES USADOS (por ramo × mes)",
         "IS_eff = BEL/PND implícita · g = gastos/BEL · mr = MR/BEL · c = IRR/BEL", real, ancho=13)
    sup = pd.DataFrame({"Supuesto": [
        "Prima base: BD del MEC (PrimasNal, Tipo Póliza P*), fuente BD, origen Real, 201901–202605; fianzas (130–170) excluidas por no tener RRC en la base.",
        "Conversión a USD al TC de cierre del mes de registro (base BEL-IRR-MR 2022+; 2019–2021 promedios Banxico aproximados).",
        "Real = saldos BD_Montos_RRC_SONR (USD). AyE = RAM_30+34+37; CAT = RAM_71+73. Índices de siniestralidad: HParametros 'Real' (31/35/39 y 30/34/37 según fecha; TEV/Hidro para CAT con relleno de huecos).",
        "Prima no devengada real implícita = Σ BEL_subramo / IS_subramo. IS efectivo, gasto, MR y % cesión se toman del real mes a mes.",
        "Prima retenida = prima emitida × (1 − % cedido anual del ER real por ramo: 2023, 2024, 2025 YTD oct; 2026 usa 2025).",
        "No proporcional (TipoRea 2): la BD del MEC no trae fin de vigencia por registro; se usa la curva PF+ de cartera por antigüedad de cohorte como proxy de la prorrata exacta.",
        "Antigüedad de registro k_reg = mes de valuación − mes de registro (Periodo). Antigüedad de cohorte k_coh = mes de valuación − mes de inicio de vigencia.",
        f"Ventana de calibración y reporte: {CAL0}–{T1}. Vectores MEC: m2_fnd_prorrata sobre Registros_Vigencia_MEC.csv, horizonte {H} meses; abre sólo Vida (decisión M3).",
    ]})
    hoja("Supuestos", "SUPUESTOS Y FUENTES", "", sup, ancho=160)
    wb.save(os.path.join(OUT, "Validacion_Prima_Devengada.xlsx"))


if __name__ == "__main__":
    main()
