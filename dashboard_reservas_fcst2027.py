# -*- coding: utf-8 -*-
"""
PRISMA · Proyección de Reservas FCST 2027   (Plotly Dash)
=========================================================
Lee BD_RFV_Proyeccion (hoja BD_Montos_RRC_SONR) y muestra la mensualización,
la estacionalidad (reserva vs. prima, año por año) y los montos.
Los filtros (Concepto, Variable, Ramo, Año, Mes, Unidades) están en un panel
que se abre con el botón "Filtros". El botón "Descargar Excel" baja un libro
con una pestaña por sección del tablero.

CÓMO EJECUTARLO DESDE VS CODE
    1) Abre este archivo en VS Code.
    2) Dale "Run Python File" (▶ arriba a la derecha) o en la terminal:
           python dashboard_reservas_fcst2027.py
    3) La primera vez instala solo los paquetes que falten (dash, plotly, pandas,
       openpyxl, xlsxwriter) y abre el dashboard en el navegador
       (http://127.0.0.1:8050). Para detenerlo: Ctrl + C en la terminal.
"""

import importlib.util
import subprocess
import sys

# --------------------------------------------------------------------------------------
# 1) Paquetería: se instala sola si falta (Dash 4 o superior)
# --------------------------------------------------------------------------------------
def _instalar(*paquetes):
    print(f"Instalando: {', '.join(paquetes)} ...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", *paquetes])


_faltan = [p for m, p in {"plotly": "plotly", "pandas": "pandas", "openpyxl": "openpyxl",
                           "xlsxwriter": "xlsxwriter"}.items() if importlib.util.find_spec(m) is None]
if importlib.util.find_spec("dash") is None:
    _faltan.append("dash>=4")
else:
    import dash as _d
    if int(_d.__version__.split(".")[0]) < 4:
        _faltan.append("dash>=4")
if _faltan:
    _instalar(*_faltan)
    if any(p.startswith("dash") for p in _faltan) and "dash" in sys.modules:
        print("Dash se actualizó. Vuelve a ejecutar el script.")
        sys.exit(0)

# --------------------------------------------------------------------------------------
# 2) App
# --------------------------------------------------------------------------------------
import base64
import glob
import io
import os
import re
import threading
import webbrowser
from datetime import datetime
from urllib.parse import quote

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, ctx, dcc, html, no_update
from plotly.subplots import make_subplots

# ---- Ruta del archivo -----------------------------------------------------------------
CARPETA = (r"C:\Users\asunad\OneDrive - GPV\Archivos de Maria Osmara Camacho Lopez - "
           r"Planeación Financiera\Presupuestos\2027\5_Generacion\4_Reservas\Outputs")
PATRON = "BD*RFV*Proyeccion*.xls*"      # acepta "BD_RFV_Proyeccion", "BD_ RFV_Proyeccion", etc.
HOJA = "BD_Montos_RRC_SONR"
PUERTO = 8050

# ---- Catálogos ------------------------------------------------------------------------
VARIABLES = {  # prefijo de la columna en la BD -> etiqueta en pantalla
    "RAM": "Reserva",
    "PRIMA 24M": "Prima 24M",
    "PR 24M": "PR 24M",
    "MA": "Monto afianzado (MA)",
    "RFV MA": "RFV MA",
    "CESION": "Cesión",
    "PT": "Prima del mes (PT)",
}
DETALLE = ["RAM", "PRIMA 24M", "PR 24M", "MA", "RFV MA", "CESION"]
PRIMAS = {"PT": "Prima del mes (PT)", "PRIMA 24M": "Prima 24M"}
FLUJOS = {"PT"}            # se acumulan en el año; el resto son saldos (se toma el cierre)
RATIOS = {"CESION"}        # porcentajes: promedio ponderado por la reserva
MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
UNIDADES = {"Pesos": (1, ""), "Miles": (1e3, " K"), "Millones": (1e6, " M")}
CONCEPTOS_ORDEN = ["RCONT", "RFV BRUTO", "RFV IRR", "RFV NETO"]

# ---- Paleta: neutra y sobria. Azul marino = dato principal; naranja = prima / referencia.
T = dict(
    bg="#e9eaef", card="#ffffff", navy="#2f3a5f", navy2="#3c4565", text="#1f2433", text2="#5b6275",
    text3="#8b90a0", grid="#eef0f4", linea="#dfe2ea",
    acento="#f08a3c", acento_suave="#f8c9a2",
    pos="#2e9e6b", neg="#d64545",
    anios=["#2f3a5f", "#7d8bc0", "#c0c6dc", "#a3a9b8"],          # año más reciente = más oscuro
    ramos=["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#c44f8a"],
    conceptos={"RCONT": "#9aa3c0", "RFV BRUTO": "#eb6834", "RFV IRR": "#1baf7a", "RFV NETO": "#2f3a5f"},
    heat=["#f3f4f8", "#d3d8ea", "#9ba5cf", "#5d6aa3", "#2f3a5f"],
)


# ---- Carga de datos -------------------------------------------------------------------
def buscar_archivo():
    for carpeta in (os.environ.get("RFV_CARPETA"), CARPETA, os.path.dirname(os.path.abspath(__file__))):
        if carpeta and os.path.isdir(carpeta):
            c = [f for f in glob.glob(os.path.join(carpeta, PATRON)) if not os.path.basename(f).startswith("~$")]
            if c:
                return max(c, key=os.path.getmtime)
    return None


def cargar(contenido: bytes) -> pd.DataFrame:
    raw = pd.read_excel(io.BytesIO(contenido), sheet_name=HOJA, header=None)
    fila = raw.index[raw.apply(lambda r: r.astype(str).str.strip().eq("CONCEPTO").any(), axis=1)][0]
    raw.columns = [str(c).strip() for c in raw.iloc[fila]]
    raw = raw.iloc[fila + 1:]
    raw = raw.loc[:, [c for c in raw.columns if c not in ("nan", "None")]]
    raw = raw.dropna(subset=["CONCEPTO", "PERIODO"])
    raw["PERIODO"] = pd.to_numeric(raw["PERIODO"], errors="coerce")
    raw = raw.dropna(subset=["PERIODO"])
    raw["PERIODO"] = raw["PERIODO"].astype(int)
    raw["CONCEPTO"] = raw["CONCEPTO"].astype(str).str.strip()
    raw = raw[~raw["CONCEPTO"].str.upper().str.startswith("BACKTESTING")]     # sin backtesting

    patron = re.compile(r"^(.+?)[ _](\d{3})$")
    cols_val = [c for c in raw.columns if patron.match(c)]
    df = raw.melt(id_vars=["CONCEPTO", "PERIODO"], value_vars=cols_val, var_name="COL", value_name="VALOR")
    ext = df["COL"].str.extract(patron)
    df["VARIABLE"] = ext[0].str.strip()
    df["RAMO"] = ext[1]
    df = df[df["VARIABLE"].isin(VARIABLES)]
    df["VALOR"] = pd.to_numeric(df["VALOR"], errors="coerce")      # "N/A" -> vacío
    df["ANIO"] = df["PERIODO"] // 100
    df["MES"] = df["PERIODO"] % 100
    df["FECHA"] = pd.to_datetime(dict(year=df["ANIO"], month=df["MES"], day=1))
    return df.drop(columns="COL").reset_index(drop=True)


ESTADO = {"df": None, "origen": "", "error": ""}
_arch = buscar_archivo()
if _arch:
    with open(_arch, "rb") as fh:            # se lee en memoria: funciona aunque esté abierto en Excel
        ESTADO["df"] = cargar(fh.read())
    ESTADO["origen"] = os.path.basename(_arch)
else:
    ESTADO["error"] = f"No encontré un archivo con el patrón {PATRON} en: {CARPETA}. Cárgalo desde Filtros › Archivo."
    ESTADO["df"] = pd.DataFrame(columns=["CONCEPTO", "PERIODO", "VALOR", "VARIABLE", "RAMO", "ANIO", "MES", "FECHA"])


def catalogos(df):
    presentes = list(dict.fromkeys(df["CONCEPTO"]))
    conceptos = [c for c in CONCEPTOS_ORDEN if c in presentes] + [c for c in presentes if c not in CONCEPTOS_ORDEN]
    return conceptos, sorted(df["RAMO"].unique()), sorted(int(a) for a in df["ANIO"].unique())


# ---- Cálculos (los usan las gráficas y la descarga a Excel) ----------------------------
def filtrar(df, conc, variable, ramos, anios, meses):
    return df[(df["CONCEPTO"] == conc) & (df["VARIABLE"] == variable) & df["RAMO"].isin(ramos)
              & df["ANIO"].isin(anios) & df["MES"].isin(meses)]


def serie(df, conc, variable, ramos, anios, meses, por=("FECHA",)):
    """Suma por ramo; para Cesión, promedio ponderado por la reserva (RAM) del mismo concepto."""
    por = list(por)
    d = filtrar(df, conc, variable, ramos, anios, meses)
    if variable in RATIOS:
        w = filtrar(df, conc, "RAM", ramos, anios, meses)[["PERIODO", "RAMO", "VALOR"]].rename(columns={"VALOR": "W"})
        d = d.merge(w, on=["PERIODO", "RAMO"], how="left").dropna(subset=["VALOR"])
        d["VW"] = d["VALOR"] * d["W"].fillna(0)
        g = d.groupby(por, as_index=False).agg(VW=("VW", "sum"), W=("W", "sum"), M=("VALOR", "mean"))
        g["VALOR"] = (g["VW"] / g["W"]).where(g["W"] > 0, g["M"])
        return g[por + ["VALOR"]]
    return d.groupby(por, as_index=False)["VALOR"].sum(min_count=1)


def indice(df, conc, variable, ramos, anios, meses):
    """Índice estacional: cada mes ÷ promedio de los meses filtrados de su año. Filas = año."""
    s = serie(df, conc, variable, ramos, anios, meses, por=("ANIO", "MES"))
    piv = s.pivot(index="ANIO", columns="MES", values="VALOR").reindex(index=anios, columns=meses)
    prom = piv.mean(axis=1).replace(0, np.nan)
    return piv.div(prom, axis=0)


def fmt(v, unidad, ratio=False, dec=1):
    if v is None or pd.isna(v):
        return "N/A"
    if ratio:
        return f"{v * 100:,.{dec}f}%"
    div, suf = UNIDADES[unidad]
    return f"${v / div:,.{dec if unidad != 'Pesos' else 0}f}{suf}"


def mes_txt(p):
    return f"{MESES[p % 100 - 1]} {p // 100}"


def datos_kpis(df, concepto, ramos, anios, meses):
    """Lista de indicadores: valor actual, año anterior, variación y referencia."""
    anios_todos = catalogos(df)[2]
    salida = []
    for variable in ["RAM", "PRIMA 24M", "PR 24M", "MA", "RFV MA", "CESION", "PT"]:
        r = variable in RATIOS
        if variable in FLUJOS:
            act = serie(df, concepto, variable, ramos, anios[-1:], meses)["VALOR"].sum()
            prev_s = serie(df, concepto, variable, ramos, [anios[-1] - 1], meses)
            prev = prev_s["VALOR"].sum() if not prev_s.empty else None
            ref = f"Acumulado {anios[-1]}"
        else:
            s = serie(df, concepto, variable, ramos, anios_todos, list(range(1, 13)), por=("PERIODO",))
            s = s.dropna(subset=["VALOR"]).set_index("PERIODO")["VALOR"]
            dentro = [p for p in s.index if p // 100 in anios and p % 100 in meses]
            act = prev = None
            ref = "Sin dato"
            if dentro:
                p = max(dentro)
                act, prev = s.get(p), s.get(p - 100)
                ref = f"Saldo al cierre de {mes_txt(p)}"
        var = None
        if act is not None and prev is not None and not pd.isna(prev) and prev != 0:
            var = (act - prev) if r else (act / prev - 1)
        salida.append(dict(variable=variable, nombre=VARIABLES[variable], ratio=r, actual=act, anterior=prev,
                           variacion=var, referencia=ref))
    return salida


def datos_por_ramo(df, concepto, var, ramos, anios, meses, per_txt):
    base = filtrar(df, concepto, var, ramos, anios, meses)
    if var in RATIOS:
        pmax = base["PERIODO"].max()
        comp = serie(df, concepto, var, ramos, anios, meses, por=("PERIODO", "RAMO"))
        comp = comp[comp["PERIODO"] == pmax][["RAMO", "VALOR"]]
        titulo = f"Por ramo · cierre {mes_txt(pmax)}" if pd.notna(pmax) else "Por ramo"
    elif var in FLUJOS:
        comp = base.groupby("RAMO", as_index=False)["VALOR"].sum()
        titulo = f"Por ramo · acumulado {per_txt}"
    else:
        pmax = base["PERIODO"].max()
        comp = base[base["PERIODO"] == pmax].groupby("RAMO", as_index=False)["VALOR"].sum()
        titulo = f"Por ramo · cierre {mes_txt(pmax)}" if pd.notna(pmax) else "Por ramo"
    comp = comp.dropna()
    total = comp["VALOR"].sum()
    comp["PART"] = comp["VALOR"] / total if (total and var not in RATIOS) else np.nan
    return comp.sort_values("VALOR"), titulo


def datos_lectura(iv, ip, meses):
    xm = [MESES[m - 1] for m in meses]
    filas = []
    for a in iv.index:
        v_, p_ = iv.loc[a], ip.loc[a]
        ok = v_.notna() & p_.notna()
        corr = v_[ok].corr(p_[ok]) if ok.sum() > 2 else np.nan
        filas.append(dict(
            Año=int(a), Correlación=corr,
            **{"Mes pico variable": xm[int(np.nanargmax(v_.values))] if v_.notna().any() else "—",
               "Mes pico prima": xm[int(np.nanargmax(p_.values))] if p_.notna().any() else "—",
               "Amplitud variable": (v_.max() - v_.min()) if v_.notna().any() else np.nan,
               "Amplitud prima": (p_.max() - p_.min()) if p_.notna().any() else np.nan}))
    return pd.DataFrame(filas)


def tabla_mensual(df, concepto, var, ramos, anios, meses):
    d = filtrar(df, concepto, var, ramos, anios, meses)
    tab = d.pivot_table(index="PERIODO", columns="RAMO", values="VALOR", aggfunc="sum")
    tab.columns = [f"Ramo {c}" for c in tab.columns]
    tab["Total"] = serie(df, concepto, var, ramos, anios, meses, por=("PERIODO",)).set_index("PERIODO")["VALOR"]
    return tab


# ---- Estilo de gráficas ---------------------------------------------------------------
GRAPH_CFG = {"displaylogo": False, "displayModeBar": "hover",
             "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d", "zoomIn2d", "zoomOut2d"],
             "toImageButtonOptions": {"format": "png", "scale": 2}}
FUENTE = "Inter, system-ui, -apple-system, 'Segoe UI', sans-serif"


def estilo(fig, h, ytitle=None, ratio=False, leyenda=True, ytick=None, compacto=False):
    fig.update_layout(
        height=h, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FUENTE, color=T["text2"], size=12),
        margin=dict(l=8, r=12, t=30 if leyenda else 8, b=8),
        hovermode="x unified", showlegend=leyenda,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, font=dict(color=T["text2"], size=12),
                    traceorder="normal", bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor="#ffffff", font=dict(color=T["text"], family=FUENTE), bordercolor=T["linea"]),
        bargap=0.3, uniformtext=dict(minsize=9, mode="hide"),
    )
    fig.update_xaxes(showgrid=False, linecolor=T["linea"], tickfont=dict(color=T["text3"]), zeroline=False,
                     fixedrange=True)
    fig.update_yaxes(gridcolor=T["grid"], zeroline=False, tickfont=dict(color=T["text3"]), title=ytitle,
                     title_font=dict(color=T["text3"], size=11), fixedrange=True,
                     tickformat=ytick if ytick is not None else (".1%" if ratio else ",.0f"))
    _meses_es(fig, 4 if compacto else 15)
    return fig


def _meses_es(fig, max_ticks=15):
    """Etiquetas de mes en español en los ejes de fecha."""
    fechas = set()
    for tr in fig.data:
        xs = getattr(tr, "x", None)
        if xs is not None and len(xs) and isinstance(xs[0], (pd.Timestamp, datetime, np.datetime64)):
            fechas.update(pd.to_datetime(list(xs)))
    if fechas:
        fechas = sorted(fechas)
        vals = fechas[::max(1, -(-len(fechas) // max_ticks))]
        fig.update_xaxes(tickvals=vals, ticktext=[f"{MESES[f.month - 1]}<br>{f.year}" for f in vals], tickangle=0)


def vacia(msg="Selecciona al menos un ramo, un año y un mes en Filtros", h=320):
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False, font=dict(color=T["text3"], size=13))
    fig.update_layout(height=h, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      margin=dict(l=10, r=10, t=10, b=10))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def color_anio(a, anios_sel):
    orden = sorted(anios_sel, reverse=True)
    return T["anios"][min(orden.index(a), len(T["anios"]) - 1)] if a in orden else T["text3"]


def color_ramo(r, ramos_todos):
    return T["ramos"][ramos_todos.index(r) % len(T["ramos"])] if r in ramos_todos else T["text3"]


# ---- Íconos (trazos tipo Feather, MIT) -------------------------------------------------
_ICONOS = {
    "home": '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
    "barras": '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
    "onda": '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    "capas": '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
    "grid": '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>',
    "tabla": '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>',
    "filtro": '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>',
    "bajar": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
    "x": '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    "escudo": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "reloj": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "pie": '<path d="M21.21 15.89A10 10 0 1 1 8 2.83"/><path d="M22 12A10 10 0 0 0 12 2v10z"/>',
    "maletin": '<rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>',
    "sube": '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>',
    "cesion": '<polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/>',
    "peso": '<line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
    "subir": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
}
CSS_ICONOS = "\n".join(
    ".ic-%s{-webkit-mask:url(\"data:image/svg+xml,%s\") center/contain no-repeat;mask:url(\"data:image/svg+xml,%s\") center/contain no-repeat;}"
    % (k, q, q) for k, q in ((k, quote("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' "
                                       "stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>"
                                       + v + "</svg>")) for k, v in _ICONOS.items()))
# Logo de Patria (PNG embebido para que el script funcione solo)
LOGO_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAEIAAABwCAYAAACq5qZOAAALNElEQVR42u2dbZBcVZnHf88553b3JBLLl6V2i6XKl/0gVvm2WK5b"
    "WzGgLoWat8HqscoXmJkkQ1VcBRYDJhFuGizMgmJRsqUTiEnA17RkJglS7oq6LFsuoq5UKa64WBSrBQuriAbSL/ec8/jh9nRmYICZ"
    "ZKZnMt33c8/0vb/7/z/3/5xz7mlhQY7UUP65UK0GyvsLZEcGQF6HcU8i8RC3Dd6ff0wNFYmdOCPpOIPyfkt1IACw7osrMSbFmHeA"
    "ARGI2aMEvZYnX3Ejd53t88+XI4guDRBpaqjsUBDl3Xv+nCJbUP6BpFTA1xVFQcE6gzjwjTvRbAsHR+479veVeBKDUKFcNW0VrN/9"
    "QYxLscW/wtdBY0DETvp8DsWVDDF7khg/TbL8OqoDzflUh3TMBmv2vp6EFLHnARCygEz4YTp+GjDWYhIIzbuJ8eMcHP7+s/7vogaR"
    "pgaASiWyenQZrvAxxFyEK7wUX1NUNIfwgmpSlIgrWULzaYifw2U7qV74hylWW4QghPL+Yzbov3kt4rZiC28lZBDDM2wwU3dpxBiD"
    "LUJo/BeEyzmw4c65VMfcgZj8qCvveiWZuxIxg9gEfOP5bTBDGrk6CpboPTHeyNFwNf+66QlIDZyYOmROimGKUJHIuTcUKZ2yCTGX"
    "4Uqn5zZQRcTMXe3ViIjBlSA0fob67YxtPHSi6pC5s8Gut0JyLa60MreBDy0A81CHJqsjRFT3EPyVHNr4yJT6NO8gJj/T+0f/AoqX"
    "ApuxSd/c2GCmPIgIhqQEWeN/MKTcNvjVSeqIgM4DiGkygdgKrvgqfGOaTNCRQ1GN2MQiQPBfQsInOLDx4dkEseO7a+/d9yaiphiz"
    "DmSaTKCzeETOqTrAlQyh8RvQHRwY2j1TdcisLFQeXYEvfBRkC65wSh6Np1xwfneMtYiB4COi0hGbTA5i1lnEQsgOo9nljG/6b0BI"
    "U3kudZgZ1gQBFF+4gb6XXIXqcnzdg0gbghIBIemzxPgE0T+EKxrECaphpl498SQjlhAioRlxxTWY5N/o33sJZ446KpVIeb8FleMD"
    "UdmRX4Sab1D7w/0kRYNYh2pAiagGXGIwFrL617FyNri/wze2QvgdSZ8FBNXYGRgYwJDVAiKn4grXc3rxEP1f/Ou8vonmQI6vRuSq"
    "WL/vZYheAnwUVzyF6ME4CM37IH6S2wYPIJOCzerR1+CSrYj5ADax+EZE6KBdWo/apGTxzSMQd7JCrmffUH1yTJ/dyUyuwOv2vBHR"
    "T2LdqwnxENnRnXxz8+/bn12VOjgL7jrb50+YvecguhNXfNMJxe0TqR3GWmwBfP37qPkY4xf858R1HcddUaE8YKhWA6iw5uZTObzp"
    "sfxi951B0veX+PqjjJ3/MwDOHE348SMBKpFzb11BXxgBLscVXz67BmzO1KG4oiH6p1H9HMFfw6GNR45fnqtSx1nEvACNvhiffBjM"
    "JdjCywmNP6LsJvnjp6he9P+AMDLq2HVhBsDa3a/FmCsx9n0YA77ZuRA2pYkr5eogXizHVYomR+u1e9diuQJXfDOhCTFEjDXYAoTG"
    "A6DXYZfvpToQKO+3PP5n0rbLuj3rMWYrLnlL5+0yUTv6LFltxyxrxKQOc82uV2KTKzB2CGOf0WG2vsQWbGsc8lvELGV8070AjIwm"
    "7BrxIMrq0WUkhUsRexHWvQxf1w7mDgWraLZdZl0XzhxNOD3ZjNgtuOS0PFq3OsLp0h5AUjL45lOgu/CFazn8/sdAhTN3OX7cssv6"
    "m85A3A7EDKBROzSeqogVot8ms7JBPup8FS45ixggzLDDVA0YY3NP1h5AY4Xx4a+B6LOeLv17/wnjLiM0FZl3ZcwAxJQO85ZTkfBx"
    "VDZjC0V8PUxJlbPxpE0sKMRwO+hVjA3/sNUPFKgOZKy9+UVY+wNscgY+i/P8RGmDMNPbYL9tQzjvpvdB+A9s6RKEHIKInf0JiuTx"
    "10diUFxpNcj36N99De/58kuoDjRJU+HQxiPALzEuh9ehwz171FkCVQL9u9+AuKsQsxaBPK5iTriqTwDMagFjl2OKWyk019F/89X8"
    "fEU1t5l2upVvgWiP6gwEzr1hBaUVHwEuwxZW4OsRbTUzc90caVBCDLi+1+KPjuIbdwGPop2fgXNTasF5e9aD3Y5xbyZmLRWInb/T"
    "kvzu+2YEmlDruBKOgahUIutHX40Ut6I6jLWCr+eNUafCjWAWQgVTQeRTcDuxhdPwdc27QzF02WEQ+RBJ32lktWZLrV0HoTUwI08R"
    "MgUsLKw8FxiEmg4kuJMBRO9YbCB0Ib/cLYLLj63a5IhOulMRqhHrLC4xIL/HJL77QOSjQ4YYfo2vbUGSs3HFx1uP8Ngd1shnsg2+"
    "8RUk2caBDz48pefpihqhmivB125l7OFBqERWpY67iAvpUtdxJdiCIavdTxIuhtYUXHWgVRsWThGd/2IRUK6huukJVqVurlfHLX4Q"
    "+TCdITR+RQzfAZWFtsMCKUIVYwF+1Z4Zo9KNIFrhUeVBQEh3LKr+xnS0OKiC0ccXOk4vjmKpi7PR63WfPRA9ED0QPRAvFPSUaLoa"
    "AYT81am4vDtBqEYQIelzhMZDiLnbdBuBfCykaICM7OjncbKSseFvuy5i0Fpe6ITQvBfsVsYGvzvR/rsuqAT5evCkz+LrvyWrX0fw"
    "N3L7hUfzNWEoSHRL3ga2YCGCr1fR7BMcHPklkK8FqUh7LMQtXRsYiytafOOnYK5mbKjaBlAtR6oSlm6OaGUCkpIFeQpf+wzNo6sY"
    "O7+av3uWmvai9GccbskgaL/FI5A17gTZzvjwvcdUICGvB9MfbknYQMSS9FlC4zeEcA3jw18A0XYxfIYNlljE1lwFrmQBxde+gDb/"
    "lvENn2+/j1GRGb9H7k5aFRhrcYngGz9CNOXA8B3HbDAQZzs67k6ySpBngkKfJWs8QVa7jqj/zKGNR/JFcXC80wPu5LHBRCZQCM0x"
    "Ykw5uOGnxzLBic2PuJPHBkWLr/8CiVdzYPgrz5cJltZ4hGreJruSRfVpstpnqYW3tSE8TyZYQorQgHGCKxQIje9Bto3xkXumFMM5"
    "3mZlcSpC5cWE5u/wfjOvf8U5jI3cQ6oGVFrFcM7nRRaXIibusnIL+vQPGR+5n/GWDeZ5G6bFaY2DQ3vn0wYnD4jJbwt06FicICqd"
    "nyXvDef3QPRA9ED0QPRA9ED0QPRA9ED0QPRA9ED0QPRA9ED0QCwcCJnxLqBLG4TqMkBaQLoYhOhP0Ag2SfJ9J1W7E8TYhm2ERpno"
    "f0HSZxEzsRFnFxbLsQ3fIEtW0jz6KeBIvhFnawa6q0CU91tu/8BvObhhG1bfRmh8E5MILjHdYpccRHUg35syVUN16D5uu2AN3p9P"
    "8A9QWDZhl7j0QQAgSkUiaWoQgYNDt+KzVWS161F5iqTPtJfvdUWgymeZ8sVYhzc9xtjQpfj49/jGHbjEYN2StMtzJ8sJu5TLlsND"
    "9zA2uBrfuBCND+bFdGnZ5QUitijVasjXJqCMb9hFPa4kq38WaJCUloxdZrgvtuTbn5T3W+4Y+j/Gh/4R4Rx8825cwWCt6egm4Avc"
    "dOkUuxwY/HfcQ+/EN0eI4dckyzq7CfgcH8exLECUKqG1/20TuInV+/4FrV0BDLVWxIfW3lZmKSriue1y+wX/y/jQJkTfRWjeTdJn"
    "MW27dMV4RG6XNDWkqWFs+Nu45e/E17ag+khrz3xOBrvMzYqZiRUu+ZqnJvBp1twyTmxsR2Qw31inmU33KwZLRRHTZI+WXQ6f/yDj"
    "g0PE+B5iuBdXSDBOFuujdj6K2VS7HBy+gyO8HZ9dTPBPglnWnUM/k3/HYu0tf0P/nnMX42n+Cc3xd+dyTGH9AAAAAElFTkSuQmCC"
)
LOGO_URI = "data:image/png;base64," + LOGO_PNG_B64
# Logo dentro de una insignia blanca (para el encabezado del Excel)
LOGO_BADGE_B64 = (
    "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"
)

KPI_ICONO = {"RAM": "escudo", "PRIMA 24M": "reloj", "PR 24M": "pie", "MA": "maletin", "RFV MA": "sube",
             "CESION": "cesion", "PT": "peso"}


def ic(nombre, cls=""):
    return html.I(className=f"ic ic-{nombre} {cls}")


# ---- Layout ---------------------------------------------------------------------------
conceptos0, ramos0, anios0 = catalogos(ESTADO["df"])
CONCEPTO0 = "RFV NETO" if "RFV NETO" in conceptos0 else (conceptos0 or [None])[0]


def grafica(id_, h):
    return dcc.Graph(id=id_, config=GRAPH_CFG, style={"height": f"{h}px"})


def panel(titulo, ayuda, cuerpo, extra=None, cls="", id_titulo=None, id_ayuda=None):
    t = html.H3(titulo, id=id_titulo) if id_titulo else html.H3(titulo)
    a = html.P(ayuda, className="ayuda", id=id_ayuda) if id_ayuda else html.P(ayuda, className="ayuda")
    return html.Div([html.Div([html.Div([t, a]), extra], className="panel-head"), cuerpo], className=f"card panel {cls}")


def seccion(id_, num, titulo, sub, *hijos, extra=None):
    return html.Section([
        html.Div([html.Span(num, className="num"),
                  html.Div([html.H2(titulo), html.P(sub, className="sec-sub")]), extra], className="sec-head"),
        *hijos], id=id_, className="bloque")


def grupo(titulo, *hijos):
    return html.Div([html.Div(titulo, className="f-lbl"), *hijos], className="f-blk")


NAV = [("resumen", "home", "Resumen"), ("mensual", "barras", "Mes a mes"), ("estacional", "onda", "Estacionalidad"),
       ("conceptos", "capas", "Conceptos"), ("ramos", "grid", "Por ramo"), ("tabla-sec", "tabla", "Tabla")]

rail = html.Nav([
    html.Div([html.A([ic(i), html.Span(t, className="tip")], href=f"#{s}", className="rail-btn") for s, i, t in NAV],
             className="rail-nav"),
    html.Div(className="rail-sep"),
    html.Button([ic("filtro"), html.Span("Filtros", className="tip")], id="rail-filtros", className="rail-btn"),
    html.Button([ic("bajar"), html.Span("Descargar Excel", className="tip")], id="rail-xls", className="rail-btn"),
], className="rail")

drawer = html.Aside([
    html.Div([html.Div([ic("filtro"), html.Span("Filtros")], className="dr-title"),
              html.Button(ic("x"), id="btn-cerrar", className="icon-btn", title="Cerrar")], className="dr-head"),
    html.P("Los cambios se aplican al instante en todo el tablero.", className="dr-sub"),
    grupo("Concepto", dcc.RadioItems(id="f-concepto", options=conceptos0, value=CONCEPTO0, className="seg")),
    grupo("Variable", dcc.RadioItems(id="f-var", options=[{"label": v, "value": k} for k, v in VARIABLES.items()],
                                     value="RAM", className="lista")),
    grupo("Ramo", dcc.Checklist(id="f-ramo", options=[{"label": r, "value": r} for r in ramos0],
                                value=ramos0, className="pills")),
    grupo("Año", dcc.Checklist(id="f-anio", options=anios0, value=anios0[-1:], className="pills")),
    grupo("Mes", dcc.Checklist(id="f-mes", options=[{"label": m, "value": i + 1} for i, m in enumerate(MESES)],
                               value=list(range(1, 13)), className="pills meses"),
          html.Div([html.Button("Todos", id="btn-mes-todos", className="mini"),
                    html.Button("Ninguno", id="btn-mes-nada", className="mini")], className="mini-row")),
    grupo("Unidades", dcc.RadioItems(id="f-unidad", options=list(UNIDADES), value="Millones", className="pills")),
    grupo("Archivo", dcc.Upload(id="upload", children=html.Div([ic("subir"), " Cargar otra versión"]),
                                className="upload", accept=".xlsx,.xlsm,.xls"),
          html.Div(id="fuente", className="fuente")),
    html.Button("Restablecer filtros", id="btn-reset", className="btn-sec"),
], id="drawer", className="drawer")

main = html.Main([
    html.Header(html.Div([
        html.Div([html.Div(html.Img(src=LOGO_URI, alt="Patria"), className="logo-badge"),
                  html.Div([html.Div("PRISMA", className="brand"),
                            html.Div("Proyección de reservas · FCST 2027", className="brand-sub")])], className="brand-box"),
        html.Div(id="chips", className="chips", n_clicks=0, title="Abrir filtros"),
        html.Button([ic("filtro"), html.Span("Filtros")], id="btn-filtros", className="btn-filtros"),
        html.Button([ic("bajar"), html.Span("Excel")], id="btn-xls", className="btn-xls"),
    ], className="top-pill"), className="top"),
    html.Div(id="aviso"),

    seccion("resumen", "01", "Resumen", "Cifras clave al cierre del periodo filtrado y su cambio contra el año anterior (AA).",
            html.Div(id="kpis", className="kpis")),

    seccion("mensual", "02", "Mes a mes", "Cómo se reparte el monto en cada mes y qué ramos lo explican.",
            html.Div([
                panel("Monto por mes", "Cada barra es el total del mes. La línea naranja punteada es el promedio.",
                      grafica("g-mens", 380), id_titulo="t-mens", id_ayuda="a-mens"),
                panel("Por ramo", "Cuánto aporta cada ramo y qué porcentaje representa del total.",
                      grafica("g-ramo", 380), id_titulo="t-ramo"),
            ], className="grid g-2-1"),
            panel("Cambio contra el mes anterior", "Verde: el monto subió. Rojo: bajó.", grafica("g-mom", 250))),

    seccion("estacional", "03", "Estacionalidad",
            "¿En qué meses el monto está por arriba o por abajo de lo normal, y se parece al patrón de la prima?",
            panel("Reserva vs. prima, año por año", "", grafica("g-comp", 360), id_titulo="t-comp", id_ayuda="a-comp",
                  extra=html.Div([html.Span([html.I(className="sw sw-line"), html.Span(id="lg-var")]),
                                  html.Span([html.I(className="sw sw-bar"), html.Span(id="lg-prima")])],
                                 className="leyenda-fija")),
            html.Div([
                panel("Lectura por año", "Correlación cercana a +1: la variable se mueve igual que la prima. "
                      "Amplitud = índice más alto − más bajo (qué tan marcada es la estacionalidad).",
                      html.Div(id="est-stats")),
                panel("Comparación entre años", "Mismo índice de la variable, un color por año (más oscuro = más reciente).",
                      grafica("g-anios", 300), id_titulo="t-anios"),
            ], className="grid g-1-2"),
            html.Div([
                panel("Monto por mes y año", "Entre más oscuro el color, mayor el monto.",
                      grafica("g-heat", 300), id_titulo="t-heat"),
                panel("Estacionalidad por ramo", "Patrón mensual de cada ramo en el año elegido.",
                      grafica("g-ramo-est", 300),
                      extra=html.Div(dcc.Dropdown(id="est-ramo-anio", options=anios0, value=(anios0 or [None])[-1],
                                                  clearable=False, searchable=False), className="ctl ctl-sm")),
            ], className="grid g-2"),
            extra=html.Div([
                html.Div([html.Label("AÑOS"),
                          dcc.Dropdown(id="est-anios", options=[{"label": str(a), "value": a} for a in anios0],
                                       value=anios0, multi=True, clearable=False, searchable=False,
                                       placeholder="Elige años",
                                       labels={"select_all": "Seleccionar todos", "deselect_all": "Quitar todos",
                                               "selected_count": "{num_selected} años"})], className="ctl"),
                html.Div([html.Label("PRIMA A COMPARAR"),
                          dcc.Dropdown(id="est-prima", options=[{"label": v, "value": k} for k, v in PRIMAS.items()],
                                       value="PT", clearable=False, searchable=False)], className="ctl"),
            ], className="ctls")),

    seccion("conceptos", "04", "Conceptos", "Los cuatro cálculos de la reserva lado a lado: RCONT, RFV bruto, RFV IRR y RFV neto.",
            panel("Comparativo de conceptos", "Cada línea es un concepto; la etiqueta final muestra su último valor.",
                  grafica("g-conc", 360), id_titulo="t-conc")),

    seccion("ramos", "05", "Detalle por ramo", "Evolución de cada variable, separada por ramo.",
            html.Div([panel(VARIABLES[v], "", grafica(f"g-v{i}", 250), cls="mini-panel") for i, v in enumerate(DETALLE)],
                     className="grid g-3"),
            extra=html.Div(id="ramo-leyenda", className="leyenda")),

    seccion("tabla-sec", "06", "Tabla mensualizada", "Los números detrás de las gráficas. El Excel trae una pestaña por sección.",
            html.Div(id="tabla", className="card tabla-wrap"), dcc.Download(id="dl"),
            extra=html.Button([ic("bajar"), html.Span("Descargar Excel")], id="btn-xls2", className="btn-pri")),
    html.Footer(id="pie", className="pie"),
], className="main")

app = Dash(__name__, title="PRISMA · Reservas FCST 2027", update_title=None)
app.layout = html.Div([dcc.Store(id="version", data=0), rail,
                       html.Div(id="overlay", className="overlay", n_clicks=0), drawer, main], className="app")

app.index_string = """<!DOCTYPE html>
<html lang="es"><head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root { --bg:#e9eaef; --card:#ffffff; --navy:#2f3a5f; --navy2:#3c4565; --tx:#1f2433; --tx2:#5b6275; --tx3:#8b90a0;
  --linea:#e3e5ec; --acc:#f08a3c; --acc-soft:#fdeee2; --nav-soft:#eceef5; --pos:#2e9e6b; --pos-soft:#e3f4ec; --neg:#d64545; --neg-soft:#fbe7e7;
  --sombra:0 1px 2px rgba(31,36,51,.04), 0 6px 20px rgba(31,36,51,.06); color-scheme:light;
  --Dash-Fill-Inverse-Strong:#fff; --Dash-Fill-Interactive-Strong:var(--navy); --Dash-Fill-Interactive-Weak:var(--nav-soft);
  --Dash-Fill-Primary-Hover:var(--nav-soft); --Dash-Fill-Primary-Active:var(--nav-soft); --Dash-Stroke-Strong:#cfd3de;
  --Dash-Stroke-Weak:var(--linea); --Dash-Text-Primary:var(--tx); --Dash-Text-Strong:var(--tx); --Dash-Text-Weak:var(--tx2); }
* { box-sizing:border-box; }
html { scroll-behavior:smooth; }
body { margin:0; font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif; -webkit-font-smoothing:antialiased; background:var(--bg); }
.app { min-height:100vh; background:var(--bg); color:var(--tx); }
.ic { display:inline-block; width:18px; height:18px; background:currentColor; flex:0 0 auto; }
%%ICONOS%%
/* --- riel izquierdo (azul marino, esquinas redondeadas) --- */
.rail { position:fixed; left:0; top:50%; transform:translateY(-50%); z-index:40; display:flex; flex-direction:column; align-items:center;
  gap:6px; padding:18px 10px; background:var(--navy); border-radius:0 26px 26px 0; box-shadow:var(--sombra); }
.rail-nav { display:flex; flex-direction:column; gap:6px; }
.rail-sep { width:26px; height:1px; background:rgba(255,255,255,.18); margin:6px 0; }
.rail-btn { position:relative; width:42px; height:42px; border-radius:12px; display:flex; align-items:center; justify-content:center;
  color:rgba(255,255,255,.72); background:none; border:0; cursor:pointer; text-decoration:none; }
.rail-btn:hover { color:#fff; background:rgba(255,255,255,.12); }
.tip { position:absolute; left:54px; white-space:nowrap; background:var(--navy); color:#fff; font-size:12px; padding:5px 10px;
  border-radius:7px; opacity:0; pointer-events:none; transform:translateX(-4px); transition:.15s; }
.rail-btn:hover .tip { opacity:1; transform:none; }
/* --- panel de filtros --- */
.overlay { position:fixed; inset:0; background:rgba(31,36,51,.25); opacity:0; pointer-events:none; transition:.2s; z-index:45; }
.overlay.abierto { opacity:1; pointer-events:auto; }
.drawer { position:fixed; top:12px; bottom:12px; left:12px; width:310px; z-index:50; overflow-y:auto; padding:20px 20px 26px;
  background:#fff; border-radius:20px; box-shadow:0 20px 50px rgba(31,36,51,.18);
  transform:translateX(calc(-100% - 40px)); visibility:hidden; transition:transform .25s ease, visibility .25s; }
.drawer.abierto { transform:none; visibility:visible; }
.dr-head { display:flex; align-items:center; justify-content:space-between; }
.dr-title { display:flex; gap:8px; align-items:center; font-weight:700; font-size:16px; color:var(--navy); }
.dr-sub { color:var(--tx3); font-size:12px; margin:6px 0 10px; }
.icon-btn { background:none; border:0; color:var(--tx3); cursor:pointer; padding:6px; border-radius:8px; display:flex; }
.icon-btn:hover { color:var(--tx); background:var(--nav-soft); }
.f-blk { padding:13px 0; border-top:1px solid var(--linea); }
.f-lbl { font-size:10.5px; font-weight:700; letter-spacing:.09em; text-transform:uppercase; color:var(--tx3); margin-bottom:9px; }
.lista label { display:flex !important; align-items:center; gap:8px; padding:6px 9px; border-radius:8px; color:var(--tx2);
  font-size:13px; cursor:pointer; margin:1px 0; }
.lista label:hover { background:var(--nav-soft); }
.lista label:has(input:checked) { background:var(--nav-soft); color:var(--navy); font-weight:600; }
.lista input { accent-color:var(--navy); margin:0; }
.pills, .seg { display:flex; flex-wrap:wrap; gap:6px; }
.pills label, .seg label { display:inline-flex !important; align-items:center; justify-content:center; padding:6px 12px; border-radius:999px;
  font-size:12.5px; color:var(--tx2); background:#f4f5f8; border:1px solid transparent; cursor:pointer; user-select:none; margin:0; }
.seg label { border-radius:9px; flex:1 1 calc(50% - 6px); }
.pills label:hover, .seg label:hover { border-color:#cfd3de; }
.pills label:has(input:checked), .seg label:has(input:checked) { background:var(--navy); color:#fff; font-weight:600; }
.pills input, .seg input { position:absolute; opacity:0; width:0; height:0; }
.pills.meses label { width:calc(25% - 5px); padding:6px 0; }
.mini-row { display:flex; gap:6px; margin-top:8px; }
.mini { background:none; border:1px solid var(--linea); color:var(--tx3); border-radius:6px; font-size:11.5px; padding:3px 9px; cursor:pointer; }
.mini:hover { color:var(--tx); }
.upload { display:flex; gap:6px; align-items:center; justify-content:center; border:1px dashed #c9cdd8; border-radius:10px; padding:10px;
  font-size:12.5px; color:var(--tx2); cursor:pointer; } .upload:hover { border-color:var(--navy); color:var(--navy); }
.fuente { color:var(--tx3); font-size:11.5px; margin-top:8px; word-break:break-all; }
.btn-sec { width:100%; margin-top:14px; padding:9px; border-radius:10px; border:1px solid var(--linea); background:none; color:var(--tx2); cursor:pointer; font:inherit; font-size:12.5px; }
.btn-sec:hover { border-color:var(--navy); color:var(--navy); }
/* --- encabezado (barra azul marino tipo píldora) --- */
.main { margin-left:76px; padding:0 34px 40px 20px; max-width:1700px; }
header.top { position:sticky; top:0; z-index:30; padding:14px 0 10px; background:linear-gradient(var(--bg) 75%, rgba(233,234,239,0)); }
.top-pill { display:flex; align-items:center; gap:16px; padding:12px 14px 12px 22px; background:var(--navy); border-radius:999px; box-shadow:var(--sombra); }
.brand-box { display:flex; align-items:center; gap:12px; }
.logo-badge { width:40px; height:40px; border-radius:11px; background:#fff; display:flex; align-items:center; justify-content:center; flex:0 0 auto; }
.logo-badge img { height:28px; width:auto; display:block; }
.brand { font-size:22px; font-weight:800; letter-spacing:.16em; line-height:1; color:#fff; }
.brand-sub { color:rgba(255,255,255,.65); font-size:12px; margin-top:4px; }
.chips { margin-left:auto; display:flex; gap:6px; flex-wrap:wrap; cursor:pointer; justify-content:flex-end; }
.chip { font-size:11.5px; color:#fff; background:rgba(255,255,255,.10); border-radius:999px; padding:5px 10px; }
.chip b { color:rgba(255,255,255,.6); font-weight:500; margin-right:4px; }
.chip:hover { background:rgba(255,255,255,.18); }
.btn-filtros, .btn-xls { display:flex; align-items:center; gap:7px; padding:9px 16px; border-radius:999px; font:inherit; font-size:13px; font-weight:600;
  cursor:pointer; border:0; }
.btn-filtros { color:var(--navy); background:#fff; } .btn-filtros:hover { background:#f1f2f6; }
.btn-xls { color:#fff; background:var(--acc); } .btn-xls:hover { filter:brightness(1.05); }
.btn-filtros .ic, .btn-xls .ic { width:15px; height:15px; }
/* --- secciones --- */
section.bloque { margin-top:28px; scroll-margin-top:96px; }
.sec-head { display:flex; align-items:center; gap:14px; flex-wrap:wrap; margin-bottom:14px; }
.num { font-size:12px; font-weight:700; color:#fff; background:var(--navy); border-radius:9px; padding:6px 9px; }
.sec-head h2 { font-size:19px; font-weight:700; margin:0; letter-spacing:-.01em; color:var(--tx); }
.sec-sub { color:var(--tx3); font-size:13px; margin:3px 0 0; }
.grid { display:grid; gap:16px; margin-bottom:16px; }
.g-2 { grid-template-columns:1fr 1fr; } .g-2-1 { grid-template-columns:minmax(0,2fr) minmax(0,1fr); }
.g-1-2 { grid-template-columns:minmax(0,1fr) minmax(0,2fr); } .g-3 { grid-template-columns:repeat(3,minmax(0,1fr)); }
@media (max-width:1200px) { .g-2,.g-2-1,.g-1-2,.g-3 { grid-template-columns:1fr; } }
.card { position:relative; background:var(--card); border-radius:20px; box-shadow:var(--sombra); }
.panel { padding:18px 20px 10px; min-width:0; margin-bottom:16px; }
.grid .panel { margin-bottom:0; }
.panel-head { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; margin-bottom:4px; }
.panel h3 { font-size:15px; font-weight:650; margin:0; color:var(--tx); }
.ayuda { color:var(--tx3); font-size:12.5px; margin:4px 0 0; line-height:1.45; }
.mini-panel .ayuda { display:none; }
.leyenda-fija { display:flex; gap:18px; font-size:12.5px; color:var(--tx2); white-space:nowrap; }
.leyenda-fija > span { display:flex; align-items:center; gap:7px; }
.sw { display:inline-block; }
.sw-line { width:22px; height:3px; border-radius:3px; background:var(--navy); position:relative; }
.sw-line::after { content:""; position:absolute; left:7px; top:-3px; width:9px; height:9px; border-radius:50%; background:var(--navy); }
.sw-bar { width:12px; height:14px; border-radius:3px; background:#f8c9a2; }
/* KPIs */
.kpis { display:grid; gap:16px; grid-template-columns:minmax(0,1.35fr) repeat(3,minmax(0,1fr)); }
@media (max-width:1200px) { .kpis { grid-template-columns:repeat(2,minmax(0,1fr)); } }
.kpi { padding:18px 20px; overflow:hidden; }
.kpi .t { display:flex; align-items:center; gap:10px; color:var(--tx2); font-size:13px; font-weight:500; }
.kpi .t .ico { width:30px; height:30px; border-radius:9px; display:flex; align-items:center; justify-content:center; background:var(--nav-soft); color:var(--navy); }
.kpi .t .ico .ic { width:15px; height:15px; }
.kpi .v { font-size:clamp(20px,1.8vw,28px); font-weight:750; letter-spacing:-.02em; margin:12px 0 6px; white-space:nowrap; font-variant-numeric:tabular-nums; color:var(--tx); }
.kpi .aa { font-size:12px; color:var(--tx3); display:flex; gap:6px; align-items:center; flex-wrap:wrap; }
.kpi .pie-k { font-size:11.5px; color:var(--tx3); margin-top:10px; padding-top:9px; border-top:1px solid var(--linea); }
.kpi.hero { grid-row:span 2; display:flex; flex-direction:column; background:var(--navy); color:#fff; }
.kpi.hero .t { color:rgba(255,255,255,.75); } .kpi.hero .t .ico { background:rgba(255,255,255,.12); color:#fff; }
.kpi.hero .v { color:#fff; font-size:clamp(30px,2.8vw,42px); }
.kpi.hero .aa, .kpi.hero .pie-k { color:rgba(255,255,255,.65); } .kpi.hero .pie-k { border-color:rgba(255,255,255,.15); }
.kpi.hero .ayuda { color:rgba(255,255,255,.6); }
.kpi.hero .spark { margin-top:auto; }
.badge { font-weight:650; padding:2px 8px; border-radius:999px; font-size:11.5px; }
.badge.up { color:var(--pos); background:var(--pos-soft); } .badge.down { color:var(--neg); background:var(--neg-soft); }
.badge.neu { color:var(--tx3); background:#f1f2f6; }
.kpi.hero .badge.up { color:#7ee2b0; background:rgba(126,226,176,.15); } .kpi.hero .badge.down { color:#ff9b9b; background:rgba(255,155,155,.15); }
/* controles */
.ctls { display:flex; gap:12px; margin-left:auto; flex-wrap:wrap; }
.ctl { display:flex; flex-direction:column; gap:5px; min-width:220px; }
.ctl-sm { min-width:110px; }
.ctl label { font-size:10.5px; letter-spacing:.09em; color:var(--tx3); font-weight:700; }
/* lectura por año */
table.lect { width:100%; border-collapse:collapse; font-size:13px; margin-top:10px; font-variant-numeric:tabular-nums; }
table.lect th { text-align:right; color:var(--tx3); font-weight:600; font-size:11px; padding:6px 6px; border-bottom:1px solid var(--linea); }
table.lect td { text-align:right; padding:11px 6px; border-bottom:1px solid var(--linea); color:var(--tx); }
table.lect th:first-child, table.lect td:first-child { text-align:left; font-weight:650; }
.dot { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:7px; }
.lect-nota { color:var(--tx3); font-size:12px; line-height:1.5; margin-top:12px; }
.leyenda { display:flex; gap:14px; margin-left:auto; flex-wrap:wrap; font-size:12.5px; color:var(--tx2); }
.leyenda span { display:flex; align-items:center; }
/* tabla */
.btn-pri { margin-left:auto; display:flex; align-items:center; gap:7px; background:var(--acc); color:#fff; border:0; border-radius:999px;
  padding:10px 18px; font:inherit; font-size:13px; font-weight:650; cursor:pointer; }
.btn-pri:hover { filter:brightness(1.05); }
.tabla-wrap { overflow:auto; max-height:620px; }
table.t { border-collapse:collapse; width:100%; font-size:13px; font-variant-numeric:tabular-nums; }
table.t th { position:sticky; top:0; background:var(--navy); color:#fff; font-weight:600; text-align:right; padding:12px 16px; font-size:12px; }
table.t th:first-child { border-top-left-radius:20px; } table.t th:last-child { border-top-right-radius:20px; }
table.t th:first-child, table.t td:first-child { text-align:left; }
table.t td { padding:9px 16px; text-align:right; border-bottom:1px solid var(--linea); color:var(--tx); }
table.t tr:nth-child(even) td { background:#fafbfc; }
table.t tr:hover td { background:var(--nav-soft); }
table.t td.tot { font-weight:700; color:var(--navy); }
.aviso { background:#fff6e5; color:#9a6200; border:1px solid #f5d79a; border-radius:12px; padding:10px 14px; margin:8px 0; font-size:13px; }
.pie { color:var(--tx3); font-size:11.5px; margin-top:28px; text-align:center; }
</style></head>
<body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>""".replace("%%ICONOS%%", CSS_ICONOS)


# ---- Callbacks de interfaz (en el navegador) ------------------------------------------
app.clientside_callback(
    """function(a, b, c, d, e, cls) {
        const t = (dash_clientside.callback_context.triggered[0] || {}).prop_id || '';
        const cerrar = t.startsWith('btn-cerrar') || t.startsWith('overlay');
        const abrir = !cerrar && !(cls || '').includes('abierto');
        return [abrir ? 'drawer abierto' : 'drawer', abrir ? 'overlay abierto' : 'overlay'];
    }""",
    Output("drawer", "className"), Output("overlay", "className"),
    Input("btn-filtros", "n_clicks"), Input("rail-filtros", "n_clicks"), Input("btn-cerrar", "n_clicks"),
    Input("overlay", "n_clicks"), Input("chips", "n_clicks"), State("drawer", "className"), prevent_initial_call=True)


@app.callback(Output("f-mes", "value"), Input("btn-mes-todos", "n_clicks"), Input("btn-mes-nada", "n_clicks"),
              prevent_initial_call=True)
def _meses_rapidos(_a, _b):
    return list(range(1, 13)) if ctx.triggered_id == "btn-mes-todos" else []


@app.callback(Output("f-concepto", "value"), Output("f-var", "value"), Output("f-ramo", "value", allow_duplicate=True),
              Output("f-anio", "value", allow_duplicate=True), Output("f-mes", "value", allow_duplicate=True),
              Output("f-unidad", "value"), Input("btn-reset", "n_clicks"), prevent_initial_call=True)
def _reset(_n):
    conceptos, ramos, anios = catalogos(ESTADO["df"])
    return ("RFV NETO" if "RFV NETO" in conceptos else conceptos[0]), "RAM", ramos, anios[-1:], list(range(1, 13)), "Millones"


@app.callback(Output("version", "data"), Output("f-concepto", "options"), Output("f-ramo", "options"),
              Output("f-ramo", "value"), Output("f-anio", "options"), Output("f-anio", "value"),
              Output("est-anios", "options"), Output("est-anios", "value"),
              Output("est-ramo-anio", "options"), Output("est-ramo-anio", "value"),
              Input("upload", "contents"), State("upload", "filename"), State("version", "data"),
              prevent_initial_call=True)
def _subir(contents, nombre, ver):
    if not contents:
        return (no_update,) * 10
    try:
        df = cargar(base64.b64decode(contents.split(",", 1)[1]))
    except Exception as e:  # archivo con otro formato
        ESTADO["error"] = f"No pude leer {nombre}: {e}"
        return (ver + 1,) + (no_update,) * 9
    ESTADO.update(df=df, origen=nombre, error="")
    conceptos, ramos, anios = catalogos(df)
    return (ver + 1, conceptos, [{"label": r, "value": r} for r in ramos], ramos, anios, anios[-1:],
            [{"label": str(a), "value": a} for a in anios], anios, anios, anios[-1])


ENTRADAS = [Input("f-concepto", "value"), Input("f-var", "value"), Input("f-ramo", "value"),
            Input("f-anio", "value"), Input("f-mes", "value"), Input("f-unidad", "value"), Input("version", "data")]


def _alpha(hex_color, a):
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


# ---- Callback principal ---------------------------------------------------------------
@app.callback(
    Output("chips", "children"), Output("aviso", "children"), Output("fuente", "children"), Output("pie", "children"),
    Output("kpis", "children"),
    Output("t-mens", "children"), Output("a-mens", "children"), Output("g-mens", "figure"),
    Output("t-ramo", "children"), Output("g-ramo", "figure"), Output("g-mom", "figure"),
    Output("t-conc", "children"), Output("g-conc", "figure"),
    *[Output(f"g-v{i}", "figure") for i in range(6)], Output("ramo-leyenda", "children"), Output("tabla", "children"),
    *ENTRADAS)
def actualizar(concepto, var, ramos, anios, meses, unidad, _ver):
    df = ESTADO["df"]
    _, ramos_todos, _anios_todos = catalogos(df)
    ramos, anios, meses = sorted(ramos or []), sorted(anios or []), sorted(meses or [])
    div, suf = UNIDADES[unidad]
    ratio = var in RATIOS
    lbl = VARIABLES[var]
    yu = f"{unidad} de pesos" if unidad != "Pesos" else "Pesos"
    aviso = html.Div(ESTADO["error"], className="aviso") if ESTADO["error"] else None
    fuente = f"Fuente: {ESTADO['origen']}" if ESTADO["origen"] else ""
    pie = f"PRISMA · {ESTADO['origen'] or 'sin archivo'} · actualizado {datetime.now():%d/%m/%Y %H:%M}"
    per_txt = (f"{anios[0]}–{anios[-1]}" if len(anios) > 1 else str(anios[0])) if anios else "—"
    m_txt = "Todos" if len(meses) == 12 else (", ".join(MESES[m - 1] for m in meses) if meses else "—")
    chips = [html.Span([html.B(k), v], className="chip") for k, v in
             [("Concepto", concepto), ("Variable", lbl), ("Ramos", ", ".join(ramos) if ramos else "—"),
              ("Año", per_txt), ("Mes", m_txt), ("En", unidad)]]
    if not (ramos and anios and meses and concepto):
        v = vacia()
        return (chips, aviso, fuente, pie, [], lbl, "", v, "Por ramo", v, v, "Comparativo de conceptos", v,
                *[v] * 6, None, html.Div("Sin datos", className="ayuda", style={"padding": "16px"}))

    # --- KPIs ---
    kpis = []
    for i, k in enumerate(datos_kpis(df, concepto, ramos, anios, meses)):
        hero = i == 0
        r = k["ratio"]
        if k["variacion"] is None:
            badge, aa = html.Span("sin comparativo", className="badge neu"), "AA: N/A"
        else:
            dv = k["variacion"] * 100
            badge = html.Span(f"{'▲' if dv >= 0 else '▼'} {abs(dv):.1f}{' pp' if r else '%'}",
                              className="badge " + ("up" if dv >= 0 else "down"))
            aa = f"AA: {fmt(k['anterior'], unidad, r)}"
        hijos = [html.Div([html.Span(ic(KPI_ICONO[k["variable"]]), className="ico"), k["nombre"]], className="t"),
                 html.Div(fmt(k["actual"], unidad, r), className="v"),
                 html.Div([html.Span(aa), badge], className="aa"),
                 html.Div(k["referencia"], className="pie-k")]
        if hero:
            s = serie(df, concepto, k["variable"], ramos, anios, meses).sort_values("FECHA")
            f = go.Figure(go.Scatter(x=s["FECHA"], y=s["VALOR"] / div, mode="lines", fill="tozeroy",
                                     line=dict(color=T["acento"], width=2.5, shape="spline"),
                                     fillcolor="rgba(255,255,255,0.10)",
                                     hovertemplate="%{x|%m/%Y}: %{y:,.1f}" + suf + "<extra></extra>"))
            f.update_layout(height=120, margin=dict(l=0, r=0, t=6, b=0), paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)", showlegend=False, hovermode="x")
            f.update_xaxes(visible=False, fixedrange=True)
            if s["VALOR"].notna().any():
                f.update_yaxes(range=[s["VALOR"].min() / div * 0.9, s["VALOR"].max() / div * 1.04])
            f.update_yaxes(visible=False, fixedrange=True)
            hijos.insert(3, html.Div([html.Div("Tendencia del periodo filtrado", className="ayuda"),
                                      dcc.Graph(figure=f, config={"displayModeBar": False}, style={"height": "120px"})],
                                     className="spark"))
        kpis.append(html.Div(hijos, className="card kpi" + (" hero" if hero else "")))

    # --- Monto por mes ---
    tot = serie(df, concepto, var, ramos, anios, meses).sort_values("FECHA")
    yv = tot["VALOR"] if ratio else tot["VALOR"] / div
    etiquetas = [((f"{v * 100:.1f}%" if ratio else f"{v:,.1f}") if pd.notna(v) else "") for v in yv]
    etiquetas = [e if len(tot) <= (24 if not ratio else 12) else "" for e in etiquetas]
    fig = go.Figure()
    for a in anios:
        m = (tot["FECHA"].dt.year == a).values
        col = color_anio(a, anios)
        txt = [e for e, k in zip(etiquetas, m) if k]
        if ratio:
            fig.add_scatter(x=tot.loc[m, "FECHA"], y=yv[m], name=str(a), mode="lines+markers+text",
                            line=dict(color=col, width=2.5), marker=dict(size=8), text=txt, textposition="top center",
                            textfont=dict(color=T["text2"], size=10), hovertemplate="%{y:.2%}<extra>" + str(a) + "</extra>")
        else:
            fig.add_bar(x=tot.loc[m, "FECHA"], y=yv[m], name=str(a), marker_color=col, marker_cornerradius=6,
                        text=txt, textposition="outside", textfont=dict(color=T["text2"], size=10), cliponaxis=False,
                        hovertemplate="%{y:,.1f}" + suf + "<extra>" + str(a) + "</extra>")
    if yv.notna().any():
        prom = yv.mean()
        fig.add_hline(y=prom, line=dict(color=T["acento"], width=1.6, dash="dash"),
                      annotation_text=f"Promedio {prom * 100:.1f}%" if ratio else f"Promedio {prom:,.1f}{suf}",
                      annotation_position="right", annotation_font=dict(color=T["acento"], size=11))
    estilo(fig, 380, None if ratio else yu, ratio, leyenda=len(anios) > 1)
    fig.update_layout(margin=dict(r=110))
    if not ratio and yv.notna().any():
        fig.update_yaxes(range=[0, yv.max() * 1.15])
    g_mens = fig
    a_mens = ("Cada punto es la cesión ponderada del mes. " if ratio else "Cada barra es el total del mes. ") + \
             "La línea naranja punteada es el promedio" + ("; más oscuro = año más reciente." if len(anios) > 1 else ".")

    # --- Por ramo ---
    comp, t_ramo = datos_por_ramo(df, concepto, var, ramos, anios, meses, per_txt)
    if ratio:
        txt, xv = [f"{v * 100:.1f}%" for v in comp["VALOR"]], comp["VALOR"]
    else:
        txt = [f"{v / div:,.1f}{suf}  ·  {p * 100:.1f}%" for v, p in zip(comp["VALOR"], comp["PART"].fillna(0))]
        xv = comp["VALOR"] / div
    fig = go.Figure(go.Bar(y=["Ramo " + r for r in comp["RAMO"]], x=xv, orientation="h", text=txt,
                           textposition="outside", cliponaxis=False, textfont=dict(color=T["text"], size=11.5),
                           marker=dict(color=T["navy"], cornerradius=6), hovertemplate="%{y}: %{text}<extra></extra>"))
    estilo(fig, 380, leyenda=False, ratio=ratio)
    fig.update_layout(hovermode="closest", margin=dict(l=8, r=8, t=8, b=8), bargap=0.4)
    fig.update_xaxes(showticklabels=False, showgrid=False, showline=False, range=[0, (xv.max() if len(xv) else 1) * 1.7])
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)", tickfont=dict(color=T["text"], size=12.5))
    g_ramo = fig

    # --- Cambio vs mes anterior ---
    t = tot.copy()
    t["DELTA"] = t["VALOR"].diff() * (100 if ratio else 1 / div)
    fig = go.Figure(go.Bar(x=t["FECHA"], y=t["DELTA"], marker_cornerradius=4,
                           marker_color=[T["pos"] if v >= 0 else T["neg"] for v in t["DELTA"].fillna(0)],
                           text=[("" if pd.isna(v) else (f"{v:+.2f}" if ratio else f"{v:+,.1f}")) if len(t) <= 24 else ""
                                 for v in t["DELTA"]], textposition="outside", cliponaxis=False,
                           textfont=dict(color=T["text2"], size=10),
                           hovertemplate=("%{y:+.2f} pp" if ratio else "%{y:+,.1f}" + suf) + "<extra></extra>"))
    estilo(fig, 250, "pp" if ratio else unidad, leyenda=False, ytick=",.1f")
    g_mom = fig

    # --- Conceptos ---
    fig = go.Figure()
    for c in [c for c in CONCEPTOS_ORDEN if c in set(df["CONCEPTO"])]:
        s = serie(df, c, var, ramos, anios, meses).sort_values("FECHA")
        y = s["VALOR"] if ratio else s["VALOR"] / div
        col = T["conceptos"].get(c, T["text3"])
        fig.add_scatter(x=s["FECHA"], y=y, name=c, mode="lines", line=dict(color=col, width=3.5 if c == concepto else 2),
                        hovertemplate=("%{y:.1%}" if ratio else "%{y:,.1f}" + suf))
        if len(s) and pd.notna(y.iloc[-1]):
            fig.add_annotation(x=s["FECHA"].iloc[-1], y=y.iloc[-1], xanchor="left", xshift=8, showarrow=False,
                               text=f"<b>{c}</b>  {fmt(s['VALOR'].iloc[-1], unidad, ratio)}", font=dict(color=col, size=12))
    estilo(fig, 360, None if ratio else yu, ratio, leyenda=False)
    fig.update_layout(margin=dict(l=8, r=180, t=10, b=8))
    g_conc = fig

    # --- Detalle por ramo ---
    peq = []
    for v in DETALLE:
        r_ = v in RATIOS
        fig = go.Figure()
        for r in ramos:
            s = serie(df, concepto, v, [r], anios, meses)
            if s["VALOR"].fillna(0).abs().sum() == 0:
                continue
            fig.add_scatter(x=s["FECHA"], y=s["VALOR"] if r_ else s["VALOR"] / div, name=f"Ramo {r}", mode="lines",
                            line=dict(color=color_ramo(r, ramos_todos), width=2.2),
                            hovertemplate="%{y:.1%}" if r_ else "%{y:,.1f}" + suf)
        estilo(fig, 250, None, r_, leyenda=False, compacto=True)
        peq.append(fig)
    leyenda = [html.Span([html.I(className="dot", style={"background": color_ramo(r, ramos_todos)}), f"Ramo {r}"])
               for r in ramos]

    # --- Tabla ---
    tab = tabla_mensual(df, concepto, var, ramos, anios, meses)
    vista = tab * 100 if ratio else tab / div
    f_ = (lambda x: "N/A" if pd.isna(x) else f"{x:,.2f}%") if ratio else (lambda x: "N/A" if pd.isna(x) else f"{x:,.1f}")
    filas = [html.Tr([html.Td(mes_txt(p))] + [html.Td(f_(row[c]), className="tot" if c == "Total" else None)
                                              for c in vista.columns]) for p, row in vista.iterrows()]
    tabla = html.Table([html.Thead(html.Tr([html.Th("Mes")] + [html.Th(c + (" (%)" if ratio else f" ({unidad})"))
                                                               for c in vista.columns])),
                        html.Tbody(filas)], className="t")

    return (chips, aviso, fuente, pie, kpis, f"{lbl} por mes · {concepto}", a_mens, g_mens, t_ramo, g_ramo, g_mom,
            f"{lbl} por concepto", g_conc, *peq, leyenda, tabla)


# ---- Estacionalidad -------------------------------------------------------------------
@app.callback(
    Output("t-comp", "children"), Output("a-comp", "children"), Output("lg-var", "children"),
    Output("lg-prima", "children"), Output("g-comp", "figure"), Output("est-stats", "children"),
    Output("t-anios", "children"), Output("g-anios", "figure"),
    Output("t-heat", "children"), Output("g-heat", "figure"), Output("g-ramo-est", "figure"),
    Input("f-concepto", "value"), Input("f-var", "value"), Input("f-ramo", "value"), Input("f-mes", "value"),
    Input("f-unidad", "value"), Input("est-anios", "value"), Input("est-prima", "value"),
    Input("est-ramo-anio", "value"), Input("version", "data"))
def estacionalidad(concepto, var, ramos, meses, unidad, anios, prima, anio_ramo, _ver):
    df = ESTADO["df"]
    _, ramos_todos, anios_todos = catalogos(df)
    ramos, meses, anios = sorted(ramos or []), sorted(meses or []), sorted(anios or [])
    lbl, lblp = VARIABLES[var], PRIMAS[prima]
    if not (ramos and meses and anios and concepto):
        v = vacia("Elige al menos un año arriba y revisa los filtros")
        return "Reserva vs. prima", "", lbl, lblp, v, None, "Comparación entre años", v, "Monto por mes y año", v, v
    div, suf = UNIDADES[unidad]
    ratio = var in RATIOS
    xm = [MESES[m - 1] for m in meses]
    iv = indice(df, concepto, var, ramos, anios, meses)
    ip = indice(df, concepto, prima, ramos, anios, meses)

    # 1) Un panel por año: prima (barras suaves) vs. variable (línea azul marino). Solo dos series por panel.
    n = len(anios)
    fig = make_subplots(rows=1, cols=n, shared_yaxes=True, horizontal_spacing=0.035 if n > 1 else 0,
                        subplot_titles=[f"<b>{a}</b>" for a in anios])
    for i, a in enumerate(anios, start=1):
        fig.add_bar(x=xm, y=ip.loc[a].values, name=lblp, marker_color=T["acento_suave"], marker_cornerradius=4,
                    showlegend=False, hovertemplate=lblp + ": %{y:.2f}<extra></extra>", row=1, col=i)
        fig.add_scatter(x=xm, y=iv.loc[a].values, name=lbl, mode="lines+markers", showlegend=False,
                        line=dict(color=T["navy"], width=3), marker=dict(size=7, color=T["navy"], line=dict(color="#fff", width=1.5)),
                        hovertemplate=lbl + ": %{y:.2f}<extra></extra>", row=1, col=i)
        fig.add_hline(y=1, line=dict(color=T["text3"], width=1, dash="dot"), row=1, col=i)
    estilo(fig, 360, None, leyenda=False, ytick=".2f")
    fig.update_layout(hovermode="x unified", margin=dict(l=8, r=8, t=34, b=8), bargap=0.25)
    fig.update_annotations(font=dict(size=14, color=T["text"]), yshift=4)
    fig.update_xaxes(tickfont=dict(size=10 if n > 2 else 11), tickangle=0)
    fig.update_yaxes(title_text="Índice (1.00 = mes promedio)", row=1, col=1)
    g_comp = fig
    t_comp = f"{lbl} vs. {lblp}, año por año"
    a_comp = ("Un panel por año. Barras naranjas: prima. Línea azul: " + lbl.lower() + ". "
              "Arriba de la línea punteada (1.00) el mes está por encima del promedio de su año; abajo, por debajo.")

    # 2) Lectura por año
    lect = datos_lectura(iv, ip, meses)
    filas = [html.Tr([html.Td([html.Span(className="dot", style={"background": color_anio(int(r["Año"]), anios)}), str(r["Año"])]),
                      html.Td("—" if pd.isna(r["Correlación"]) else f"{r['Correlación']:+.2f}"),
                      html.Td(r["Mes pico variable"]), html.Td(r["Mes pico prima"]),
                      html.Td("—" if pd.isna(r["Amplitud variable"]) else f"{r['Amplitud variable']:.2f}"),
                      html.Td("—" if pd.isna(r["Amplitud prima"]) else f"{r['Amplitud prima']:.2f}")])
             for _, r in lect.iterrows()]
    stats = [html.Table([html.Thead(html.Tr([html.Th("Año"), html.Th("Correlación"), html.Th("Pico var."),
                                             html.Th("Pico prima"), html.Th("Amplitud var."), html.Th("Amplitud prima")])),
                         html.Tbody(filas)], className="lect"),
             html.Div("Una reserva es un saldo: normalmente se mueve menos que la prima del mes, por eso su amplitud es menor.",
                      className="lect-nota")]

    # 3) Comparación entre años (solo la variable)
    fig = go.Figure()
    for a in anios:
        fig.add_scatter(x=xm, y=iv.loc[a].values, name=str(a), mode="lines+markers",
                        line=dict(color=color_anio(a, anios), width=3 if a == anios[-1] else 2.2), marker=dict(size=7),
                        hovertemplate="%{y:.2f}")
    fig.add_hline(y=1, line=dict(color=T["text3"], width=1, dash="dot"))
    estilo(fig, 300, "Índice", ytick=".2f")
    g_anios = fig
    t_anios = f"Comparación entre años · {lbl}"

    # 4) Mapa de calor de montos
    s = serie(df, concepto, var, ramos, anios, meses, por=("ANIO", "MES"))
    piv = s.pivot(index="ANIO", columns="MES", values="VALOR").reindex(index=anios, columns=meses)
    z = piv.values * (100 if ratio else 1 / div)
    fig = go.Figure(go.Heatmap(
        z=z, x=xm, y=[str(a) for a in piv.index], colorscale=[[i / (len(T["heat"]) - 1), c] for i, c in enumerate(T["heat"])],
        text=[["" if pd.isna(v) else (f"{v:.1f}%" if ratio else f"{v:,.0f}") for v in row] for row in z],
        texttemplate="%{text}", textfont=dict(size=11, family=FUENTE), xgap=4, ygap=4, showscale=False,
        hovertemplate="%{x} %{y}: %{text}" + ("" if ratio else suf) + "<extra></extra>"))
    estilo(fig, 300, leyenda=False, ytick="")
    fig.update_layout(hovermode="closest")
    fig.update_yaxes(type="category", gridcolor="rgba(0,0,0,0)", tickfont=dict(color=T["text"], size=12))
    g_heat = fig
    t_heat = f"{lbl} por mes y año" + ("" if ratio else f" ({unidad.lower()})")

    # 5) Estacionalidad por ramo en el año elegido
    fig = go.Figure()
    a_r = anio_ramo if anio_ramo in anios_todos else (anios_todos or [None])[-1]
    for r in ramos:
        ir = indice(df, concepto, var, [r], [a_r], meses)
        if ir.empty or ir.iloc[0].isna().all():
            continue
        fig.add_scatter(x=xm, y=ir.iloc[0].values, name=f"Ramo {r}", mode="lines+markers",
                        line=dict(color=color_ramo(r, ramos_todos), width=2.2), marker=dict(size=6), hovertemplate="%{y:.2f}")
    fig.add_hline(y=1, line=dict(color=T["text3"], width=1, dash="dot"))
    estilo(fig, 300, "Índice", ytick=".2f")
    return t_comp, a_comp, lbl, lblp, g_comp, stats, t_anios, g_anios, t_heat, g_heat, fig


# ---- Descarga a Excel: el mismo tablero en un libro, una pestaña por sección ---------
XL = dict(bg="#E9EAEF", navy="#2F3A5F", card="#FFFFFF", tx="#1F2433", tx2="#5B6275", tx3="#8B90A0",
          acc="#F08A3C", acc_s="#F8C9A2", pos="#2E9E6B", pos_s="#E3F4EC", neg="#D64545", neg_s="#FBE7E7",
          nav_s="#ECEEF5", linea="#E3E5EC", grid="#EEF0F4", zebra="#F7F8FA")
XL_FUENTE = "Segoe UI"
XL_SECCIONES = [("01 Resumen", "⌂  Resumen"), ("02 Mes a mes", "▮  Mes a mes"), ("03 Estacionalidad", "∿  Estacionalidad"),
                ("04 Conceptos", "≋  Conceptos"), ("05 Detalle por ramo", "▦  Detalle por ramo"),
                ("06 Tabla mensualizada", "☰  Tabla mensualizada")]
XL_C0, XL_C1 = 3, 26          # columnas de contenido: D … AA (24 columnas de 64 px)
XL_COLPX, XL_ROWPX = 64, 20


def libro_excel(concepto, var, ramos, anios, meses, unidad, est_anios, prima, anio_ramo=None):
    """Arma el libro con el mismo diseño del tablero. Devuelve una función que escribe el .xlsx en un buffer."""
    import xlsxwriter
    from xlsxwriter.utility import xl_rowcol_to_cell

    df = ESTADO["df"]
    conceptos_todos, ramos_todos, anios_todos = catalogos(df)
    ramos, anios, meses = sorted(ramos or []), sorted(anios or []), sorted(meses or [])
    est_anios = sorted(est_anios or anios_todos)
    a_r = anio_ramo if anio_ramo in anios_todos else anios_todos[-1]
    div, suf = UNIDADES[unidad]
    ratio = var in RATIOS
    lbl, lblp = VARIABLES[var], PRIMAS[prima]
    per_txt = f"{anios[0]}–{anios[-1]}" if len(anios) > 1 else str(anios[0])
    m_txt = "Todos" if len(meses) == 12 else ", ".join(MESES[m - 1] for m in meses)
    xm = [MESES[m - 1] for m in meses]
    nf = "0.0%" if ratio else "#,##0.0"               # formato de la variable elegida
    esc = (lambda x: x) if ratio else (lambda x: x / div)
    unidad_txt = "%" if ratio else f"{unidad.lower()} de pesos"
    filtros = (f"Concepto {concepto}  ·  Variable {lbl}  ·  Ramos {', '.join(ramos)}  ·  Año {per_txt}  ·  "
               f"Mes {m_txt}  ·  En {unidad}")

    # ---------- cálculos: los mismos del tablero ----------
    kp = datos_kpis(df, concepto, ramos, anios, meses)
    tot = serie(df, concepto, var, ramos, anios, meses, por=("PERIODO",)).sort_values("PERIODO").reset_index(drop=True)
    comp, t_ramo = datos_por_ramo(df, concepto, var, ramos, anios, meses, per_txt)
    iv = indice(df, concepto, var, ramos, est_anios, meses)
    ip = indice(df, concepto, prima, ramos, est_anios, meses)
    lect = datos_lectura(iv, ip, meses)
    hs = serie(df, concepto, var, ramos, est_anios, meses, por=("ANIO", "MES"))
    heat = hs.pivot(index="ANIO", columns="MES", values="VALOR").reindex(index=est_anios, columns=meses)
    ir_ramo = {r: indice(df, concepto, var, [r], [a_r], meses) for r in ramos}
    conc_lista = [c for c in CONCEPTOS_ORDEN if c in set(df["CONCEPTO"])]
    conc = {c: serie(df, c, var, ramos, anios, meses, por=("PERIODO",)).set_index("PERIODO")["VALOR"] for c in conc_lista}
    det = {v: tabla_mensual(df, concepto, v, ramos, anios, meses) for v in DETALLE}
    tm = tabla_mensual(df, concepto, var, ramos, anios, meses)
    hero = serie(df, concepto, "RAM", ramos, anios, meses, por=("PERIODO",)).sort_values("PERIODO")
    logo_badge = base64.b64decode(LOGO_BADGE_B64)

    def escribir(buf):
        wb = xlsxwriter.Workbook(buf, {"in_memory": True, "nan_inf_to_errors": True})
        wb.set_properties({"title": "PRISMA · Proyección de reservas FCST 2027", "author": "PRISMA"})
        cache = {}

        def F(**kw):
            """Formato con caché. Claves cortas: bg, c (color de letra), b (negrita), s (tamaño), nf, al, va, wr, it."""
            k = tuple(sorted(kw.items()))
            if k not in cache:
                d = {"font_name": XL_FUENTE, "font_size": kw.get("s", 10), "font_color": kw.get("c", XL["tx"]),
                     "valign": kw.get("va", "vcenter")}
                if "bg" in kw: d["bg_color"] = kw["bg"]; d["pattern"] = 1
                if kw.get("b"): d["bold"] = True
                if kw.get("it"): d["italic"] = True
                if "nf" in kw: d["num_format"] = kw["nf"]
                if "al" in kw: d["align"] = kw["al"]
                if kw.get("wr"): d["text_wrap"] = True
                if kw.get("ind"): d["indent"] = kw["ind"]
                if "bt" in kw: d["top"] = 1; d["top_color"] = kw["bt"]
                if "bb" in kw: d["bottom"] = 1; d["bottom_color"] = kw["bb"]
                cache[k] = wb.add_format(d)
            return cache[k]

        # ---------- hoja oculta con los datos de todas las gráficas ----------
        pendientes = []          # bloques para la hoja oculta Datos_graficas (se escribe al final)
        cur = {"r": 0}

        def bloque(titulo, columnas, filas, formatos=None):
            """Escribe un bloque en Datos_graficas y devuelve una función ref(col) para las series."""
            r0 = cur["r"]
            pendientes.append((r0, titulo, list(columnas), [list(f) for f in filas], formatos or {}))
            r1, r2 = r0 + 2, r0 + 1 + len(filas)
            cur["r"] = r2 + 3
            return lambda col: ["Datos_graficas", r1, columnas.index(col), r2, columnas.index(col)]

        # ---------- piezas de diseño ----------
        def hoja(idx, titulo, sub):
            nombre = XL_SECCIONES[idx][0]
            ws = wb.add_worksheet(nombre)
            ws.hide_gridlines(2)
            ws.set_zoom(80)
            ws.set_default_row(15)          # 20 px
            ws.set_landscape()
            ws.fit_to_pages(1, 0)
            fondo = F(bg=XL["bg"])
            ws.set_column_pixels(0, 0, 10, fondo)
            ws.set_column_pixels(1, 1, 150, fondo)
            ws.set_column_pixels(2, 2, 16, fondo)
            ws.set_column_pixels(XL_C0, XL_C1, XL_COLPX, fondo)
            ws.set_column_pixels(XL_C1 + 1, XL_C1 + 1, 24, fondo)
            ws.set_column_pixels(XL_C1 + 2, 60, XL_COLPX, fondo)
            for r, px in [(0, 12), (1, 32), (2, 30), (3, 18), (4, 30), (5, 20), (6, 10)]:
                ws.set_row_pixels(r, px)
            # encabezado tipo píldora
            nv = F(bg=XL["navy"])
            for r in (1, 2):
                for c in range(XL_C0, XL_C1 + 1):
                    ws.write_blank(r, c, None, nv)
            ws.insert_image(1, XL_C0, "logo.png", {"image_data": io.BytesIO(logo_badge), "x_offset": 10, "y_offset": 6,
                                                  "x_scale": 50 / 160, "y_scale": 50 / 160, "object_position": 3})
            ws.merge_range(1, XL_C0 + 1, 1, XL_C0 + 5, "PRISMA", F(bg=XL["navy"], c="#FFFFFF", b=True, s=18, va="bottom"))
            ws.merge_range(2, XL_C0 + 1, 2, XL_C0 + 5, "Proyección de reservas · FCST 2027",
                           F(bg=XL["navy"], c="#C9CEDD", s=9, va="top"))
            ws.merge_range(1, XL_C0 + 6, 2, XL_C1 - 3, filtros, F(bg=XL["navy"], c="#FFFFFF", s=9, al="right", wr=True))
            ws.merge_range(1, XL_C1 - 2, 2, XL_C1, f"Excel · {datetime.now():%d/%m/%Y}",
                           F(bg=XL["acc"], c="#FFFFFF", b=True, s=10, al="center"))
            # riel de navegación (azul marino) con enlaces a cada pestaña
            for r in range(4, 80):
                ws.write_blank(r, 1, None, nv)
            for k, (hoja_dest, etiqueta) in enumerate(XL_SECCIONES):
                r = 8 + k * 2
                activo = k == idx
                ws.write_url(r, 1, f"internal:'{hoja_dest}'!A1",
                             F(bg=XL["navy"], c=XL["acc"] if activo else "#FFFFFF", b=activo, s=10, ind=1),
                             string=etiqueta)
            ws.write(8 + len(XL_SECCIONES) * 2 + 1, 1, "Base de datos en", F(bg=XL["navy"], c="#AEB5CB", s=8, ind=1))
            ws.write(8 + len(XL_SECCIONES) * 2 + 2, 1, "pestañas ocultas", F(bg=XL["navy"], c="#AEB5CB", s=8, ind=1))
            # título de la sección
            ws.write(4, XL_C0, f"{idx + 1:02d}", F(bg=XL["navy"], c="#FFFFFF", b=True, s=11, al="center"))
            ws.merge_range(4, XL_C0 + 1, 4, XL_C0 + 12, titulo, F(bg=XL["bg"], b=True, s=15, ind=1))
            ws.merge_range(5, XL_C0 + 1, 5, XL_C1, sub, F(bg=XL["bg"], c=XL["tx3"], s=10, ind=1))
            return ws

        def tarjeta(ws, r1, c1, r2, c2, titulo=None, ayuda=None, oscuro=False):
            bgc = XL["navy"] if oscuro else XL["card"]
            for r in range(r1, r2 + 1):
                for c in range(c1, c2 + 1):
                    ws.write_blank(r, c, None, F(bg=bgc))
            if titulo:
                ws.merge_range(r1, c1, r1, c2, titulo, F(bg=bgc, b=True, s=11, c="#FFFFFF" if oscuro else XL["tx"], ind=1, va="bottom"))
            if ayuda:
                ws.merge_range(r1 + 1, c1, r1 + 1, c2, ayuda, F(bg=bgc, s=9, c="#C9CEDD" if oscuro else XL["tx3"], ind=1, va="top"))

        def colocar(ws, ch, r1, c1, r2, c2, top=2):
            """Inserta la gráfica dentro de la tarjeta (debajo del título)."""
            w = (c2 - c1 + 1) * XL_COLPX - 16
            h = (r2 - (r1 + top) + 1) * XL_ROWPX - 8
            ch.set_size({"width": w, "height": h})
            ws.insert_chart(r1 + top, c1, ch, {"x_offset": 8, "y_offset": 2, "object_position": 3})

        def estilo_ch(ch, leyenda=False, y_fmt="#,##0", y_min=None, y_max=None, oscuro=False, barra=False,
                      x_visible=True, y_visible=True):
            ch.set_chartarea({"border": {"none": True}, "fill": {"color": XL["navy"] if oscuro else XL["card"]}})
            ch.set_plotarea({"border": {"none": True}, "fill": {"none": True}})
            ch.set_legend({"position": "top", "font": {"name": XL_FUENTE, "size": 9, "color": XL["tx2"]}} if leyenda
                          else {"none": True})
            cat = {"num_font": {"name": XL_FUENTE, "size": 9, "color": XL["tx3"]}, "line": {"color": XL["linea"]},
                   "major_tick_mark": "none", "visible": x_visible}
            val = {"num_font": {"name": XL_FUENTE, "size": 9, "color": XL["tx3"]}, "num_format": y_fmt,
                   "line": {"none": True}, "major_tick_mark": "none", "visible": y_visible,
                   "major_gridlines": {"visible": y_visible, "line": {"color": XL["grid"]}}}
            if y_min is not None: val["min"] = y_min
            if y_max is not None: val["max"] = y_max
            ch.set_title({"none": True})
            if barra:   # en barras horizontales Excel usa x = valores (horizontal) y y = categorías (vertical)
                cat.update({"line": {"none": True}, "num_font": {"name": XL_FUENTE, "size": 10, "color": XL["tx"]}})
                ch.set_x_axis(val)
                ch.set_y_axis(cat)
            else:
                ch.set_x_axis(cat)
                ch.set_y_axis(val)

        etiqueta = lambda nfmt, color=None, pos="outside_end": {
            "value": True, "num_format": nfmt, "position": pos,
            "font": {"name": XL_FUENTE, "size": 8, "color": color or XL["tx2"]}}

        def badge(ws, r, c1, c2, variacion, es_ratio, oscuro=False):
            if variacion is None:
                ws.merge_range(r, c1, r, c2, "sin comparativo", F(bg=XL["navy"] if oscuro else XL["card"], c=XL["tx3"], s=9))
                return
            dv = variacion * 100
            sube = dv >= 0
            txt = f"{'▲' if sube else '▼'} {abs(dv):.1f}{' pp' if es_ratio else '%'}"
            ws.merge_range(r, c1, r, c2, txt, F(bg=XL["pos_s"] if sube else XL["neg_s"], c=XL["pos"] if sube else XL["neg"],
                                               b=True, s=9, al="center"))

        def tabla(ws, r, c1, columnas, filas, anchos, formatos, total_col=None):
            """Tabla con encabezado azul marino y renglones cebra. anchos = nº de columnas de Excel por campo."""
            c = c1
            for col, w in zip(columnas, anchos):
                al = "left" if col == columnas[0] else "right"
                f = F(bg=XL["navy"], c="#FFFFFF", b=True, s=9, al=al, ind=1)
                (ws.merge_range(r, c, r, c + w - 1, col, f) if w > 1 else ws.write(r, c, col, f))
                c += w
            for i, fila in enumerate(filas, start=1):
                bgc = XL["card"] if i % 2 else XL["zebra"]
                c = c1
                for col, w, v in zip(columnas, anchos, fila):
                    es_tot = col == total_col
                    f = F(bg=bgc, s=10, al="left" if col == columnas[0] else "right", ind=1, b=es_tot or col == columnas[0],
                          c=XL["navy"] if es_tot else XL["tx"], nf=formatos.get(col, "General"), bb=XL["linea"])
                    if v is None or (isinstance(v, float) and np.isnan(v)):
                        v = "N/A"
                    (ws.merge_range(r + i, c, r + i, c + w - 1, v, f) if w > 1 else ws.write(r + i, c, v, f))
                    c += w
            return r + len(filas)

        # =================== 01 RESUMEN ===================
        ws = hoja(0, "Resumen", "Cifras clave al cierre del periodo filtrado y su cambio contra el año anterior (AA).")
        iconos = {"RAM": "🛡", "PRIMA 24M": "◷", "PR 24M": "◔", "MA": "▣", "RFV MA": "↗", "CESION": "⇄", "PT": "$"}
        # tarjeta principal (Reserva)
        k0 = kp[0]
        tarjeta(ws, 7, XL_C0, 21, XL_C0 + 5, oscuro=True)
        ws.merge_range(7, XL_C0, 7, XL_C0 + 5, f"{iconos['RAM']}  {k0['nombre']}", F(bg=XL["navy"], c="#C9CEDD", s=11, ind=1))
        ws.set_row_pixels(8, 30); ws.set_row_pixels(9, 26)
        ws.merge_range(8, XL_C0, 9, XL_C0 + 5, fmt(k0["actual"], unidad), F(bg=XL["navy"], c="#FFFFFF", b=True, s=28, ind=1))
        ws.merge_range(10, XL_C0, 10, XL_C0 + 2, f"AA: {fmt(k0['anterior'], unidad)}", F(bg=XL["navy"], c="#C9CEDD", s=9, ind=1))
        badge(ws, 10, XL_C0 + 3, XL_C0 + 4, k0["variacion"], False, oscuro=True)
        ws.merge_range(12, XL_C0, 12, XL_C0 + 5, "Tendencia del periodo filtrado", F(bg=XL["navy"], c="#AEB5CB", s=9, ind=1))
        ws.merge_range(21, XL_C0, 21, XL_C0 + 5, k0["referencia"], F(bg=XL["navy"], c="#AEB5CB", s=9, ind=1, bt="#56607F"))
        ref = bloque("Tendencia de la reserva (tarjeta principal)", ["Mes", "Reserva"],
                     [[mes_txt(p), v / div] for p, v in zip(hero["PERIODO"], hero["VALOR"])])
        ch = wb.add_chart({"type": "area"})
        ch.add_series({"categories": ref("Mes"), "values": ref("Reserva"), "name": "Reserva",
                       "fill": {"color": "#FFFFFF", "transparency": 88}, "line": {"color": XL["acc"], "width": 2.25}})
        vmin = hero["VALOR"].min() / div if len(hero) else 0
        estilo_ch(ch, oscuro=True, x_visible=False, y_visible=False, y_min=vmin * 0.9)
        colocar(ws, ch, 13, XL_C0, 20, XL_C0 + 5, top=0)
        # 6 tarjetas blancas (3 × 2)
        posiciones = [(7, XL_C0 + 6), (7, XL_C0 + 12), (7, XL_C0 + 18), (14, XL_C0 + 6), (14, XL_C0 + 12), (14, XL_C0 + 18)]
        for k, (r, c) in zip(kp[1:], posiciones):
            r2 = 21 if r == 14 else r + 5
            tarjeta(ws, r, c, r2, c + 5)
            ws.merge_range(r, c, r, c + 5, f"{iconos[k['variable']]}  {k['nombre']}", F(bg=XL["card"], c=XL["tx2"], s=10, ind=1))
            ws.merge_range(r + 1, c, r + 2, c + 5, fmt(k["actual"], unidad, k["ratio"]), F(bg=XL["card"], b=True, s=18, ind=1))
            ws.merge_range(r + 3, c, r + 3, c + 2, f"AA: {fmt(k['anterior'], unidad, k['ratio'])}",
                           F(bg=XL["card"], c=XL["tx3"], s=9, ind=1))
            badge(ws, r + 3, c + 3, c + 4, k["variacion"], k["ratio"])
            ws.merge_range(r2, c, r2, c + 5, k["referencia"], F(bg=XL["card"], c=XL["tx3"], s=9, ind=1, bt=XL["linea"]))
        # filtros y guía
        tarjeta(ws, 23, XL_C0, 31, XL_C0 + 11, "Filtros aplicados", "Así se generó este libro desde PRISMA.")
        items = [("Concepto", concepto), ("Variable", lbl), ("Ramos", ", ".join(ramos)), ("Años", per_txt),
                 ("Meses", m_txt), ("Unidades", unidad), ("Estacionalidad", f"Años {', '.join(map(str, est_anios))} · vs. {lblp}")]
        for i, (k_, v_) in enumerate(items):
            ws.merge_range(25 + i, XL_C0, 25 + i, XL_C0 + 2, k_, F(bg=XL["card"], c=XL["tx3"], s=10, ind=1))
            ws.merge_range(25 + i, XL_C0 + 3, 25 + i, XL_C0 + 11, v_, F(bg=XL["card"], b=True, s=10))
        tarjeta(ws, 23, XL_C0 + 12, 31, XL_C1, "Cómo leer este libro", "Cada pestaña es una sección del tablero.")
        guia = ["Usa el menú azul de la izquierda para cambiar de sección.",
                "AA = mismo mes del año anterior. Verde: subió · Rojo: bajó.",
                "Montos en " + unidad.lower() + " de pesos; Cesión en %.",
                "Índice estacional 1.00 = mes promedio de su año.",
                "Datos de las gráficas: pestaña oculta Datos_graficas.",
                "Base completa: pestaña oculta BD_Proyeccion.",
                "Para verlas: clic derecho en una pestaña › Mostrar."]
        for i, g in enumerate(guia):
            ws.merge_range(25 + i, XL_C0 + 12, 25 + i, XL_C1, "•  " + g, F(bg=XL["card"], c=XL["tx2"], s=10, ind=1))
        ws.activate()

        # =================== 02 MES A MES ===================
        ws = hoja(1, "Mes a mes", "Cómo se reparte el monto en cada mes y qué ramos lo explican.")
        tarjeta(ws, 7, XL_C0, 27, XL_C0 + 16, f"{lbl} por mes · {concepto}",
                "Cada barra es el total del mes. La línea naranja punteada es el promedio."
                + (" Más oscuro = año más reciente." if len(anios) > 1 else ""))
        prom = esc(tot["VALOR"]).mean() if len(tot) else np.nan
        cols = ["Mes"] + [str(a) for a in anios] + ["Promedio"]
        filas = []
        for p, v in zip(tot["PERIODO"], tot["VALOR"]):
            filas.append([mes_txt(p)] + [esc(v) if p // 100 == a else None for a in anios] + [prom])
        ref = bloque(f"{lbl} por mes", cols, filas, {c: ("0.0000" if ratio else "#,##0.0") for c in cols[1:]})
        if ratio:
            ch = wb.add_chart({"type": "line"})
            for a in anios:
                ser = {"name": str(a), "categories": ref("Mes"), "values": ref(str(a)),
                       "line": {"color": color_anio(a, anios), "width": 2.5},
                       "marker": {"type": "circle", "size": 6, "fill": {"color": color_anio(a, anios)},
                                  "border": {"color": color_anio(a, anios)}}}
                if len(tot) <= 12:
                    ser["data_labels"] = etiqueta("0.0%", pos="above")
                ch.add_series(ser)
            base_ch = ch
        else:
            ch = wb.add_chart({"type": "column"})
            for a in anios:
                ser = {"name": str(a), "categories": ref("Mes"), "values": ref(str(a)),
                       "fill": {"color": color_anio(a, anios)}, "border": {"none": True}, "gap": 45, "overlap": 100}
                if len(tot) <= 24:
                    ser["data_labels"] = etiqueta("#,##0.0")
                ch.add_series(ser)
            base_ch = ch
        ln = wb.add_chart({"type": "line"})
        ln.add_series({"name": "Promedio", "categories": ref("Mes"), "values": ref("Promedio"),
                       "line": {"color": XL["acc"], "width": 1.75, "dash_type": "dash"}, "marker": {"type": "none"}})
        base_ch.combine(ln)
        estilo_ch(base_ch, leyenda=True, y_fmt="0.0%" if ratio else "#,##0", y_min=None if ratio else 0)
        colocar(ws, base_ch, 7, XL_C0, 27, XL_C0 + 16)

        tarjeta(ws, 7, XL_C0 + 17, 27, XL_C1, t_ramo, "Cuánto aporta cada ramo y qué % representa del total.")
        filas = [["Ramo " + r, esc(v), p] for r, v, p in zip(comp["RAMO"], comp["VALOR"], comp["PART"])]
        ref = bloque(t_ramo, ["Ramo", "Monto", "% del total"], filas, {"Monto": "0.0000" if ratio else "#,##0.0", "% del total": "0.0%"})
        ch = wb.add_chart({"type": "bar"})
        etiquetas_ramo = [{"value": (f"{v * 100:.1f}%" if ratio else f"{v:,.1f}{suf}  ·  {(p if pd.notna(p) else 0) * 100:.1f}%")}
                          for _, v, p in filas]
        ch.add_series({"name": "Por ramo", "categories": ref("Ramo"), "values": ref("Monto"),
                       "fill": {"color": XL["navy"]}, "border": {"none": True}, "gap": 70,
                       "data_labels": {"custom": etiquetas_ramo, "position": "outside_end",
                                       "font": {"name": XL_FUENTE, "size": 9, "color": XL["tx"]}}})
        mx = max([v for _, v, _ in filas] or [1])
        estilo_ch(ch, barra=True, y_fmt=nf, y_min=0, y_max=mx * 1.75, y_visible=False)
        colocar(ws, ch, 7, XL_C0 + 17, 27, XL_C1)

        tarjeta(ws, 29, XL_C0, 43, XL_C1, "Cambio contra el mes anterior", "Verde: el monto subió. Rojo: bajó.")
        delta = esc(tot["VALOR"]).diff() * (100 if ratio else 1)
        filas = [[mes_txt(p), d if (pd.notna(d) and d >= 0) else None, d if (pd.notna(d) and d < 0) else None]
                 for p, d in zip(tot["PERIODO"], delta)]
        ref = bloque("Cambio contra el mes anterior" + (" (pp)" if ratio else f" ({unidad})"), ["Mes", "Sube", "Baja"], filas)
        ch = wb.add_chart({"type": "column"})
        for nombre_s, col in (("Sube", XL["pos"]), ("Baja", XL["neg"])):
            ser = {"name": nombre_s, "categories": ref("Mes"), "values": ref(nombre_s), "fill": {"color": col},
                   "border": {"none": True}, "gap": 60, "overlap": 100}
            if len(filas) <= 24:
                ser["data_labels"] = etiqueta("+#,##0.0;-#,##0.0")
            ch.add_series(ser)
        estilo_ch(ch, y_fmt="#,##0.0")
        ch.set_x_axis({"num_font": {"name": XL_FUENTE, "size": 9, "color": XL["tx3"]}, "line": {"color": XL["linea"]},
                       "major_tick_mark": "none", "label_position": "low"})
        colocar(ws, ch, 29, XL_C0, 43, XL_C1)

        n = len(tot)
        tarjeta(ws, 45, XL_C0, 45 + n + 3, XL_C0 + 11, "Datos del mes", f"{lbl} y cambio contra el mes anterior ({unidad_txt}).")
        tabla(ws, 47, XL_C0, ["Mes", lbl, "Cambio"], [[mes_txt(p), esc(v), d] for p, v, d in zip(tot["PERIODO"], tot["VALOR"], delta / (100 if ratio else 1))],
              [4, 4, 4], {lbl: nf, "Cambio": ("+0.00%;-0.00%" if ratio else "+#,##0.0;-#,##0.0")})
        tarjeta(ws, 45, XL_C0 + 12, 45 + len(comp) + 3, XL_C1, "Datos por ramo", t_ramo)
        if ratio:
            tabla(ws, 47, XL_C0 + 12, ["Ramo", lbl], [["Ramo " + r, v] for r, v in zip(comp["RAMO"][::-1], comp["VALOR"][::-1])],
                  [6, 7], {lbl: nf})
        else:
            tabla(ws, 47, XL_C0 + 12, ["Ramo", lbl, "% del total"],
                  [["Ramo " + r, esc(v), p] for r, v, p in zip(comp["RAMO"][::-1], comp["VALOR"][::-1], comp["PART"][::-1])],
                  [4, 4, 5], {lbl: nf, "% del total": "0.0%"})

        # =================== 03 ESTACIONALIDAD ===================
        ws = hoja(2, "Estacionalidad", f"¿En qué meses el monto está por arriba o por abajo de lo normal? Años "
                                       f"{', '.join(map(str, est_anios))} · comparado con {lblp.lower()}.")
        tarjeta(ws, 7, XL_C0, 26, XL_C1, f"{lbl} vs. {lblp}, año por año",
                f"Un panel por año. Barras naranjas: {lblp.lower()}. Línea azul: {lbl.lower()}. "
                "Arriba de 1.00 el mes está por encima del promedio de su año; abajo, por debajo.")
        cols = ["Mes"] + [f"{lbl} {a}" for a in est_anios] + [f"Prima {a}" for a in est_anios] + ["Base 1.00"]
        filas = [[xm[j]] + [iv.loc[a].iloc[j] for a in est_anios] + [ip.loc[a].iloc[j] for a in est_anios] + [1.0]
                 for j in range(len(meses))]
        ref = bloque(f"Índice estacional · {lbl} y {lblp}", cols, filas)
        tope = np.nanmax(np.concatenate([iv.values.ravel(), ip.values.ravel(), [1.2]]))
        tope = float(np.ceil(tope * 5) / 5)

        def piso(*arrs):
            vals = np.concatenate([np.asarray(a_, dtype=float).ravel() for a_ in arrs] + [np.array([1.0])])
            return float(np.floor((np.nanmin(vals) - 0.03) * 20) / 20)
        n_a = len(est_anios)
        ancho = (XL_C1 - XL_C0 + 1) // n_a
        for i, a in enumerate(est_anios):
            ch = wb.add_chart({"type": "column"})
            ch.add_series({"name": lblp, "categories": ref("Mes"), "values": ref(f"Prima {a}"),
                           "fill": {"color": XL["acc_s"]}, "border": {"none": True}, "gap": 40})
            ln = wb.add_chart({"type": "line"})
            ln.add_series({"name": lbl, "categories": ref("Mes"), "values": ref(f"{lbl} {a}"),
                           "line": {"color": XL["navy"], "width": 2.75},
                           "marker": {"type": "circle", "size": 5, "fill": {"color": XL["navy"]}, "border": {"color": "#FFFFFF"}}})
            ln.add_series({"name": "Promedio (1.00)", "categories": ref("Mes"), "values": ref("Base 1.00"),
                           "line": {"color": XL["tx3"], "width": 1, "dash_type": "round_dot"}, "marker": {"type": "none"}})
            ch.combine(ln)
            estilo_ch(ch, leyenda=(i == 0), y_fmt="0.00", y_min=0, y_max=tope)
            ch.set_title({"name": str(a), "name_font": {"name": XL_FUENTE, "size": 12, "bold": True, "color": XL["tx"]},
                          "overlay": False})
            c1 = XL_C0 + i * ancho
            colocar(ws, ch, 7, c1, 26, c1 + ancho - 1)

        tarjeta(ws, 28, XL_C0, 42, XL_C0 + 10, "Lectura por año",
                "Correlación cercana a +1: se mueve igual que la prima. Amplitud = índice más alto − más bajo.")
        tabla(ws, 30, XL_C0, ["Año", "Correlación", "Pico var.", "Pico prima", "Amp. var.", "Amp. prima"],
              [[int(r["Año"]), r["Correlación"], r["Mes pico variable"], r["Mes pico prima"], r["Amplitud variable"],
                r["Amplitud prima"]] for _, r in lect.iterrows()],
              [1, 2, 2, 2, 2, 2], {"Correlación": "+0.00;-0.00", "Amp. var.": "0.00", "Amp. prima": "0.00", "Año": "0"})
        ws.merge_range(31 + len(lect) + 1, XL_C0, 31 + len(lect) + 3, XL_C0 + 10,
                       "Una reserva es un saldo: normalmente se mueve menos que la prima del mes, por eso su amplitud es menor.",
                       F(bg=XL["card"], c=XL["tx3"], s=9, wr=True, ind=1, va="top"))

        tarjeta(ws, 28, XL_C0 + 11, 42, XL_C1, f"Comparación entre años · {lbl}",
                "Mismo índice de la variable, un color por año (más oscuro = más reciente).")
        ch = wb.add_chart({"type": "line"})
        for a in est_anios:
            col = color_anio(a, est_anios)
            ch.add_series({"name": str(a), "categories": ref("Mes"), "values": ref(f"{lbl} {a}"),
                           "line": {"color": col, "width": 2.75 if a == est_anios[-1] else 2},
                           "marker": {"type": "circle", "size": 5, "fill": {"color": col}, "border": {"color": col}}})
        ch.add_series({"name": "1.00", "categories": ref("Mes"), "values": ref("Base 1.00"),
                       "line": {"color": XL["tx3"], "width": 1, "dash_type": "round_dot"}, "marker": {"type": "none"}})
        estilo_ch(ch, leyenda=True, y_fmt="0.00", y_min=piso(iv.values))
        colocar(ws, ch, 28, XL_C0 + 11, 42, XL_C1)

        r_h = 44
        tarjeta(ws, r_h, XL_C0, r_h + len(est_anios) + 4, XL_C0 + 13,
                f"{lbl} por mes y año" + ("" if ratio else f" ({unidad.lower()})"), "Entre más oscuro el color, mayor el monto.")
        ws.write(r_h + 2, XL_C0, "Año", F(bg=XL["card"], c=XL["tx3"], b=True, s=9, al="center"))
        for j, m in enumerate(xm):
            ws.write(r_h + 2, XL_C0 + 1 + j, m, F(bg=XL["card"], c=XL["tx3"], b=True, s=9, al="center"))
        hz = heat if ratio else heat / div
        for i, a in enumerate(est_anios):
            ws.set_row_pixels(r_h + 3 + i, 34)
            ws.write(r_h + 3 + i, XL_C0, a, F(bg=XL["card"], b=True, s=10, al="center"))
            for j in range(len(meses)):
                v = hz.loc[a].iloc[j]
                f = F(bg="#F3F4F8", s=10, al="center", nf="0.0%" if ratio else "#,##0")
                if pd.isna(v):
                    ws.write_blank(r_h + 3 + i, XL_C0 + 1 + j, None, f)
                else:
                    ws.write_number(r_h + 3 + i, XL_C0 + 1 + j, float(v), f)
        rng = (r_h + 3, XL_C0 + 1, r_h + 2 + len(est_anios), XL_C0 + len(meses))
        ws.conditional_format(*rng, {"type": "3_color_scale", "min_color": "#F3F4F8", "mid_color": "#9BA5CF", "max_color": XL["navy"]})
        valores = hz.values[~np.isnan(hz.values)] if hz.size else np.array([])
        if valores.size:
            corte = float(np.percentile(valores, 55))
            ws.conditional_format(*rng, {"type": "cell", "criteria": ">=", "value": corte,
                                         "format": wb.add_format({"font_color": "#FFFFFF", "bold": True})})

        tarjeta(ws, r_h, XL_C0 + 14, r_h + 16, XL_C1, f"Estacionalidad por ramo · {a_r}",
                "Patrón mensual de cada ramo en el año elegido (1.00 = mes promedio).")
        cols = ["Mes"] + [f"Ramo {r}" for r in ramos] + ["Base 1.00"]
        filas = [[xm[j]] + [(ir_ramo[r].iloc[0].iloc[j] if not ir_ramo[r].empty else None) for r in ramos] + [1.0]
                 for j in range(len(meses))]
        ref = bloque(f"Estacionalidad por ramo · {a_r}", cols, filas)
        ch = wb.add_chart({"type": "line"})
        for r in ramos:
            if ir_ramo[r].empty or ir_ramo[r].iloc[0].isna().all():
                continue
            col = color_ramo(r, ramos_todos)
            ch.add_series({"name": f"Ramo {r}", "categories": ref("Mes"), "values": ref(f"Ramo {r}"),
                           "line": {"color": col, "width": 2}, "marker": {"type": "circle", "size": 4,
                                                                          "fill": {"color": col}, "border": {"color": col}}})
        ch.add_series({"name": "1.00", "categories": ref("Mes"), "values": ref("Base 1.00"),
                       "line": {"color": XL["tx3"], "width": 1, "dash_type": "round_dot"}, "marker": {"type": "none"}})
        estilo_ch(ch, leyenda=True, y_fmt="0.00",
                  y_min=piso(*[ir_ramo[r].values for r in ramos if not ir_ramo[r].empty]))
        colocar(ws, ch, r_h, XL_C0 + 14, r_h + 16, XL_C1)

        # =================== 04 CONCEPTOS ===================
        ws = hoja(3, "Conceptos", "Los cuatro cálculos de la reserva lado a lado: RCONT, RFV bruto, RFV IRR y RFV neto.")
        tarjeta(ws, 7, XL_C0, 28, XL_C1, f"{lbl} por concepto",
                f"Cada línea es un concepto; la más gruesa es el concepto filtrado ({concepto}).")
        periodos = sorted(set().union(*[set(s.index) for s in conc.values()])) if conc else []
        cols = ["Mes"] + conc_lista
        filas = [[mes_txt(p)] + [esc(conc[c].get(p, np.nan)) for c in conc_lista] for p in periodos]
        ref = bloque(f"{lbl} por concepto", cols, filas)
        ch = wb.add_chart({"type": "line"})
        for c in conc_lista:
            col = T["conceptos"].get(c, XL["tx3"])
            ch.add_series({"name": c, "categories": ref("Mes"), "values": ref(c),
                           "line": {"color": col, "width": 3.5 if c == concepto else 2}, "marker": {"type": "none"}})
        estilo_ch(ch, leyenda=True, y_fmt="0.0%" if ratio else "#,##0")
        colocar(ws, ch, 7, XL_C0, 28, XL_C1)
        tarjeta(ws, 30, XL_C0, 30 + len(filas) + 3, XL_C1, "Datos por concepto", f"{lbl} en {unidad_txt}.")
        tabla(ws, 32, XL_C0, cols, filas, [4, 5, 5, 5, 5][:len(cols)] if len(cols) <= 5 else [4] + [4] * (len(cols) - 1),
              {c: nf for c in conc_lista}, total_col=concepto)

        # =================== 05 DETALLE POR RAMO ===================
        ws = hoja(4, "Detalle por ramo", "Evolución de cada variable, separada por ramo.")
        for i, r in enumerate(ramos):
            ws.merge_range(4, XL_C1 - 2 * (len(ramos) - i) + 1, 4, XL_C1 - 2 * (len(ramos) - i) + 2, f"● Ramo {r}",
                           F(bg=XL["bg"], c=color_ramo(r, ramos_todos), b=True, s=10, al="center"))
        cajas = [(7, XL_C0), (7, XL_C0 + 8), (7, XL_C0 + 16), (23, XL_C0), (23, XL_C0 + 8), (23, XL_C0 + 16)]
        for v, (r1, c1) in zip(DETALLE, cajas):
            es_r = v in RATIOS
            tv = det[v]
            tarjeta(ws, r1, c1, r1 + 14, c1 + 7, VARIABLES[v], "%" if es_r else f"{unidad} de pesos")
            cols = ["Mes"] + [f"Ramo {r}" for r in ramos]
            filas = [[mes_txt(p)] + [(row.get(f"Ramo {r}", np.nan) if es_r else row.get(f"Ramo {r}", np.nan) / div)
                                     for r in ramos] for p, row in tv.iterrows()]
            ref = bloque(f"Detalle por ramo · {VARIABLES[v]}", cols, filas)
            ch = wb.add_chart({"type": "line"})
            for j, r in enumerate(ramos):
                vals = [f_[1 + j] for f_ in filas]
                if np.nansum(np.abs(np.array(vals, dtype=float))) == 0:
                    continue
                ch.add_series({"name": f"Ramo {r}", "categories": ref("Mes"), "values": ref(f"Ramo {r}"),
                               "line": {"color": color_ramo(r, ramos_todos), "width": 2}, "marker": {"type": "none"}})
            estilo_ch(ch, y_fmt="0%" if es_r else "#,##0")
            colocar(ws, ch, r1, c1, r1 + 14, c1 + 7)

        # =================== 06 TABLA MENSUALIZADA ===================
        ws = hoja(5, "Tabla mensualizada", "Los números detrás de las gráficas.")
        vista = tm if ratio else tm / div
        cols = ["Mes"] + [f"{c} ({'%' if ratio else unidad})" for c in vista.columns]
        n_c = len(cols)
        anchos = [3] + [max(2, (XL_C1 - XL_C0 + 1 - 3) // (n_c - 1))] * (n_c - 1)
        tarjeta(ws, 7, XL_C0, 7 + len(vista) + 3, XL_C0 + sum(anchos) - 1, f"{lbl} · {concepto}",
                f"Mensualización por ramo en {unidad_txt}. Total en azul.")
        tabla(ws, 9, XL_C0, cols, [[mes_txt(p)] + list(row.values) for p, row in vista.iterrows()], anchos,
              {c: nf for c in cols[1:]}, total_col=cols[-1])

        # =================== HOJAS OCULTAS ===================
        wd = wb.add_worksheet("Datos_graficas")
        wd.set_column(0, 0, 26)
        wd.set_column(1, 30, 14)
        for r0, titulo, columnas, filas, formatos in pendientes:
            wd.write(r0, 0, titulo, F(b=True, c=XL["navy"], s=11))
            for j, c in enumerate(columnas):
                wd.write(r0 + 1, j, c, F(b=True, c="#FFFFFF", bg=XL["navy"]))
            for i, fila in enumerate(filas, start=r0 + 2):
                for j, v in enumerate(fila):
                    if v is None or (isinstance(v, float) and np.isnan(v)):
                        wd.write_blank(i, j, None)
                    elif isinstance(v, (int, float, np.integer, np.floating)):
                        wd.write_number(i, j, float(v), F(nf=formatos.get(columnas[j], "#,##0.00")))
                    else:
                        wd.write(i, j, str(v))
        wd.hide()
        wb_bd = wb.add_worksheet("BD_Proyeccion")
        base = df.drop(columns="FECHA").assign(VARIABLE_NOMBRE=lambda d: d["VARIABLE"].map(VARIABLES))
        base = base[["CONCEPTO", "PERIODO", "ANIO", "MES", "RAMO", "VARIABLE", "VARIABLE_NOMBRE", "VALOR"]]
        datos_bd = [[None if (isinstance(x, float) and np.isnan(x)) else (x.item() if hasattr(x, "item") else x)
                     for x in fila] for fila in base.itertuples(index=False)]
        wb_bd.add_table(0, 0, len(datos_bd), len(base.columns) - 1,
                        {"data": datos_bd, "name": "BD_Proyeccion", "style": "Table Style Medium 2",
                         "columns": [({"header": c, "format": F(nf="#,##0.00")} if c.startswith("VALOR") else {"header": c})
                                     for c in ["CONCEPTO", "PERIODO", "AÑO", "MES", "RAMO", "CLAVE", "VARIABLE", "VALOR (pesos)"]]})
        wb_bd.set_column(0, 6, 14)
        wb_bd.set_column(7, 7, 20)
        wb_bd.freeze_panes(1, 0)
        wb_bd.hide()
        wb.close()

    return escribir


@app.callback(Output("dl", "data"), Input("btn-xls", "n_clicks"), Input("btn-xls2", "n_clicks"),
              Input("rail-xls", "n_clicks"),
              *[State(i.component_id, i.component_property) for i in ENTRADAS[:6]],
              State("est-anios", "value"), State("est-prima", "value"), State("est-ramo-anio", "value"),
              prevent_initial_call=True)
def descargar(_a, _b, _c, concepto, var, ramos, anios, meses, unidad, est_anios, prima, anio_ramo):
    if not (ramos and anios and meses):
        return no_update
    return dcc.send_bytes(libro_excel(concepto, var, ramos, anios, meses, unidad, est_anios, prima, anio_ramo),
                          f"PRISMA_Reservas_{datetime.now():%Y%m%d_%H%M}.xlsx")


# --------------------------------------------------------------------------------------
if __name__ == "__main__":
    url = f"http://127.0.0.1:{PUERTO}"
    print(f"\nPRISMA listo en {url}  (Ctrl + C para detener)\n")
    if not os.environ.get("RFV_NO_BROWSER"):
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    app.run(debug=False, port=PUERTO, host="127.0.0.1")
