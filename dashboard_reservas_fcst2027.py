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
    "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"
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


def multi(id_, opciones, valor, nombre, prefijo=""):
    """Selector múltiple con 'Seleccionar todos', igual al de años."""
    return dcc.Dropdown(id=id_, options=[{"label": f"{prefijo}{o}", "value": o} for o in opciones], value=valor,
                        multi=True, clearable=False, searchable=False, placeholder=f"Elige {nombre}",
                        labels={"select_all": "Seleccionar todos", "deselect_all": "Quitar todos",
                                "selected_count": "{num_selected} " + nombre})


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
            panel("Comparativo de conceptos", "", dcc.Graph(id="g-conc", config=GRAPH_CFG), id_titulo="t-conc",
                  id_ayuda="a-conc"),
            extra=html.Div([
                html.Div([html.Label("CONCEPTOS"), multi("conc-conceptos", conceptos0, conceptos0, "conceptos")], className="ctl"),
                html.Div([html.Label("RAMOS"), multi("conc-ramos", ramos0, ramos0, "ramos", prefijo="Ramo ")], className="ctl"),
                html.Div([html.Label("VER RAMOS"),
                          dcc.Dropdown(id="conc-vista", options=[{"label": "Juntos (suma de ramos)", "value": "juntos"},
                                                                 {"label": "Por separado (un panel por ramo)", "value": "separado"}],
                                       value="juntos", clearable=False, searchable=False)], className="ctl"),
            ], className="ctls")),

    seccion("ramos", "05", "Detalle por ramo", "Evolución de cada variable, separada por ramo.",
            html.Div(id="ramo-leyenda", className="leyenda leyenda-sec"),
            html.Div([panel(VARIABLES[v], "", grafica(f"g-v{i}", 250), cls="mini-panel") for i, v in enumerate(DETALLE)],
                     className="grid g-3"),
            extra=html.Div([
                html.Div([html.Label("CONCEPTOS"), multi("det-conceptos", conceptos0, [CONCEPTO0], "conceptos")], className="ctl"),
                html.Div([html.Label("RAMOS"), multi("det-ramos", ramos0, ramos0, "ramos", prefijo="Ramo ")], className="ctl"),
                html.Div([html.Label("VER RAMOS"),
                          dcc.Dropdown(id="det-vista", options=[{"label": "Por separado (una línea por ramo)", "value": "separado"},
                                                                {"label": "Juntos (suma de ramos)", "value": "juntos"}],
                                       value="separado", clearable=False, searchable=False)], className="ctl"),
            ], className="ctls")),

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
.leyenda-sec { margin:-4px 0 12px; justify-content:flex-end; }
.dash-ln { display:inline-block; width:22px; height:0; border-top:2.5px solid var(--tx2); margin-right:7px; }
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
    Output("tabla", "children"),
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
        return (chips, aviso, fuente, pie, [], lbl, "", v, "Por ramo", v, v, html.Div("Sin datos", className="ayuda", style={"padding": "16px"}))

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

    # --- Tabla ---
    tab = tabla_mensual(df, concepto, var, ramos, anios, meses)
    vista = tab * 100 if ratio else tab / div
    f_ = (lambda x: "N/A" if pd.isna(x) else f"{x:,.2f}%") if ratio else (lambda x: "N/A" if pd.isna(x) else f"{x:,.1f}")
    filas = [html.Tr([html.Td(mes_txt(p))] + [html.Td(f_(row[c]), className="tot" if c == "Total" else None)
                                              for c in vista.columns]) for p, row in vista.iterrows()]
    tabla = html.Table([html.Thead(html.Tr([html.Th("Mes")] + [html.Th(c + (" (%)" if ratio else f" ({unidad})"))
                                                               for c in vista.columns])),
                        html.Tbody(filas)], className="t")

    return (chips, aviso, fuente, pie, kpis, f"{lbl} por mes · {concepto}", a_mens, g_mens, t_ramo, g_ramo, g_mom, tabla)


# ---- Conceptos y Detalle por ramo (con sus propios filtros) ----------------------------
DASH_CONCEPTO = {"RCONT": "dot", "RFV BRUTO": "dash", "RFV IRR": "dashdot", "RFV NETO": "solid"}


@app.callback(Output("conc-conceptos", "options"), Output("conc-conceptos", "value"),
              Output("det-conceptos", "options"), Output("det-conceptos", "value"),
              Output("conc-ramos", "options"), Output("conc-ramos", "value"),
              Output("det-ramos", "options"), Output("det-ramos", "value"),
              Input("f-concepto", "value"), Input("f-ramo", "value"), Input("version", "data"), prevent_initial_call=True)
def _sincronizar(concepto, ramos, _ver):
    """Los filtros generales (panel Filtros) ponen el punto de partida; luego cada sección se ajusta sola."""
    conceptos, ramos_todos, _ = catalogos(ESTADO["df"])
    oc = [{"label": c, "value": c} for c in conceptos]
    orr = [{"label": f"Ramo {r}", "value": r} for r in ramos_todos]
    ramos = [r for r in (ramos or []) if r in ramos_todos] or ramos_todos
    t = ctx.triggered_id
    return (oc, conceptos if t == "version" else no_update, oc, [concepto] if concepto else no_update,
            orr, ramos, orr, ramos)


@app.callback(Output("t-conc", "children"), Output("a-conc", "children"), Output("g-conc", "figure"),
              Input("f-var", "value"), Input("f-anio", "value"), Input("f-mes", "value"), Input("f-unidad", "value"),
              Input("conc-conceptos", "value"), Input("conc-ramos", "value"), Input("conc-vista", "value"),
              Input("version", "data"))
def conceptos_cb(var, anios, meses, unidad, conceptos, ramos, vista, _ver):
    df = ESTADO["df"]
    anios, meses, ramos = sorted(anios or []), sorted(meses or []), sorted(ramos or [])
    conceptos = [c for c in CONCEPTOS_ORDEN if c in (conceptos or [])] + [c for c in (conceptos or []) if c not in CONCEPTOS_ORDEN]
    lbl = VARIABLES[var]
    if not (anios and meses and ramos and conceptos):
        return f"{lbl} por concepto", "", vacia("Elige al menos un concepto y un ramo arriba", h=360)
    div, suf = UNIDADES[unidad]
    ratio = var in RATIOS
    yu = f"{unidad} de pesos" if unidad != "Pesos" else "Pesos"
    hov = "%{y:.1%}" if ratio else "%{y:,.1f}" + suf
    if vista == "separado" and len(ramos) > 1:
        sin_monto = [r for r in ramos if all(serie(df, c, var, [r], anios, meses)["VALOR"].fillna(0).abs().sum() == 0
                                              for c in conceptos)]
        ramos = [r for r in ramos if r not in sin_monto] or ramos
        ncol = 3 if len(ramos) > 4 else 2
        nfil = -(-len(ramos) // ncol)
        fig = make_subplots(rows=nfil, cols=ncol, subplot_titles=[f"<b>Ramo {r}</b>" for r in ramos],
                            horizontal_spacing=0.06, vertical_spacing=0.16 if nfil > 1 else 0.1)
        for k, r in enumerate(ramos):
            fi, co = k // ncol + 1, k % ncol + 1
            for c in conceptos:
                s = serie(df, c, var, [r], anios, meses).sort_values("FECHA")
                fig.add_scatter(x=s["FECHA"], y=s["VALOR"] if ratio else s["VALOR"] / div, name=c, legendgroup=c,
                                showlegend=k == 0, mode="lines", line=dict(color=T["conceptos"].get(c, T["text3"]), width=2.4),
                                hovertemplate=hov, row=fi, col=co)
        estilo(fig, 290 * nfil + 40, None, ratio, compacto=True, ytick=".1%" if ratio else ",.2~f")
        fig.update_layout(legend=dict(yanchor="bottom", y=1.02 + 0.02 * nfil, xanchor="left", x=0, font=dict(size=12)),
                          margin=dict(l=8, r=12, t=60, b=8))
        fig.update_annotations(font=dict(size=13, color=T["text"]))
        ayuda = (f"Un panel por ramo; cada línea es un concepto. {lbl} en "
                 + ("%." if ratio else f"{unidad.lower()} de pesos.") + " Cada panel tiene su propia escala."
                 + (f" Sin monto (no se muestra): ramo {', '.join(sin_monto)}." if sin_monto else ""))
        return f"{lbl} por concepto y ramo", ayuda, fig
    fig = go.Figure()
    for c in conceptos:
        s = serie(df, c, var, ramos, anios, meses).sort_values("FECHA")
        y = s["VALOR"] if ratio else s["VALOR"] / div
        col = T["conceptos"].get(c, T["text3"])
        fig.add_scatter(x=s["FECHA"], y=y, name=c, mode="lines", line=dict(color=col, width=2.8), hovertemplate=hov)
        if len(s) and pd.notna(y.iloc[-1]):
            fig.add_annotation(x=s["FECHA"].iloc[-1], y=y.iloc[-1], xanchor="left", xshift=8, showarrow=False,
                               text=f"<b>{c}</b>  {fmt(s['VALOR'].iloc[-1], unidad, ratio)}", font=dict(color=col, size=12))
    estilo(fig, 360, None if ratio else yu, ratio, leyenda=False)
    fig.update_layout(margin=dict(l=8, r=180, t=10, b=8))
    txt_r = "todos los ramos" if len(ramos) == len(catalogos(df)[1]) else "ramos " + ", ".join(ramos)
    return (f"{lbl} por concepto", f"Cada línea es un concepto ({txt_r} sumados); la etiqueta final muestra su último valor.",
            fig)


@app.callback(*[Output(f"g-v{i}", "figure") for i in range(6)], Output("ramo-leyenda", "children"),
              Input("f-anio", "value"), Input("f-mes", "value"), Input("f-unidad", "value"),
              Input("det-conceptos", "value"), Input("det-ramos", "value"), Input("det-vista", "value"),
              Input("version", "data"))
def detalle_cb(anios, meses, unidad, conceptos, ramos, vista, _ver):
    df = ESTADO["df"]
    _, ramos_todos, _ = catalogos(df)
    anios, meses, ramos = sorted(anios or []), sorted(meses or []), sorted(ramos or [])
    conceptos = [c for c in CONCEPTOS_ORDEN if c in (conceptos or [])] + [c for c in (conceptos or []) if c not in CONCEPTOS_ORDEN]
    if not (anios and meses and ramos and conceptos):
        v = vacia("Elige al menos un concepto y un ramo arriba", h=250)
        return (*[v] * 6, None)
    div, suf = UNIDADES[unidad]
    varios = len(conceptos) > 1
    figs = []
    for v in DETALLE:
        r_ = v in RATIOS
        hov = "%{y:.1%}" if r_ else "%{y:,.1f}" + suf
        fig = go.Figure()
        for c in conceptos:
            estilo_linea = DASH_CONCEPTO.get(c, "solid") if varios else "solid"
            if vista == "juntos":
                s = serie(df, c, v, ramos, anios, meses)
                fig.add_scatter(x=s["FECHA"], y=s["VALOR"] if r_ else s["VALOR"] / div, name=c, mode="lines",
                                line=dict(color=T["conceptos"].get(c, T["navy"]) if varios else T["navy"], width=2.4),
                                hovertemplate=hov)
            else:
                for r in ramos:
                    s = serie(df, c, v, [r], anios, meses)
                    if s["VALOR"].fillna(0).abs().sum() == 0:
                        continue
                    fig.add_scatter(x=s["FECHA"], y=s["VALOR"] if r_ else s["VALOR"] / div,
                                    name=f"Ramo {r}" + (f" · {c}" if varios else ""), mode="lines",
                                    line=dict(color=color_ramo(r, ramos_todos), width=2.2, dash=estilo_linea),
                                    hovertemplate=hov)
        estilo(fig, 250, None, r_, leyenda=False, compacto=True)
        figs.append(fig)
    if vista == "juntos":
        leyenda = [html.Span("Suma de ramos " + ", ".join(ramos), style={"color": T["text3"]})] + (
            [html.Span([html.I(className="dot", style={"background": T["conceptos"].get(c, T["navy"])}), c]) for c in conceptos]
            if varios else [html.Span([html.I(className="dot", style={"background": T["navy"]}), conceptos[0]])])
    else:
        leyenda = [html.Span([html.I(className="dot", style={"background": color_ramo(r, ramos_todos)}), f"Ramo {r}"])
                   for r in ramos]
        if varios:
            leyenda += [html.Span([html.I(className="dash-ln", style={"borderTopStyle": {"solid": "solid", "dash": "dashed",
                                                                                         "dot": "dotted", "dashdot": "dashed"}
                                                                                        [DASH_CONCEPTO.get(c, "solid")]}), c])
                        for c in conceptos]
        else:
            leyenda = [html.Span(conceptos[0], style={"color": T["text3"], "fontWeight": 600})] + leyenda
    return (*figs, leyenda)


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


# ---- Descarga a Excel: tablero vivo (fórmulas + panel de control), una pestaña por sección ----
XL = dict(bg="#E9EAEF", navy="#2F3A5F", card="#FFFFFF", tx="#1F2433", tx2="#5B6275", tx3="#8B90A0",
          acc="#F08A3C", acc_s="#F8C9A2", pos="#2E9E6B", pos_s="#E3F4EC", neg="#D64545", neg_s="#FBE7E7",
          nav_s="#ECEEF5", linea="#E3E5EC", grid="#EEF0F4", zebra="#F7F8FA", aa="#9AA3C0")
XL_FUENTE = "Segoe UI"
XL_SECCIONES = [("01 Resumen", "⌂  Resumen"), ("02 Mes a mes", "▮  Mes a mes"), ("03 Estacionalidad", "∿  Estacionalidad"),
                ("04 Conceptos", "≋  Conceptos"), ("05 Detalle por ramo", "▦  Detalle por ramo"),
                ("06 Tabla mensualizada", "☰  Tabla mensualizada")]
XL_C0, XL_C1 = 3, 26          # columnas de contenido: D … AA (24 columnas de 64 px)
XL_COLPX, XL_ROWPX = 64, 20
KPI_VARS = ["RAM", "PRIMA 24M", "PR 24M", "MA", "RFV MA", "CESION", "PT"]


def libro_excel(concepto, var, ramos, anios, meses, unidad, est_anios, prima, anio_ramo=None):
    """Libro de Excel 'vivo': un panel de control (listas desplegables) y fórmulas sobre la base oculta.
    Al cambiar concepto, variable, año, unidades, prima o ramos, todo el libro se recalcula en Excel."""
    import xlsxwriter
    from xlsxwriter.utility import xl_rowcol_to_cell as celda, xl_col_to_name as col_l

    df = ESTADO["df"]
    conceptos, ramos_todos, anios_todos = catalogos(df)
    ramos_xl = ramos_todos[:5]                       # el panel admite hasta 5 ramos
    anio0 = max(anios) if anios else anios_todos[-1]
    ramos_on = set(ramos or ramos_todos)
    base = df.drop(columns="FECHA").copy()
    base["RAMO_N"] = pd.to_numeric(base["RAMO"], errors="coerce")
    base = base[["CONCEPTO", "PERIODO", "ANIO", "MES", "RAMO_N", "VARIABLE", "VALOR"]]
    base["VARIABLE_NOMBRE"] = base["VARIABLE"].map(VARIABLES)
    n_bd = len(base)
    logo_badge = base64.b64decode(LOGO_BADGE_B64)

    def escribir(buf):
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        wb.set_properties({"title": "PRISMA · Proyección de reservas FCST 2027", "author": "PRISMA",
                           "comments": "Tablero vivo: cambia los filtros en '01 Resumen' › Panel de control."})
        cache = {}

        def F(**kw):
            k = tuple(sorted(kw.items()))
            if k not in cache:
                d = {"font_name": XL_FUENTE, "font_size": kw.get("s", 10), "font_color": kw.get("c", XL["tx"]),
                     "valign": kw.get("va", "vcenter")}
                if "bg" in kw: d.update(bg_color=kw["bg"], pattern=1)
                if kw.get("b"): d["bold"] = True
                if kw.get("it"): d["italic"] = True
                if "nf" in kw: d["num_format"] = kw["nf"]
                if "al" in kw: d["align"] = kw["al"]
                if kw.get("wr"): d["text_wrap"] = True
                if kw.get("ind"): d["indent"] = kw["ind"]
                if "bt" in kw: d.update(top=1, top_color=kw["bt"])
                if "bb" in kw: d.update(bottom=1, bottom_color=kw["bb"])
                if "box" in kw: d.update(border=1, border_color=kw["box"])
                cache[k] = wb.add_format(d)
            return cache[k]

        dxf = lambda **kw: wb.add_format(kw)
        PCT, PP = dxf(num_format="0.0%"), dxf(num_format='+0.0" pp";-0.0" pp"')
        ES_RATIO = "=sel_ratio"

        # ======================= hojas visibles (se crean primero para el orden de pestañas) ==========
        hojas = {}

        def hoja(idx, titulo, sub):
            nombre = XL_SECCIONES[idx][0]
            ws = wb.add_worksheet(nombre)
            hojas[idx] = ws
            ws.hide_gridlines(2)
            ws.set_zoom(80)
            ws.set_default_row(15)
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
            nv = F(bg=XL["navy"])
            for r in (1, 2):
                for c in range(XL_C0, XL_C1 + 1):
                    ws.write_blank(r, c, None, nv)
            ws.insert_image(1, XL_C0, "logo.png", {"image_data": io.BytesIO(logo_badge), "x_offset": 10, "y_offset": 6,
                                                  "x_scale": 50 / 160, "y_scale": 50 / 160, "object_position": 3})
            ws.merge_range(1, XL_C0 + 1, 1, XL_C0 + 5, "PRISMA", F(bg=XL["navy"], c="#FFFFFF", b=True, s=18, va="bottom"))
            ws.merge_range(2, XL_C0 + 1, 2, XL_C0 + 5, "Proyección de reservas · FCST 2027",
                           F(bg=XL["navy"], c="#C9CEDD", s=9, va="top"))
            ws.merge_range(1, XL_C0 + 6, 2, XL_C1 - 3, "", F(bg=XL["navy"], c="#FFFFFF", s=9, al="right", wr=True))
            ws.write_formula(1, XL_C0 + 6, "=sel_txt", F(bg=XL["navy"], c="#FFFFFF", s=9, al="right", wr=True))
            ws.merge_range(1, XL_C1 - 2, 2, XL_C1, "", F(bg=XL["acc"], c="#FFFFFF", b=True, s=10, al="center"))
            ws.write_url(1, XL_C1 - 2, "internal:'01 Resumen'!D11",
                         F(bg=XL["acc"], c="#FFFFFF", b=True, s=10, al="center"), string="⚙  Cambiar filtros")
            for r in range(4, 160):
                ws.write_blank(r, 1, None, nv)
            for k, (dest, etiqueta) in enumerate(XL_SECCIONES):
                activo = k == idx
                ws.write_url(8 + k * 2, 1, f"internal:'{dest}'!A1",
                             F(bg=XL["navy"], c=XL["acc"] if activo else "#FFFFFF", b=activo, s=10, ind=1), string=etiqueta)
            r_n = 8 + len(XL_SECCIONES) * 2 + 1
            ws.write_url(r_n, 1, "internal:'01 Resumen'!D11", F(bg=XL["navy"], c="#F8C9A2", b=True, s=10, ind=1),
                         string="⚙  Panel de control")
            ws.write(r_n + 2, 1, "Base y cálculos en", F(bg=XL["navy"], c="#AEB5CB", s=8, ind=1))
            ws.write(r_n + 3, 1, "pestañas ocultas", F(bg=XL["navy"], c="#AEB5CB", s=8, ind=1))
            ws.write(4, XL_C0, f"{idx + 1:02d}", F(bg=XL["navy"], c="#FFFFFF", b=True, s=11, al="center"))
            ws.merge_range(4, XL_C0 + 1, 4, XL_C0 + 12, titulo, F(bg=XL["bg"], b=True, s=15, ind=1))
            ws.merge_range(5, XL_C0 + 1, 5, XL_C1, sub, F(bg=XL["bg"], c=XL["tx3"], s=10, ind=1))
            ws.freeze_panes(4, 0)
            return ws

        def tarjeta(ws, r1, c1, r2, c2, titulo=None, ayuda=None, oscuro=False, f_titulo=None):
            bgc = XL["navy"] if oscuro else XL["card"]
            for r in range(r1, r2 + 1):
                for c in range(c1, c2 + 1):
                    ws.write_blank(r, c, None, F(bg=bgc))
            ft = F(bg=bgc, b=True, s=11, c="#FFFFFF" if oscuro else XL["tx"], ind=1, va="bottom")
            if f_titulo:
                ws.merge_range(r1, c1, r1, c2, "", ft)
                ws.write_formula(r1, c1, f_titulo, ft)
            elif titulo:
                ws.merge_range(r1, c1, r1, c2, titulo, ft)
            if ayuda:
                ws.merge_range(r1 + 1, c1, r1 + 1, c2, ayuda, F(bg=bgc, s=9, c="#C9CEDD" if oscuro else XL["tx3"], ind=1, va="top"))

        def colocar(ws, ch, r1, c1, r2, c2, top=2):
            ch.set_size({"width": (c2 - c1 + 1) * XL_COLPX - 16, "height": (r2 - (r1 + top) + 1) * XL_ROWPX - 8})
            ws.insert_chart(r1 + top, c1, ch, {"x_offset": 8, "y_offset": 2, "object_position": 3})

        def estilo_ch(ch, leyenda=False, y_fmt="#,##0", y_min=None, y_max=None, oscuro=False, barra=False,
                      x_visible=True, y_visible=True):
            ch.set_title({"none": True})
            ch.set_chartarea({"border": {"none": True}, "fill": {"color": XL["navy"] if oscuro else XL["card"]}})
            ch.set_plotarea({"border": {"none": True}, "fill": {"none": True}})
            ch.set_legend({"position": "top", "font": {"name": XL_FUENTE, "size": 9, "color": XL["tx2"]}} if leyenda
                          else {"none": True})
            cat = {"num_font": {"name": XL_FUENTE, "size": 9, "color": XL["tx3"]}, "line": {"color": XL["linea"]},
                   "major_tick_mark": "none", "visible": x_visible, "label_position": "low"}
            val = {"num_font": {"name": XL_FUENTE, "size": 9, "color": XL["tx3"]}, "num_format": y_fmt,
                   "line": {"none": True}, "major_tick_mark": "none", "visible": y_visible,
                   "major_gridlines": {"visible": y_visible, "line": {"color": XL["grid"]}}}
            if y_min is not None: val["min"] = y_min
            if y_max is not None: val["max"] = y_max
            if barra:
                cat.update({"line": {"none": True}, "reverse": True, "num_font": {"name": XL_FUENTE, "size": 10, "color": XL["tx"]}})
                ch.set_x_axis(val)
                ch.set_y_axis(cat)
            else:
                ch.set_x_axis(cat)
                ch.set_y_axis(val)

        def etq(nfmt, color=None, pos="outside_end"):
            return {"value": True, "num_format": nfmt, "position": pos,
                    "font": {"name": XL_FUENTE, "size": 8, "color": color or XL["tx2"]}}

        def encabezado(ws, r, c, texto, w=1, al="right", formula=False):
            f = F(bg=XL["navy"], c="#FFFFFF", b=True, s=9, al=al, ind=1, wr=True)
            if w > 1:
                ws.merge_range(r, c, r, c + w - 1, "", f)
            (ws.write_formula if formula else ws.write)(r, c, texto, f)

        def celda_tabla(ws, r, c, valor, w=1, nf="#,##0.0", zebra=False, b=False, color=None, al="right", formula=True):
            f = F(bg=XL["zebra"] if zebra else XL["card"], s=10, al=al, ind=1, b=b, c=color or XL["tx"], nf=nf, bb=XL["linea"])
            if w > 1:
                ws.merge_range(r, c, r, c + w - 1, "", f)
            if formula and isinstance(valor, str) and valor.startswith("="):
                ws.write_formula(r, c, valor, f)
            else:
                ws.write(r, c, valor, f)

        def fmt_ratio(ws, rng):        # muestra % cuando la variable elegida es Cesión
            ws.conditional_format(*rng, {"type": "formula", "criteria": ES_RATIO, "format": PCT})

        for i, (t, s_) in enumerate([("Resumen", "Cifras clave al cierre del año elegido y su cambio contra el año anterior (AA)."),
                                     ("Mes a mes", "Cómo se reparte el monto en cada mes del año elegido, contra el año anterior y por ramo."),
                                     ("Estacionalidad", "¿En qué meses el monto está por arriba o por abajo de lo normal, y se parece a la prima?"),
                                     ("Conceptos", "Los cuatro cálculos de la reserva lado a lado: RCONT, RFV bruto, RFV IRR y RFV neto."),
                                     ("Detalle por ramo", "Evolución mensual de cada variable, separada por ramo (concepto y año del panel)."),
                                     ("Tabla mensualizada", "Mensualización por ramo con resumen anual. Lista para copiar a otros reportes.")]):
            hoja(i, t, s_)
        wc = wb.add_worksheet("Calculos")
        wl = wb.add_worksheet("Listas")
        wbd = wb.add_worksheet("BD_Proyeccion")

        # ======================= Listas (catálogos de las listas desplegables) =======================
        listas = {"lst_conc": ("Conceptos", conceptos), "lst_var_lbl": ("Variable", list(VARIABLES.values())),
                  "lst_var_clave": ("Clave", list(VARIABLES.keys())), "lst_uni_lbl": ("Unidades", list(UNIDADES)),
                  "lst_uni_div": ("Divisor", [v[0] for v in UNIDADES.values()]), "lst_pri_lbl": ("Prima", list(PRIMAS.values())),
                  "lst_pri_clave": ("Clave prima", list(PRIMAS.keys())), "lst_anios": ("Años", anios_todos),
                  "lst_sino": ("Incluir", ["Sí", "No"]), "lst_meses": ("Meses", MESES)}
        for j, (nombre, (titulo, valores)) in enumerate(listas.items()):
            wl.write(0, j, titulo, F(b=True, c="#FFFFFF", bg=XL["navy"]))
            for i, v in enumerate(valores, start=1):
                wl.write(i, j, v)
            wb.define_name(nombre, f"=Listas!${col_l(j)}$2:${col_l(j)}${len(valores) + 1}")
        wl.set_column(0, len(listas), 18)
        wl.hide()

        # ======================= Base de datos (oculta) =======================
        cols_bd = ["CONCEPTO", "PERIODO", "AÑO", "MES", "RAMO", "CLAVE", "VALOR (pesos)", "VARIABLE"]
        datos_bd = [[None if (isinstance(x, float) and np.isnan(x)) else (x.item() if hasattr(x, "item") else x)
                     for x in fila] for fila in base.itertuples(index=False)]
        wbd.add_table(0, 0, n_bd, len(cols_bd) - 1,
                      {"data": datos_bd, "name": "BD_Proyeccion", "style": "Table Style Medium 2",
                       "columns": [({"header": c, "format": F(nf="#,##0.00")} if c.startswith("VALOR") else {"header": c})
                                   for c in cols_bd]})
        wbd.set_column(0, 7, 15)
        wbd.freeze_panes(1, 0)
        for nombre, letra in [("bd_conc", "A"), ("bd_per", "B"), ("bd_ramo", "E"), ("bd_clave", "F"), ("bd_val", "G")]:
            wb.define_name(nombre, f"=BD_Proyeccion!${letra}$2:${letra}${n_bd + 1}")
        wbd.hide()

        # ======================= 01 RESUMEN: panel de control =======================
        ws = hojas[0]
        PANEL_R = 10                                   # renglón (0-based) de las celdas editables
        tarjeta(ws, 7, XL_C0, 11, XL_C1, "⚙  Panel de control",
                "Elige de las listas y todo el libro se recalcula: cifras, tablas y gráficas de todas las pestañas.")
        campos = [("CONCEPTO", 0, 3, "sel_conc", "lst_conc", concepto),
                  ("VARIABLE", 3, 3, "sel_var", "lst_var_lbl", VARIABLES[var]),
                  ("AÑO", 6, 2, "sel_anio", "lst_anios", anio0),
                  ("UNIDADES", 8, 2, "sel_uni", "lst_uni_lbl", unidad),
                  ("PRIMA A COMPARAR", 10, 3, "sel_pri", "lst_pri_lbl", PRIMAS[prima])]
        f_in = F(bg=XL["nav_s"], b=True, s=11, c=XL["navy"], al="center", box="#9BA5CF")
        for lbl_, off, w, nombre, lista, valor in campos:
            c = XL_C0 + off
            ws.merge_range(PANEL_R - 1, c, PANEL_R - 1, c + w - 1, lbl_, F(bg=XL["card"], c=XL["tx3"], b=True, s=8, ind=1, va="bottom"))
            ws.merge_range(PANEL_R, c, PANEL_R, c + w - 1, valor, f_in)
            ws.data_validation(PANEL_R, c, PANEL_R, c, {"validate": "list", "source": f"={lista}",
                                                       "input_title": lbl_.title(), "input_message": "Elige de la lista ▾"})
            wb.define_name(nombre, f"='01 Resumen'!${col_l(c)}${PANEL_R + 1}")
        ws.set_row_pixels(PANEL_R, 28)
        celdas_ramo = []
        for k, r in enumerate(ramos_xl):
            c = XL_C0 + 13 + k * 2
            ws.merge_range(PANEL_R - 1, c, PANEL_R - 1, c + 1, f"RAMO {r}", F(bg=XL["card"], c=XL["tx3"], b=True, s=8, al="center", va="bottom"))
            ws.merge_range(PANEL_R, c, PANEL_R, c + 1, "Sí" if r in ramos_on else "No", f_in)
            ws.data_validation(PANEL_R, c, PANEL_R, c, {"validate": "list", "source": "=lst_sino",
                                                       "input_title": f"Ramo {r}", "input_message": "Sí = incluir · No = excluir"})
            ws.conditional_format(PANEL_R, c, PANEL_R, c + 1, {"type": "cell", "criteria": "==", "value": '"No"',
                                                              "format": dxf(font_color=XL["tx3"], bg_color="#F4F5F8")})
            celdas_ramo.append(f"'01 Resumen'!${col_l(c)}${PANEL_R + 1}")

        # ======================= CALCULOS (oculta): parámetros y bloque mensual =======================
        wc.set_column(0, 0, 26)
        wc.set_column(1, 120, 13)
        params = [("Clave de la variable", "=INDEX(lst_var_clave,MATCH(sel_var,lst_var_lbl,0))", "sel_clave"),
                  ("¿Es porcentaje?", '=sel_clave="CESION"', "sel_ratio"),
                  ("Divisor de unidades", "=INDEX(lst_uni_div,MATCH(sel_uni,lst_uni_lbl,0))", "sel_div"),
                  ("Clave de la prima", "=INDEX(lst_pri_clave,MATCH(sel_pri,lst_pri_lbl,0))", "sel_prima"),
                  ("Año anterior", "=sel_anio-1", "sel_ant")]
        for i, (t, f, n) in enumerate(params):
            wc.write(i, 0, t)
            wc.write_formula(i, 1, f)
            wb.define_name(n, f"=Calculos!$B${i + 1}")
        # ramos
        wc.write(0, 3, "Ramo", F(b=True)); wc.write(0, 4, "Incluir", F(b=True))
        for k, r in enumerate(ramos_xl):
            wc.write_number(k + 1, 3, int(r))
            wc.write_formula(k + 1, 4, f'=IF({celdas_ramo[k]}="Sí",1,0)')
        n_r = len(ramos_xl)
        wb.define_name("f_ramos", f"=Calculos!$D$2:$D${n_r + 1}")
        wb.define_name("f_incl", f"=Calculos!$E$2:$E${n_r + 1}")
        txt_ramos = "&".join(f'IF(Calculos!$E${k + 2}=1,"{r} ","")' for k, r in enumerate(ramos_xl))
        wc.write(6, 0, "Texto de filtros")
        wc.write_formula(6, 1, '="Concepto "&sel_conc&"   ·   Variable "&sel_var&"   ·   Año "&sel_anio&" (AA "&sel_ant&")'
                               f'   ·   Ramos "&TRIM({txt_ramos})&"   ·   En "&IF(sel_ratio,"%",sel_uni)')
        wb.define_name("sel_txt", "=Calculos!$B$7")

        # --- generadores de fórmulas ---
        def S(c, k, p):
            return f"SUMPRODUCT(SUMIFS(bd_val,bd_conc,{c},bd_clave,{k},bd_per,{p},bd_ramo,f_ramos)*f_incl)"

        def W(c, p):
            return (f'IFERROR(SUMPRODUCT(SUMIFS(bd_val,bd_conc,{c},bd_clave,"CESION",bd_per,{p},bd_ramo,f_ramos)'
                    f'*SUMIFS(bd_val,bd_conc,{c},bd_clave,"RAM",bd_per,{p},bd_ramo,f_ramos)*f_incl)/{S(c, chr(34) + "RAM" + chr(34), p)},NA())')

        def Gsel(c, p):
            return f"IF(sel_ratio,{W(c, p)},{S(c, 'sel_clave', p)}/sel_div)"

        def Gfix(c, k, p):
            return W(c, p) if k == "CESION" else f'{S(c, chr(34) + k + chr(34), p)}/sel_div'

        def R1(c, k, p, r):
            return f"SUMIFS(bd_val,bd_conc,{c},bd_clave,{k},bd_per,{p},bd_ramo,{r})"

        H, R0 = 10, 11                                 # encabezado y primer renglón del bloque mensual
        RN = R0 + 11
        cols = {}

        def nueva(nombre, encabezado_txt=None):
            j = len(cols)
            cols[nombre] = j
            t = encabezado_txt if encabezado_txt is not None else nombre
            (wc.write_formula if str(t).startswith("=") else wc.write)(H, j, t, F(b=True, c="#FFFFFF", bg=XL["navy"]))
            return j

        def rng(nombre, hoja_="Calculos"):
            j = cols[nombre]
            return [hoja_, R0, j, RN, j]

        def ref(nombre, i=None, abs_=True):
            j = cols[nombre]
            if i is None:
                return f"Calculos!${col_l(j)}${R0 + 1}:${col_l(j)}${RN + 1}"
            return f"Calculos!${col_l(j)}${R0 + 1 + i}" if abs_ else f"Calculos!{col_l(j)}{R0 + 1 + i}"

        conc_q = {c: f'"{c}"' for c in conceptos}
        for nombre in ["Mes", "PerY", "PerA"]:
            nueva(nombre)
        nueva("SelY", '=sel_anio&""'); nueva("SelA", '="AA "&sel_ant'); nueva("Prom", "Promedio")
        nueva("Cambio"); nueva("Sube"); nueva("Baja"); nueva("VsAA")
        nueva("LblY", "Etiqueta año"); nueva("LblSube", "Etiqueta sube"); nueva("LblBaja", "Etiqueta baja")
        for c in conceptos:
            nueva(f"C_{c}", c); nueva(f"CA_{c}", f"{c} AA")
        for r in ramos_xl:
            nueva(f"R_{r}", f"Ramo {r}")
        for k in KPI_VARS:
            nueva(f"K_{k}"); nueva(f"KA_{k}")
        for a in anios_todos:
            nueva(f"V_{a}", f"Var {a}"); nueva(f"P_{a}", f"Prima {a}")
        for a in anios_todos:
            nueva(f"IV_{a}", f"Índice var {a}"); nueva(f"IP_{a}", f"Índice prima {a}")
        nueva("Base1", "1.00")
        for r in ramos_xl:
            nueva(f"IR_{r}", f"Índice ramo {r}")
        for v in DETALLE:
            for r in ramos_xl:
                nueva(f"D_{v}_{r}", f"{VARIABLES[v]} · {r}")
            nueva(f"DT_{v}", f"{VARIABLES[v]} · Total")

        for i in range(12):
            rr = R0 + i
            pY, pA = f"$B{rr + 1}", f"$C{rr + 1}"
            fila = {
                "Mes": MESES[i], "PerY": f"=sel_anio*100+{i + 1}", "PerA": f"=sel_ant*100+{i + 1}",
                "SelY": "=" + Gsel("sel_conc", pY), "SelA": "=" + Gsel("sel_conc", pA),
                "Prom": f"=AVERAGE({ref('SelY')})",
                "Cambio": "=NA()" if i == 0 else f"={col_l(cols['SelY'])}{rr + 1}-{col_l(cols['SelY'])}{rr}",
                "Sube": f"=IF(ISNUMBER({col_l(cols['Cambio'])}{rr + 1}),IF({col_l(cols['Cambio'])}{rr + 1}>=0,{col_l(cols['Cambio'])}{rr + 1},NA()),NA())",
                "Baja": f"=IF(ISNUMBER({col_l(cols['Cambio'])}{rr + 1}),IF({col_l(cols['Cambio'])}{rr + 1}<0,{col_l(cols['Cambio'])}{rr + 1},NA()),NA())",
                "VsAA": f"=IFERROR(IF(sel_ratio,{col_l(cols['SelY'])}{rr + 1}-{col_l(cols['SelA'])}{rr + 1},"
                        f"{col_l(cols['SelY'])}{rr + 1}/{col_l(cols['SelA'])}{rr + 1}-1),NA())",
                "Base1": 1.0,
                "LblY": f'=IFERROR(TEXT({col_l(cols["SelY"])}{rr + 1},IF(sel_ratio,"0.0%","#,##0.0")),"")',
                "LblSube": f'=IF(ISNUMBER({col_l(cols["Sube"])}{rr + 1}),TEXT({col_l(cols["Sube"])}{rr + 1},IF(sel_ratio,"+0.00%","+#,##0.0")),"")',
                "LblBaja": f'=IF(ISNUMBER({col_l(cols["Baja"])}{rr + 1}),TEXT({col_l(cols["Baja"])}{rr + 1},IF(sel_ratio,"-0.00%;-0.00%","-#,##0.0;-#,##0.0")),"")',
            }
            for c in conceptos:
                fila[f"C_{c}"] = "=" + Gsel(conc_q[c], pY)
                fila[f"CA_{c}"] = "=" + Gsel(conc_q[c], pA)
            for k_, r in enumerate(ramos_xl):
                rr_ = R1("sel_conc", "sel_clave", pY, int(r))
                fila[f"R_{r}"] = f"=IF(Calculos!$E${k_ + 2}=1,IF(sel_ratio,{rr_},{rr_}/sel_div),NA())"
            for k in KPI_VARS:
                fila[f"K_{k}"] = "=" + Gfix("sel_conc", k, pY)
                fila[f"KA_{k}"] = "=" + Gfix("sel_conc", k, pA)
            for a in anios_todos:
                pa = f"{a * 100 + i + 1}"
                fila[f"V_{a}"] = "=" + Gsel("sel_conc", pa)
                fila[f"P_{a}"] = f"={S('sel_conc', 'sel_prima', pa)}/sel_div"
                fila[f"IV_{a}"] = f"=IFERROR({col_l(cols[f'V_{a}'])}{rr + 1}/AVERAGE({ref(f'V_{a}')}),NA())"
                fila[f"IP_{a}"] = f"=IFERROR({col_l(cols[f'P_{a}'])}{rr + 1}/AVERAGE({ref(f'P_{a}')}),NA())"
            for r in ramos_xl:
                fila[f"IR_{r}"] = f"=IFERROR({col_l(cols[f'R_{r}'])}{rr + 1}/AVERAGE({ref(f'R_{r}')}),NA())"
            for v in DETALLE:
                for k_, r in enumerate(ramos_xl):
                    rr_ = R1("sel_conc", f'"{v}"', pY, int(r))
                    fila[f"D_{v}_{r}"] = f"=IF(Calculos!$E${k_ + 2}=1,{rr_ if v in RATIOS else rr_ + '/sel_div'},NA())"
                fila[f"DT_{v}"] = "=" + Gfix("sel_conc", v, pY)
            for nombre, j in cols.items():
                val = fila[nombre]
                if isinstance(val, str) and val.startswith("="):
                    wc.write_formula(rr, j, val)
                else:
                    wc.write(rr, j, val)

        # --- bloques auxiliares (debajo del mensual) ---
        def ultimo(rango_):          # último valor numérico de un rango (cierre)
            return f"IFERROR(LOOKUP(2,1/ISNUMBER({rango_}),{rango_}),NA())"

        B_KPI = RN + 3
        for j, t in enumerate(["Indicador", "Actual", "AA", "Variación", "Referencia"]):
            wc.write(B_KPI, j, t, F(b=True, c="#FFFFFF", bg=XL["navy"]))
        kpi_cel = {}
        for i, k in enumerate(KPI_VARS):
            r = B_KPI + 1 + i
            act = f"SUM({ref(f'K_{k}')})" if k in FLUJOS else ultimo(ref(f"K_{k}"))
            ant = f"SUM({ref(f'KA_{k}')})" if k in FLUJOS else ultimo(ref(f"KA_{k}"))
            wc.write(r, 0, VARIABLES[k])
            wc.write_formula(r, 1, "=" + act)
            wc.write_formula(r, 2, "=" + ant)
            wc.write_formula(r, 3, f"=IFERROR({'B{0}-C{0}'.format(r + 1) if k in RATIOS else 'B{0}/C{0}-1'.format(r + 1)},NA())")
            if k in FLUJOS:
                wc.write_formula(r, 4, '="Acumulado "&sel_anio')
            else:
                rg = ref(f"K_{k}")
                wc.write_formula(r, 4, f'=IFERROR("Saldo al cierre de "&INDEX(lst_meses,LOOKUP(2,1/ISNUMBER({rg}),ROW({rg})-ROW(INDEX({rg},1))+1))&" "&sel_anio,"Sin dato")')
            kpi_cel[k] = {n_: f"Calculos!${col_l(j)}${r + 1}" for n_, j in [("act", 1), ("ant", 2), ("var", 3), ("ref", 4)]}

        B_RAMO = B_KPI + len(KPI_VARS) + 3
        for j, t in enumerate(["Ramo", "Cierre", "% del total", "Etiqueta"]):
            wc.write(B_RAMO, j, t, F(b=True, c="#FFFFFF", bg=XL["navy"]))
        for i, r in enumerate(ramos_xl):
            rr = B_RAMO + 1 + i
            wc.write(rr, 0, f"Ramo {r}")
            rg = ref(f"R_{r}")
            wc.write_formula(rr, 1, f'=IF(Calculos!$E${i + 2}=0,NA(),IF(sel_clave="PT",SUM({rg}),{ultimo(rg)}))')
            wc.write_formula(rr, 2, f"=IF(sel_ratio,NA(),IFERROR(B{rr + 1}/SUMIF($B${B_RAMO + 2}:$B${B_RAMO + 1 + n_r},\">=0\"),NA()))")
            wc.write_formula(rr, 3, f'=IFERROR(IF(sel_ratio,TEXT(B{rr + 1},"0.0%"),TEXT(B{rr + 1},"#,##0.0")&"  ·  "&TEXT(C{rr + 1},"0.0%")),"")')
        ramo_rng = lambda j: ["Calculos", B_RAMO + 1, j, B_RAMO + n_r, j]

        B_LECT = B_RAMO + n_r + 3
        for j, t in enumerate(["Año", "Correlación", "Pico variable", "Pico prima", "Amplitud variable", "Amplitud prima"]):
            wc.write(B_LECT, j, t, F(b=True, c="#FFFFFF", bg=XL["navy"]))
        for i, a in enumerate(anios_todos):
            rr = B_LECT + 1 + i
            iv_, ip_ = ref(f"IV_{a}"), ref(f"IP_{a}")
            wc.write_number(rr, 0, a)
            wc.write_formula(rr, 1, f"=IFERROR(CORREL({iv_},{ip_}),NA())")
            wc.write_formula(rr, 2, f'=IFERROR(INDEX(lst_meses,MATCH(MAX({iv_}),{iv_},0)),"—")')
            wc.write_formula(rr, 3, f'=IFERROR(INDEX(lst_meses,MATCH(MAX({ip_}),{ip_},0)),"—")')
            wc.write_formula(rr, 4, f"=IFERROR(MAX({iv_})-MIN({iv_}),NA())")
            wc.write_formula(rr, 5, f"=IFERROR(MAX({ip_})-MIN({ip_}),NA())")
        wc.hide()

        # ======================= 01 RESUMEN: tarjetas de indicadores =======================
        iconos = {"RAM": "🛡", "PRIMA 24M": "◷", "PR 24M": "◔", "MA": "▣", "RFV MA": "↗", "CESION": "⇄", "PT": "$"}
        fmt_uni = {"Millones": '"$"#,##0.0" M"', "Miles": '"$"#,##0.0" K"', "Pesos": '"$"#,##0'}

        def valor_kpi(ws, r1, c1, r2, c2, k, s, color, bg):
            f = F(bg=bg, c=color, b=True, s=s, ind=1, nf=fmt_uni["Millones"])
            ws.merge_range(r1, c1, r2, c2, "", f)
            ws.write_formula(r1, c1, f"={kpi_cel[k]['act']}", f)
            if k in RATIOS:
                ws.conditional_format(r1, c1, r2, c2, {"type": "no_errors", "format": PCT})
            else:
                for u, nfm in fmt_uni.items():
                    ws.conditional_format(r1, c1, r2, c2, {"type": "formula", "criteria": f'=sel_uni="{u}"',
                                                          "format": dxf(num_format=nfm)})

        def aa_kpi(ws, r, c1, c2, k, color, bg):
            f = F(bg=bg, c=color, s=9, ind=1)
            ws.merge_range(r, c1, r, c2, "", f)
            if k in RATIOS:
                ws.write_formula(r, c1, f'=IFERROR("AA: "&TEXT({kpi_cel[k]["ant"]},"0.0%"),"AA: N/A")', f)
            else:
                ws.write_formula(r, c1, f'=IFERROR("AA: $"&TEXT({kpi_cel[k]["ant"]},"#,##0.0")&IF(sel_uni="Millones"," M",IF(sel_uni="Miles"," K","")),"AA: N/A")', f)

        def badge_kpi(ws, r, c1, c2, k):
            nfm = '"▲ "0.0" pp";"▼ "0.0" pp"' if k in RATIOS else '"▲ "0.0%;"▼ "0.0%'
            f = F(bg=XL["pos_s"], c=XL["pos"], b=True, s=9, al="center", nf=nfm)
            ws.merge_range(r, c1, r, c2, "", f)
            ws.write_formula(r, c1, f"=IFERROR({kpi_cel[k]['var']}{'*100' if k in RATIOS else ''},\"sin comparativo\")", f)
            ws.conditional_format(r, c1, r, c2, {"type": "cell", "criteria": "<", "value": 0,
                                                 "format": dxf(font_color=XL["neg"], bg_color=XL["neg_s"])})

        R_K = 13
        tarjeta(ws, R_K, XL_C0, R_K + 14, XL_C0 + 5, oscuro=True)
        ws.merge_range(R_K, XL_C0, R_K, XL_C0 + 5, f"{iconos['RAM']}  Reserva", F(bg=XL["navy"], c="#C9CEDD", s=11, ind=1))
        ws.set_row_pixels(R_K + 1, 30); ws.set_row_pixels(R_K + 2, 26)
        valor_kpi(ws, R_K + 1, XL_C0, R_K + 2, XL_C0 + 5, "RAM", 28, "#FFFFFF", XL["navy"])
        aa_kpi(ws, R_K + 3, XL_C0, XL_C0 + 2, "RAM", "#C9CEDD", XL["navy"])
        badge_kpi(ws, R_K + 3, XL_C0 + 3, XL_C0 + 4, "RAM")
        ws.merge_range(R_K + 5, XL_C0, R_K + 5, XL_C0 + 5, "Tendencia del año elegido", F(bg=XL["navy"], c="#AEB5CB", s=9, ind=1))
        f_ref = F(bg=XL["navy"], c="#AEB5CB", s=9, ind=1, bt="#56607F")
        ws.merge_range(R_K + 14, XL_C0, R_K + 14, XL_C0 + 5, "", f_ref)
        ws.write_formula(R_K + 14, XL_C0, f"={kpi_cel['RAM']['ref']}", f_ref)
        ch = wb.add_chart({"type": "area"})
        ch.add_series({"categories": rng("Mes"), "values": rng("K_RAM"), "name": "Reserva",
                       "fill": {"color": "#FFFFFF", "transparency": 88}, "line": {"color": XL["acc"], "width": 2.25}})
        estilo_ch(ch, oscuro=True, x_visible=False, y_visible=False)
        colocar(ws, ch, R_K + 6, XL_C0, R_K + 13, XL_C0 + 5, top=0)
        posiciones = [(R_K, XL_C0 + 6), (R_K, XL_C0 + 12), (R_K, XL_C0 + 18),
                      (R_K + 7, XL_C0 + 6), (R_K + 7, XL_C0 + 12), (R_K + 7, XL_C0 + 18)]
        for k, (r, c) in zip(KPI_VARS[1:], posiciones):
            r2 = R_K + 14 if r > R_K else r + 5
            tarjeta(ws, r, c, r2, c + 5)
            ws.merge_range(r, c, r, c + 5, f"{iconos[k]}  {VARIABLES[k]}", F(bg=XL["card"], c=XL["tx2"], s=10, ind=1))
            valor_kpi(ws, r + 1, c, r + 2, c + 5, k, 18, XL["tx"], XL["card"])
            aa_kpi(ws, r + 3, c, c + 2, k, XL["tx3"], XL["card"])
            badge_kpi(ws, r + 3, c + 3, c + 4, k)
            f_r = F(bg=XL["card"], c=XL["tx3"], s=9, ind=1, bt=XL["linea"])
            ws.merge_range(r2, c, r2, c + 5, "", f_r)
            ws.write_formula(r2, c, f"={kpi_cel[k]['ref']}", f_r)

        R_G = R_K + 16
        tarjeta(ws, R_G, XL_C0, R_G + 9, XL_C0 + 11, "Cómo usar este libro", "Funciona solo en Excel, sin el tablero web.")
        pasos = ["1. Cambia Concepto, Variable, Año, Unidades o Prima en el Panel de control (arriba).",
                 "2. Escribe Sí / No en cada ramo para incluirlo o excluirlo de los totales.",
                 "3. Recorre las secciones con el menú azul de la izquierda.",
                 "4. AA = mismo mes del año anterior. Verde: subió · Rojo: bajó.",
                 "5. Las tablas son fórmulas: puedes copiarlas o enlazarlas a otros archivos.",
                 "6. Para volver al panel usa '⚙ Cambiar filtros' (arriba a la derecha)."]
        for i, p_ in enumerate(pasos):
            ws.merge_range(R_G + 2 + i, XL_C0, R_G + 2 + i, XL_C0 + 11, p_, F(bg=XL["card"], c=XL["tx2"], s=10, ind=1))
        tarjeta(ws, R_G, XL_C0 + 12, R_G + 9, XL_C1, "Qué hay detrás", "Pestañas ocultas: clic derecho en una pestaña › Mostrar.")
        notas = [("BD_Proyeccion", f"Base completa en pesos ({n_bd:,} renglones), como tabla filtrable."),
                 ("Calculos", "Fórmulas SUMIFS que alimentan cada cifra y gráfica."),
                 ("Listas", "Catálogos de las listas desplegables."),
                 ("Cesión", "Promedio ponderado por la reserva de los ramos incluidos."),
                 ("Índice", "Mes ÷ promedio de su año (1.00 = mes promedio).")]
        for i, (k_, v_) in enumerate(notas):
            ws.merge_range(R_G + 2 + i, XL_C0 + 12, R_G + 2 + i, XL_C0 + 15, k_, F(bg=XL["card"], b=True, s=10, ind=1))
            ws.merge_range(R_G + 2 + i, XL_C0 + 16, R_G + 2 + i, XL_C1, v_, F(bg=XL["card"], c=XL["tx2"], s=10))
        ws.activate()
        ws.set_first_sheet()

        # ======================= 02 MES A MES =======================
        ws = hojas[1]
        tarjeta(ws, 7, XL_C0, 27, XL_C0 + 16, f_titulo='=sel_var&" por mes · "&sel_conc&" · "&sel_anio',
                ayuda="Barras: año elegido. Línea gris: año anterior (AA). Línea naranja punteada: promedio del año.")
        ch = wb.add_chart({"type": "column"})
        ch.add_series({"name": ["Calculos", H, cols["SelY"]], "categories": rng("Mes"), "values": rng("SelY"),
                       "fill": {"color": XL["navy"]}, "border": {"none": True}, "gap": 55,
                       "data_labels": {"custom": [{"value": "=" + ref("LblY", i)} for i in range(12)], "position": "outside_end",
                                       "font": {"name": XL_FUENTE, "size": 8, "color": XL["tx2"]}}})
        ln = wb.add_chart({"type": "line"})
        ln.add_series({"name": ["Calculos", H, cols["SelA"]], "categories": rng("Mes"), "values": rng("SelA"),
                       "line": {"color": XL["aa"], "width": 2}, "marker": {"type": "circle", "size": 5,
                                                                         "fill": {"color": XL["aa"]}, "border": {"color": XL["aa"]}}})
        ln.add_series({"name": "Promedio", "categories": rng("Mes"), "values": rng("Prom"),
                       "line": {"color": XL["acc"], "width": 1.75, "dash_type": "dash"}, "marker": {"type": "none"}})
        ch.combine(ln)
        estilo_ch(ch, leyenda=True, y_fmt="#,##0.0##")
        colocar(ws, ch, 7, XL_C0, 27, XL_C0 + 16)

        tarjeta(ws, 7, XL_C0 + 17, 27, XL_C1, "Por ramo · cierre del año", "Monto de cada ramo incluido y su % del total.")
        ch = wb.add_chart({"type": "bar"})
        ch.add_series({"name": "Por ramo", "categories": ramo_rng(0), "values": ramo_rng(1),
                       "fill": {"color": XL["navy"]}, "border": {"none": True}, "gap": 70,
                       "data_labels": {"custom": [{"value": f"=Calculos!$D${B_RAMO + 2 + i}"} for i in range(n_r)],
                                       "position": "outside_end", "font": {"name": XL_FUENTE, "size": 9, "color": XL["tx"]}}})
        estilo_ch(ch, barra=True, y_fmt="#,##0", y_min=0, y_visible=False)
        colocar(ws, ch, 7, XL_C0 + 17, 27, XL_C1)

        tarjeta(ws, 29, XL_C0, 42, XL_C1, "Cambio contra el mes anterior", "Verde: el monto subió. Rojo: bajó.")
        ch = wb.add_chart({"type": "column"})
        for nm, col in (("Sube", XL["pos"]), ("Baja", XL["neg"])):
            ch.add_series({"name": nm, "categories": rng("Mes"), "values": rng(nm), "fill": {"color": col},
                           "border": {"none": True}, "gap": 60, "overlap": 100,
                           "data_labels": {"custom": [{"value": "=" + ref("Lbl" + nm, i)} for i in range(12)],
                                           "position": "outside_end", "font": {"name": XL_FUENTE, "size": 8, "color": XL["tx2"]}}})
        estilo_ch(ch, y_fmt="#,##0.0##")
        colocar(ws, ch, 29, XL_C0, 42, XL_C1)

        R_T = 44
        tarjeta(ws, R_T, XL_C0, R_T + 20, XL_C1, f_titulo='="Datos del mes · "&sel_var&" ("&IF(sel_ratio,"%",sel_uni)&")"',
                ayuda="Variación vs. AA: % para montos, puntos porcentuales para Cesión. Todo se recalcula con el panel.")
        heads = [("Mes", 3, None), ('=sel_anio&""', 4, "SelY"), ('="AA "&sel_ant', 4, "SelA"), ("Variación vs. AA", 4, "VsAA"),
                 ("Cambio vs. mes anterior", 5, "Cambio"), ("Promedio del año", 4, "Prom")]
        c = XL_C0
        for t, w, _ in heads:
            encabezado(ws, R_T + 2, c, t, w, al="left" if t == "Mes" else "right", formula=t.startswith("="))
            c += w
        for i in range(12):
            r = R_T + 3 + i
            c = XL_C0
            for t, w, key in heads:
                z = i % 2 == 1
                if key is None:
                    celda_tabla(ws, r, c, MESES[i], w, zebra=z, b=True, al="left")
                else:
                    nfm = '+0.0%;-0.0%' if key == "VsAA" else "#,##0.0"
                    celda_tabla(ws, r, c, f'=IFERROR({ref(key, i)},"—")', w, nf=nfm, zebra=z, b=key == "SelY",
                                color=XL["navy"] if key == "SelY" else None)
                    if key == "VsAA":
                        ws.conditional_format(r, c, r, c + w - 1, {"type": "formula", "criteria": ES_RATIO,
                                                                  "format": dxf(num_format='+0.00" pp";-0.00" pp"')})
                        ws.conditional_format(r, c, r, c + w - 1, {"type": "cell", "criteria": "<", "value": 0,
                                                                  "format": dxf(font_color=XL["neg"])})
                        ws.conditional_format(r, c, r, c + w - 1, {"type": "cell", "criteria": ">=", "value": 0,
                                                                  "format": dxf(font_color=XL["pos"])})
                    elif key == "Cambio":
                        ws.conditional_format(r, c, r, c + w - 1, {"type": "formula", "criteria": ES_RATIO,
                                                                  "format": dxf(num_format='+0.00%;-0.00%')})
                    else:
                        fmt_ratio(ws, (r, c, r, c + w - 1))
                c += w
        r = R_T + 16
        resumen_f = [("Cierre / acumulado", f'=IF(sel_clave="PT",SUM({ref("SelY")}),{ultimo(ref("SelY"))})',
                      f'=IF(sel_clave="PT",SUM({ref("SelA")}),{ultimo(ref("SelA"))})'),
                     ("Promedio", f"=AVERAGE({ref('SelY')})", f"=AVERAGE({ref('SelA')})"),
                     ("Máximo", f"=MAX({ref('SelY')})", f"=MAX({ref('SelA')})"),
                     ("Mínimo", f"=MIN({ref('SelY')})", f"=MIN({ref('SelA')})")]
        for i, (t, fy, fa) in enumerate(resumen_f):
            celda_tabla(ws, r + i, XL_C0, t, 3, b=True, al="left", zebra=True)
            celda_tabla(ws, r + i, XL_C0 + 3, f"=IFERROR({fy[1:]},\"—\")", 4, b=True, color=XL["navy"], zebra=True)
            celda_tabla(ws, r + i, XL_C0 + 7, f"=IFERROR({fa[1:]},\"—\")", 4, zebra=True)
            fmt_ratio(ws, (r + i, XL_C0 + 3, r + i, XL_C0 + 10))
            celda_tabla(ws, r + i, XL_C0 + 11, "", 13, zebra=True, formula=False)

        # ======================= 03 ESTACIONALIDAD =======================
        ws = hojas[2]
        tarjeta(ws, 7, XL_C0, 26, XL_C1, f_titulo='=sel_var&" vs. "&sel_pri&", año por año · "&sel_conc',
                ayuda="Un panel por año. Barras naranjas: prima. Línea azul: variable elegida. "
                      "Arriba de 1.00 el mes está por encima del promedio de su año; abajo, por debajo.")
        n_a = len(anios_todos)
        ancho = (XL_C1 - XL_C0 + 1) // n_a
        for i, a in enumerate(anios_todos):
            ch = wb.add_chart({"type": "column"})
            ch.add_series({"name": "Prima", "categories": rng("Mes"), "values": rng(f"IP_{a}"),
                           "fill": {"color": XL["acc_s"]}, "border": {"none": True}, "gap": 40})
            ln = wb.add_chart({"type": "line"})
            ln.add_series({"name": "Variable", "categories": rng("Mes"), "values": rng(f"IV_{a}"),
                           "line": {"color": XL["navy"], "width": 2.75},
                           "marker": {"type": "circle", "size": 5, "fill": {"color": XL["navy"]}, "border": {"color": "#FFFFFF"}}})
            ln.add_series({"name": "1.00", "categories": rng("Mes"), "values": rng("Base1"),
                           "line": {"color": XL["tx3"], "width": 1, "dash_type": "round_dot"}, "marker": {"type": "none"}})
            ch.combine(ln)
            estilo_ch(ch, leyenda=(i == 0), y_fmt="0.00", y_min=0)
            ch.set_title({"name": str(a), "name_font": {"name": XL_FUENTE, "size": 12, "bold": True, "color": XL["tx"]},
                          "overlay": False})
            c1 = XL_C0 + i * ancho
            colocar(ws, ch, 7, c1, 26, c1 + ancho - 1)

        tarjeta(ws, 28, XL_C0, 40, XL_C0 + 10, "Lectura por año",
                "Correlación cercana a +1: se mueve igual que la prima. Amplitud = índice más alto − más bajo.")
        enc = [("Año", 1), ("Correlación", 2), ("Pico var.", 2), ("Pico prima", 2), ("Amp. var.", 2), ("Amp. prima", 2)]
        c = XL_C0
        for t, w in enc:
            encabezado(ws, 30, c, t, w, al="left" if t == "Año" else "right")
            c += w
        nfs = ["0", "+0.00;-0.00", "@", "@", "0.00", "0.00"]
        for i, a in enumerate(anios_todos):
            c = XL_C0
            for j, (t, w) in enumerate(enc):
                celda_tabla(ws, 31 + i, c, f"=Calculos!{col_l(j)}{B_LECT + 2 + i}", w, nf=nfs[j], zebra=i % 2 == 1,
                            b=j == 0, al="left" if j == 0 else "right")
                c += w
            ws.conditional_format(31 + i, XL_C0, 31 + i, XL_C0 + 10, {"type": "formula", "criteria": f"=$D${32 + i}=sel_anio",
                                                                     "format": dxf(bold=True, font_color=XL["navy"])})
        ws.merge_range(31 + n_a + 1, XL_C0, 31 + n_a + 3, XL_C0 + 10,
                       "Una reserva es un saldo: normalmente se mueve menos que la prima del mes, por eso su amplitud es menor. "
                       "El año elegido en el panel aparece resaltado.", F(bg=XL["card"], c=XL["tx3"], s=9, wr=True, ind=1, va="top"))

        tarjeta(ws, 28, XL_C0 + 11, 40, XL_C1, f_titulo='="Comparación entre años · "&sel_var',
                ayuda="Mismo índice de la variable, un color por año (más oscuro = más reciente).")
        ch = wb.add_chart({"type": "line"})
        for a in anios_todos:
            col = color_anio(a, anios_todos)
            ch.add_series({"name": str(a), "categories": rng("Mes"), "values": rng(f"IV_{a}"),
                           "line": {"color": col, "width": 2.75 if a == anios_todos[-1] else 2},
                           "marker": {"type": "circle", "size": 5, "fill": {"color": col}, "border": {"color": col}}})
        ch.add_series({"name": "1.00", "categories": rng("Mes"), "values": rng("Base1"),
                       "line": {"color": XL["tx3"], "width": 1, "dash_type": "round_dot"}, "marker": {"type": "none"}})
        estilo_ch(ch, leyenda=True, y_fmt="0.00")
        colocar(ws, ch, 28, XL_C0 + 11, 40, XL_C1)

        R_H = 42
        tarjeta(ws, R_H, XL_C0, R_H + n_a + 4, XL_C0 + 13,
                f_titulo='=sel_var&" por mes y año ("&IF(sel_ratio,"%",LOWER(sel_uni))&")"',
                ayuda="Mapa de calor: entre más oscuro, mayor el monto.")
        ws.write(R_H + 2, XL_C0, "Año", F(bg=XL["card"], c=XL["tx3"], b=True, s=9, al="center"))
        for j, m in enumerate(MESES):
            ws.write(R_H + 2, XL_C0 + 1 + j, m, F(bg=XL["card"], c=XL["tx3"], b=True, s=9, al="center"))
        f_h = F(bg="#F3F4F8", s=10, al="center", nf="#,##0.0")
        for i, a in enumerate(anios_todos):
            ws.set_row_pixels(R_H + 3 + i, 34)
            ws.write(R_H + 3 + i, XL_C0, a, F(bg=XL["card"], b=True, s=10, al="center"))
            for j in range(12):
                ws.write_formula(R_H + 3 + i, XL_C0 + 1 + j, f'=IFERROR({ref(f"V_{a}", j)},"")', f_h)
        hrng = (R_H + 3, XL_C0 + 1, R_H + 2 + n_a, XL_C0 + 12)
        ws.conditional_format(*hrng, {"type": "3_color_scale", "min_color": "#F3F4F8", "mid_color": "#9BA5CF",
                                      "max_color": XL["navy"]})
        a1 = celda(hrng[0], hrng[1], row_abs=True, col_abs=True)
        a2 = celda(hrng[2], hrng[3], row_abs=True, col_abs=True)
        tl = celda(hrng[0], hrng[1])
        ws.conditional_format(*hrng, {"type": "formula", "criteria": f"={tl}>=PERCENTILE({a1}:{a2},0.55)",
                                      "format": dxf(font_color="#FFFFFF", bold=True)})
        fmt_ratio(ws, hrng)

        tarjeta(ws, R_H, XL_C0 + 14, R_H + 16, XL_C1, f_titulo='="Estacionalidad por ramo · "&sel_anio',
                ayuda="Patrón mensual de cada ramo incluido (1.00 = mes promedio).")
        ch = wb.add_chart({"type": "line"})
        for r in ramos_xl:
            col = color_ramo(r, ramos_todos)
            ch.add_series({"name": f"Ramo {r}", "categories": rng("Mes"), "values": rng(f"IR_{r}"),
                           "line": {"color": col, "width": 2}, "marker": {"type": "circle", "size": 4,
                                                                          "fill": {"color": col}, "border": {"color": col}}})
        ch.add_series({"name": "1.00", "categories": rng("Mes"), "values": rng("Base1"),
                       "line": {"color": XL["tx3"], "width": 1, "dash_type": "round_dot"}, "marker": {"type": "none"}})
        estilo_ch(ch, leyenda=True, y_fmt="0.00")
        colocar(ws, ch, R_H, XL_C0 + 14, R_H + 16, XL_C1)

        # ======================= 04 CONCEPTOS =======================
        ws = hojas[3]
        tarjeta(ws, 7, XL_C0, 27, XL_C1, f_titulo='=sel_var&" por concepto · "&sel_anio',
                ayuda="Cada línea es un concepto, con la suma de los ramos incluidos en el panel.")
        ch = wb.add_chart({"type": "line"})
        for c in conceptos:
            col = T["conceptos"].get(c, XL["tx3"])
            ch.add_series({"name": c, "categories": rng("Mes"), "values": rng(f"C_{c}"),
                           "line": {"color": col, "width": 2.75}, "marker": {"type": "circle", "size": 4,
                                                                             "fill": {"color": col}, "border": {"color": col}}})
        estilo_ch(ch, leyenda=True, y_fmt="#,##0.0##")
        colocar(ws, ch, 7, XL_C0, 27, XL_C1)
        R_T = 29
        n_c = len(conceptos)
        wcol = max(3, (24 - 3) // max(n_c, 1))
        tarjeta(ws, R_T, XL_C0, R_T + 20, XL_C1, f_titulo='="Datos por concepto · "&sel_var&" ("&IF(sel_ratio,"%",sel_uni)&")"',
                ayuda="El concepto elegido en el panel aparece resaltado. Al final: cierre, AA y variación.")
        encabezado(ws, R_T + 2, XL_C0, "Mes", 3, al="left")
        for k, c in enumerate(conceptos):
            encabezado(ws, R_T + 2, XL_C0 + 3 + k * wcol, c, wcol)
        for i in range(12):
            celda_tabla(ws, R_T + 3 + i, XL_C0, MESES[i], 3, zebra=i % 2 == 1, b=True, al="left")
            for k, c in enumerate(conceptos):
                cc = XL_C0 + 3 + k * wcol
                celda_tabla(ws, R_T + 3 + i, cc, f'=IFERROR({ref(f"C_{c}", i)},"—")', wcol, zebra=i % 2 == 1)
        extra = [("Cierre / acumulado", "C_"), ("AA", "CA_"), ("Variación vs. AA", None)]
        for j, (t, pre) in enumerate(extra):
            r = R_T + 15 + j
            celda_tabla(ws, r, XL_C0, t, 3, b=True, al="left", zebra=True)
            for k, c in enumerate(conceptos):
                cc = XL_C0 + 3 + k * wcol
                if pre:
                    rg = ref(pre + c)
                    celda_tabla(ws, r, cc, f'=IFERROR(IF(sel_clave="PT",SUM({rg}),{ultimo(rg)}),"—")', wcol, b=True, zebra=True)
                else:
                    a_, b_ = celda(R_T + 15, cc), celda(R_T + 16, cc)
                    celda_tabla(ws, r, cc, f'=IFERROR(IF(sel_ratio,{a_}-{b_},{a_}/{b_}-1),"—")', wcol, nf="+0.0%;-0.0%",
                                b=True, zebra=True)
                    ws.conditional_format(r, cc, r, cc + wcol - 1, {"type": "formula", "criteria": ES_RATIO,
                                                                   "format": dxf(num_format='+0.00%;-0.00%')})
                    ws.conditional_format(r, cc, r, cc + wcol - 1, {"type": "cell", "criteria": "<", "value": 0,
                                                                   "format": dxf(font_color=XL["neg"])})
                    ws.conditional_format(r, cc, r, cc + wcol - 1, {"type": "cell", "criteria": ">=", "value": 0,
                                                                   "format": dxf(font_color=XL["pos"])})
        cuerpo = (R_T + 3, XL_C0 + 3, R_T + 16, XL_C0 + 2 + n_c * wcol)
        fmt_ratio(ws, cuerpo)
        for k, c in enumerate(conceptos):
            cc = XL_C0 + 3 + k * wcol
            ws.conditional_format(R_T + 3, cc, R_T + 17, cc + wcol - 1,
                                  {"type": "formula", "criteria": f'=sel_conc="{c}"', "format": dxf(bold=True, font_color=XL["navy"],
                                                                                                   bg_color=XL["nav_s"])})

        # ======================= 05 DETALLE POR RAMO =======================
        ws = hojas[4]
        for i, r in enumerate(ramos_xl):
            ws.merge_range(4, XL_C1 - 2 * (n_r - i) + 1, 4, XL_C1 - 2 * (n_r - i) + 2, f"● Ramo {r}",
                           F(bg=XL["bg"], c=color_ramo(r, ramos_todos), b=True, s=10, al="center"))
        cajas = [(7, XL_C0), (7, XL_C0 + 8), (7, XL_C0 + 16), (23, XL_C0), (23, XL_C0 + 8), (23, XL_C0 + 16)]
        for v, (r1, c1) in zip(DETALLE, cajas):
            es_r = v in RATIOS
            tarjeta(ws, r1, c1, r1 + 14, c1 + 7, VARIABLES[v], "%" if es_r else None)
            if not es_r:
                ws.merge_range(r1 + 1, c1, r1 + 1, c1 + 7, "", F(bg=XL["card"], s=9, c=XL["tx3"], ind=1, va="top"))
                ws.write_formula(r1 + 1, c1, '=sel_uni&" de pesos · "&sel_conc&" · "&sel_anio',
                                 F(bg=XL["card"], s=9, c=XL["tx3"], ind=1, va="top"))
            ch = wb.add_chart({"type": "line"})
            for r in ramos_xl:
                ch.add_series({"name": f"Ramo {r}", "categories": rng("Mes"), "values": rng(f"D_{v}_{r}"),
                               "line": {"color": color_ramo(r, ramos_todos), "width": 2}, "marker": {"type": "none"}})
            estilo_ch(ch, y_fmt="0%" if es_r else "#,##0.0##")
            colocar(ws, ch, r1, c1, r1 + 14, c1 + 7)
        R_T = 39
        ws.merge_range(R_T, XL_C0, R_T, XL_C1, "Tablas por variable", F(bg=XL["bg"], b=True, s=13, ind=1))
        w_m, w_r = 3, 3
        w_t = (XL_C1 - XL_C0 + 1) - w_m - w_r * n_r
        for n_v, v in enumerate(DETALLE):
            es_r = v in RATIOS
            nfv = "0.0%" if es_r else "#,##0.0"
            fila_t = R_T + 2 + n_v * 18
            tarjeta(ws, fila_t, XL_C0, fila_t + 16, XL_C1, VARIABLES[v] + (" (%)" if es_r else ""))
            if not es_r:
                f_s = F(bg=XL["card"], s=9, c=XL["tx3"], ind=1, va="top")
                ws.merge_range(fila_t + 1, XL_C0, fila_t + 1, XL_C1, "", f_s)
                ws.write_formula(fila_t + 1, XL_C0, '="En "&LOWER(sel_uni)&" de pesos · "&sel_conc&" · "&sel_anio', f_s)
            encabezado(ws, fila_t + 2, XL_C0, "Mes", w_m, al="left")
            for k, r in enumerate(ramos_xl):
                encabezado(ws, fila_t + 2, XL_C0 + w_m + k * w_r, f"Ramo {r}", w_r)
            encabezado(ws, fila_t + 2, XL_C0 + w_m + n_r * w_r, "Total" + (" ponderado" if es_r else ""), w_t)
            for i in range(12):
                z = i % 2 == 1
                celda_tabla(ws, fila_t + 3 + i, XL_C0, MESES[i], w_m, zebra=z, b=True, al="left")
                for k, r in enumerate(ramos_xl):
                    celda_tabla(ws, fila_t + 3 + i, XL_C0 + w_m + k * w_r, f'=IFERROR({ref(f"D_{v}_{r}", i)},"—")', w_r,
                                nf=nfv, zebra=z)
                celda_tabla(ws, fila_t + 3 + i, XL_C0 + w_m + n_r * w_r, f'=IFERROR({ref(f"DT_{v}", i)},"—")', w_t,
                            nf=nfv, zebra=z, b=True, color=XL["navy"])

        # ======================= 06 TABLA MENSUALIZADA =======================
        ws = hojas[5]
        w_v = max(2, (24 - 3) // (n_r + 1))
        tarjeta(ws, 7, XL_C0, 7 + 25, XL_C0 + 3 + (n_r + 1) * w_v - 1,
                f_titulo='=sel_var&" · "&sel_conc&" · "&sel_anio&" ("&IF(sel_ratio,"%",sel_uni)&")"',
                ayuda="Mensualización por ramo; Total en azul. Los ramos excluidos en el panel aparecen como —.")
        encabezado(ws, 9, XL_C0, "Mes", 3, al="left")
        for k, r in enumerate(ramos_xl):
            encabezado(ws, 9, XL_C0 + 3 + k * w_v, f"Ramo {r}", w_v)
        encabezado(ws, 9, XL_C0 + 3 + n_r * w_v, "Total", w_v)
        for i in range(12):
            z = i % 2 == 1
            celda_tabla(ws, 10 + i, XL_C0, MESES[i], 3, zebra=z, b=True, al="left")
            for k, r in enumerate(ramos_xl):
                celda_tabla(ws, 10 + i, XL_C0 + 3 + k * w_v, f'=IFERROR({ref(f"R_{r}", i)},"—")', w_v, zebra=z)
            celda_tabla(ws, 10 + i, XL_C0 + 3 + n_r * w_v, f'=IFERROR({ref("SelY", i)},"—")', w_v, zebra=z, b=True,
                        color=XL["navy"])
        resumen = [("Promedio", "AVERAGE"), ("Mínimo", "MIN"), ("Máximo", "MAX")]
        for j, (t, fn) in enumerate(resumen):
            r = 23 + j
            celda_tabla(ws, r, XL_C0, t, 3, b=True, al="left", zebra=True)
            for k in range(n_r + 1):
                cc = XL_C0 + 3 + k * w_v
                a1_, a2_ = celda(10, cc), celda(21, cc)
                celda_tabla(ws, r, cc, f'=IFERROR({fn}({a1_}:{a2_}),"—")', w_v, b=True, zebra=True)
        r = 26
        celda_tabla(ws, r, XL_C0, "Cierre / acumulado", 3, b=True, al="left", zebra=True)
        for k in range(n_r + 1):
            cc = XL_C0 + 3 + k * w_v
            rg_ = f"{celda(10, cc, True, True)}:{celda(21, cc, True, True)}"
            celda_tabla(ws, r, cc, f'=IFERROR(IF(sel_clave="PT",SUM({rg_}),{ultimo(rg_)}),"—")', w_v, b=True, zebra=True,
                        color=XL["navy"])
        celda_tabla(ws, 27, XL_C0, "AA", 3, b=True, al="left", zebra=True)
        celda_tabla(ws, 28, XL_C0, "Variación vs. AA", 3, b=True, al="left", zebra=True)
        for k in range(n_r + 1):
            cc = XL_C0 + 3 + k * w_v
            if k < n_r:
                r_ = ramos_xl[k]
                aa = f'IFERROR(IF(Calculos!$E${k + 2}=0,NA(),IF(sel_ratio,1,1/sel_div)*IF(sel_clave="PT",SUMPRODUCT(SUMIFS(bd_val,bd_conc,sel_conc,bd_clave,sel_clave,bd_per,{ref("PerA")},bd_ramo,{int(r_)})),SUMIFS(bd_val,bd_conc,sel_conc,bd_clave,sel_clave,bd_per,sel_ant*100+12,bd_ramo,{int(r_)}))),"—")'
            else:
                aa = f'IFERROR(IF(sel_clave="PT",SUM({ref("SelA")}),{ultimo(ref("SelA"))}),"—")'
            celda_tabla(ws, 27, cc, "=" + aa, w_v, zebra=True)
            a_, b_ = celda(26, cc), celda(27, cc)
            celda_tabla(ws, 28, cc, f'=IFERROR(IF(sel_ratio,{a_}-{b_},{a_}/{b_}-1),"—")', w_v, nf="+0.0%;-0.0%", b=True, zebra=True)
            ws.conditional_format(28, cc, 28, cc + w_v - 1, {"type": "formula", "criteria": ES_RATIO,
                                                            "format": dxf(num_format='+0.00%;-0.00%')})
            ws.conditional_format(28, cc, 28, cc + w_v - 1, {"type": "cell", "criteria": "<", "value": 0,
                                                            "format": dxf(font_color=XL["neg"])})
            ws.conditional_format(28, cc, 28, cc + w_v - 1, {"type": "cell", "criteria": ">=", "value": 0,
                                                            "format": dxf(font_color=XL["pos"])})
        fmt_ratio(ws, (10, XL_C0 + 3, 27, XL_C0 + 2 + (n_r + 1) * w_v))
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
