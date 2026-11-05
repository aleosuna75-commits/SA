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
        html.Div([html.Span(className="dot-brand"),
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
.dot-brand { width:22px; height:22px; border-radius:50%; background:radial-gradient(circle at 35% 35%, #ffb27a, var(--acc)); box-shadow:0 0 0 4px rgba(240,138,60,.18); }
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


# ---- Descarga a Excel: una pestaña por sección -----------------------------------------
def libro_excel(concepto, var, ramos, anios, meses, unidad, est_anios, prima):
    df = ESTADO["df"]
    ramos, anios, meses = sorted(ramos or []), sorted(anios or []), sorted(meses or [])
    est_anios = sorted(est_anios or anios)
    div, _ = UNIDADES[unidad]
    ratio = var in RATIOS
    lbl, lblp = VARIABLES[var], PRIMAS[prima]
    per_txt = f"{anios[0]}–{anios[-1]}" if len(anios) > 1 else str(anios[0])
    filtros = (f"Concepto: {concepto} · Variable: {lbl} · Ramos: {', '.join(ramos)} · Años: {per_txt} · "
               f"Meses: {'Todos' if len(meses) == 12 else ', '.join(MESES[m - 1] for m in meses)} · Unidades: {unidad}")
    monto = lambda s: s / div   # montos en las unidades elegidas
    hojas = {}

    # Resumen
    k = pd.DataFrame(datos_kpis(df, concepto, ramos, anios, meses))
    res = pd.DataFrame({
        "Indicador": k["nombre"],
        "Valor": [v if r else (v / div if v is not None else None) for v, r in zip(k["actual"], k["ratio"])],
        "Año anterior (AA)": [v if r else (v / div if v is not None and not pd.isna(v) else None) for v, r in zip(k["anterior"], k["ratio"])],
        "Variación": k["variacion"], "Tipo de variación": ["pp" if r else "%" for r in k["ratio"]],
        "Referencia": k["referencia"]})
    hojas["1 Resumen"] = [("Cifras clave vs. año anterior", res, {"Valor": "auto", "Año anterior (AA)": "auto",
                                                                 "Variación": "pct"})]

    # Mes a mes
    tot = serie(df, concepto, var, ramos, anios, meses, por=("PERIODO",)).sort_values("PERIODO")
    mm = pd.DataFrame({"Mes": [mes_txt(p) for p in tot["PERIODO"]],
                       lbl: tot["VALOR"].values if ratio else monto(tot["VALOR"]).values})
    mm["Cambio vs. mes anterior"] = mm[lbl].diff()
    comp, t_ramo = datos_por_ramo(df, concepto, var, ramos, anios, meses, per_txt)
    pr = pd.DataFrame({"Ramo": ["Ramo " + r for r in comp["RAMO"]][::-1],
                       lbl: (comp["VALOR"] if ratio else monto(comp["VALOR"])).values[::-1],
                       "% del total": comp["PART"].values[::-1]})
    fmt_m = "pct" if ratio else "num"
    hojas["2 Mes a mes"] = [(f"{lbl} por mes · {concepto}", mm, {lbl: fmt_m, "Cambio vs. mes anterior": fmt_m}),
                            (t_ramo, pr, {lbl: fmt_m, "% del total": "pct"})]

    # Estacionalidad
    iv = indice(df, concepto, var, ramos, est_anios, meses)
    ip = indice(df, concepto, prima, ramos, est_anios, meses)
    lab = lambda p: p.rename(columns=lambda m: MESES[m - 1]).rename_axis("Año").reset_index()
    s = serie(df, concepto, var, ramos, est_anios, meses, por=("ANIO", "MES"))
    piv = s.pivot(index="ANIO", columns="MES", values="VALOR").reindex(index=est_anios, columns=meses)
    piv = piv if ratio else piv / div
    meses_cols = {MESES[m - 1]: "idx" for m in meses}
    hojas["3 Estacionalidad"] = [
        (f"Índice estacional · {lbl} (1.00 = mes promedio de su año)", lab(iv), meses_cols),
        (f"Índice estacional · {lblp}", lab(ip), meses_cols),
        ("Lectura por año", datos_lectura(iv, ip, meses),
         {"Correlación": "idx", "Amplitud variable": "idx", "Amplitud prima": "idx"}),
        (f"{lbl} por mes y año", lab(piv), {MESES[m - 1]: fmt_m for m in meses}),
    ]

    # Conceptos
    con = None
    for c in [c for c in CONCEPTOS_ORDEN if c in set(df["CONCEPTO"])]:
        sc = serie(df, c, var, ramos, anios, meses, por=("PERIODO",)).set_index("PERIODO")["VALOR"]
        sc = sc if ratio else sc / div
        con = sc.rename(c).to_frame() if con is None else con.join(sc.rename(c), how="outer")
    con = con.reset_index()
    con.insert(0, "Mes", [mes_txt(p) for p in con.pop("PERIODO")])
    hojas["4 Conceptos"] = [(f"{lbl} por concepto", con, {c: fmt_m for c in con.columns[1:]})]

    # Detalle por ramo
    det = []
    for v in DETALLE:
        tv = tabla_mensual(df, concepto, v, ramos, anios, meses)
        tv = tv if v in RATIOS else tv / div
        tv = tv.reset_index()
        tv.insert(0, "Mes", [mes_txt(p) for p in tv.pop("PERIODO")])
        det.append((VARIABLES[v] + (" (%)" if v in RATIOS else f" ({unidad})"), tv,
                    {c: ("pct" if v in RATIOS else "num") for c in tv.columns[1:]}))
    hojas["5 Detalle por ramo"] = det

    # Tabla mensualizada
    tm = tabla_mensual(df, concepto, var, ramos, anios, meses)
    tm = (tm if ratio else tm / div).reset_index()
    tm.insert(0, "Mes", [mes_txt(p) for p in tm.pop("PERIODO")])
    hojas["6 Tabla mensualizada"] = [(f"{lbl} · {concepto}", tm, {c: fmt_m for c in tm.columns[1:]})]

    # Base filtrada (valores originales en pesos)
    base = df[df["RAMO"].isin(ramos) & df["ANIO"].isin(anios) & df["MES"].isin(meses)].drop(columns="FECHA")
    base = base.assign(VARIABLE=base["VARIABLE"].map(VARIABLES))
    hojas["7 Base filtrada"] = [("Base en pesos (sin escalar)", base, {"VALOR": "raw"})]

    def escribir(buf):
        with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
            wb = xw.book
            f_tit = wb.add_format({"bold": True, "font_size": 16, "font_color": T["navy"]})
            f_sub = wb.add_format({"italic": True, "font_color": "#8b90a0", "font_size": 9})
            f_blk = wb.add_format({"bold": True, "font_size": 12, "font_color": T["navy"]})
            f_hdr = wb.add_format({"bold": True, "font_color": "#ffffff", "bg_color": T["navy"], "border": 0,
                                   "align": "center", "valign": "vcenter", "text_wrap": True})
            formatos = {"num": wb.add_format({"num_format": "#,##0.0"}), "pct": wb.add_format({"num_format": "0.0%"}),
                        "idx": wb.add_format({"num_format": "0.00"}), "raw": wb.add_format({"num_format": "#,##0.00"})}
            for nombre, bloques in hojas.items():
                ws = wb.add_worksheet(nombre)
                ws.hide_gridlines(2)
                ws.write(0, 0, f"PRISMA · {nombre[2:]}", f_tit)
                ws.write(1, 0, filtros + f" · Generado {datetime.now():%d/%m/%Y %H:%M}", f_sub)
                fila, ancho = 3, {}
                for titulo, tabla, formatos_col in bloques:
                    ws.write(fila, 0, titulo, f_blk)
                    fila += 1
                    for j, col in enumerate(tabla.columns):
                        ws.write(fila, j, str(col), f_hdr)
                        ancho[j] = max(ancho.get(j, 10), min(len(str(col)) + 2, 28))
                    for i, row in enumerate(tabla.itertuples(index=False), start=fila + 1):
                        for j, (col, val) in enumerate(zip(tabla.columns, row)):
                            if val is None or (isinstance(val, float) and np.isnan(val)):
                                ws.write_blank(i, j, None)
                                continue
                            f = formatos_col.get(col)
                            if f == "auto":   # Resumen: % para Cesión, número para montos
                                f = "pct" if res.loc[i - fila - 1, "Tipo de variación"] == "pp" else "num"
                            if isinstance(val, (int, float, np.integer, np.floating)) and f:
                                ws.write_number(i, j, float(val), formatos[f])
                            else:
                                ws.write(i, j, val.item() if hasattr(val, "item") else val)
                            ancho[j] = max(ancho.get(j, 10), min(len(str(val)) + 2, 28))
                    if fila == 4:
                        ws.freeze_panes(fila + 1, 0)
                    fila += len(tabla) + 3
                for j, w in ancho.items():
                    ws.set_column(j, j, w)

    return escribir


@app.callback(Output("dl", "data"), Input("btn-xls", "n_clicks"), Input("btn-xls2", "n_clicks"),
              Input("rail-xls", "n_clicks"),
              *[State(i.component_id, i.component_property) for i in ENTRADAS[:6]],
              State("est-anios", "value"), State("est-prima", "value"), prevent_initial_call=True)
def descargar(_a, _b, _c, concepto, var, ramos, anios, meses, unidad, est_anios, prima):
    if not (ramos and anios and meses):
        return no_update
    return dcc.send_bytes(libro_excel(concepto, var, ramos, anios, meses, unidad, est_anios, prima),
                          f"PRISMA_Reservas_{datetime.now():%Y%m%d_%H%M}.xlsx")


# --------------------------------------------------------------------------------------
if __name__ == "__main__":
    url = f"http://127.0.0.1:{PUERTO}"
    print(f"\nPRISMA listo en {url}  (Ctrl + C para detener)\n")
    if not os.environ.get("RFV_NO_BROWSER"):
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    app.run(debug=False, port=PUERTO, host="127.0.0.1")
