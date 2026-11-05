# -*- coding: utf-8 -*-
"""
PRISMA · Proyección de Reservas FCST 2027   (Plotly Dash)
=========================================================
Lee BD_RFV_Proyeccion (hoja BD_Montos_RRC_SONR) y muestra la mensualización,
la estacionalidad (comparada con la de la prima, año por año) y los montos.
Los filtros (Concepto, Variable, Ramo, Año, Mes, Unidades) están en un panel
que se abre con el botón "Filtros".

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
PRIMAS = {"PT": "Prima del mes (PT)", "PRIMA 24M": "Prima 24M"}
FLUJOS = {"PT"}            # se acumulan en el año; el resto son saldos (se toma el cierre)
RATIOS = {"CESION"}        # porcentajes: promedio ponderado por la reserva
MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
UNIDADES = {"Pesos": (1, ""), "Miles": (1e3, " K"), "Millones": (1e6, " M")}

# ---- Temas (oscuro verde agua / claro naranja). Paletas categóricas validadas para daltonismo.
TEMAS = {
    "oscuro": dict(
        bg="#0a0f14", card="#101920", text="#e9f2f3", text2="#a9b7bf", text3="#6f7f8a",
        grid="rgba(255,255,255,0.06)", linea="#22313b", accent="#2dd4bf", pos="#34d399", neg="#f87171",
        anios=["#2dd4bf", "#f5a524", "#8ea0b5", "#d55181"],
        ramos=["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"],
        heat=["#0f2a2e", "#115e59", "#0f766e", "#14b8a6", "#5eead4"],
        hover_bg="#15232c"),
    "claro": dict(
        bg="#f4f1ec", card="#ffffff", text="#1d232b", text2="#4b5563", text3="#8b919a",
        grid="rgba(0,0,0,0.06)", linea="#e6e1d9", accent="#ea6a1f", pos="#16a34a", neg="#dc2626",
        anios=["#ea6a1f", "#2a78d6", "#8b95a1", "#d55181"],
        ramos=["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"],
        heat=["#fff4ec", "#fed7aa", "#fb923c", "#ea580c", "#9a3412"],
        hover_bg="#ffffff"),
}
CONCEPTOS_ORDEN = ["RCONT", "RFV BRUTO", "RFV IRR", "RFV NETO"]


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


# ---- Cálculos -------------------------------------------------------------------------
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


def color_anio(a, todos, T):
    """El año más reciente toma el color de acento; los anteriores, colores fijos."""
    orden = sorted(todos, reverse=True)
    return T["anios"][min(orden.index(a), len(T["anios"]) - 1)] if a in orden else T["text3"]


def color_ramo(r, ramos_todos, T):
    return T["ramos"][ramos_todos.index(r) % len(T["ramos"])] if r in ramos_todos else T["text3"]


# ---- Estilo de gráficas ---------------------------------------------------------------
GRAPH_CFG = {"displaylogo": False, "displayModeBar": "hover",
             "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d", "zoomIn2d", "zoomOut2d"],
             "toImageButtonOptions": {"format": "png", "scale": 2}}


def estilo(fig, T, h, ytitle=None, ratio=False, leyenda=True, ytick=None, compacto=False):
    fig.update_layout(
        height=h, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, system-ui, -apple-system, 'Segoe UI', sans-serif", color=T["text2"], size=12),
        margin=dict(l=8, r=12, t=30 if leyenda else 8, b=8),
        hovermode="x unified", showlegend=leyenda,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, font=dict(color=T["text2"], size=11),
                    traceorder="normal", bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor=T["hover_bg"], font=dict(color=T["text"]), bordercolor=T["linea"]),
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


def vacia(T, msg="Selecciona al menos un ramo, un año y un mes en Filtros", h=320):
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False, font=dict(color=T["text3"], size=13))
    fig.update_layout(height=h, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      margin=dict(l=10, r=10, t=10, b=10))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


# ---- Íconos (trazos tipo Feather, MIT) -------------------------------------------------
_ICONOS = {
    "home": '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
    "barras": '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
    "onda": '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    "capas": '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
    "grid": '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>',
    "tabla": '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>',
    "filtro": '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>',
    "luna": '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
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
    html.A(html.Span("P", className="mark"), href="#resumen", className="rail-logo", title="PRISMA"),
    html.Div([html.A([ic(i), html.Span(t, className="tip")], href=f"#{s}", className="rail-btn") for s, i, t in NAV],
             className="rail-nav"),
    html.Div([
        html.Button([ic("filtro"), html.Span("Filtros", className="tip")], id="rail-filtros", className="rail-btn"),
        html.Button([ic("luna"), html.Span("Tema claro / oscuro", className="tip")], id="btn-tema", className="rail-btn"),
    ], className="rail-foot"),
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
    html.Header([
        html.Div([html.Div("PRISMA", className="brand"),
                  html.Div("Proyección de reservas · FCST 2027", className="brand-sub")], className="brand-box"),
        html.Div([html.Div(id="chips", className="chips", n_clicks=0, title="Abrir filtros"),
                  html.Button([ic("filtro"), html.Span("Filtros")], id="btn-filtros", className="btn-filtros")],
                 className="top-right"),
    ], className="top"),
    html.Div(id="aviso"),

    seccion("resumen", "01", "Resumen", "Cifras clave al cierre del periodo filtrado y su cambio contra el año anterior (AA).",
            html.Div(id="kpis", className="kpis")),

    seccion("mensual", "02", "Mes a mes", "Cómo se reparte el monto en cada mes y qué ramos lo explican.",
            html.Div([
                panel("Monto por mes", "Cada barra es el total del mes. La línea punteada es el promedio; "
                      "el color distingue el año.", grafica("g-mens", 380), id_titulo="t-mens"),
                panel("Por ramo", "Cuánto aporta cada ramo y qué porcentaje representa del total.",
                      grafica("g-ramo", 380), id_titulo="t-ramo"),
            ], className="grid g-2-1"),
            panel("Cambio contra el mes anterior", "Barras verdes: el monto subió; rojas: bajó.",
                  grafica("g-mom", 250))),

    seccion("estacional", "03", "Estacionalidad",
            "¿En qué meses el monto está por arriba o por abajo de lo normal? Comparado año contra año y contra la prima.",
            html.Div([
                panel("Estacionalidad vs. prima", "", grafica("g-comp", 400), id_titulo="t-comp", id_ayuda="a-comp"),
                panel("Lectura por año", "Correlación cercana a +1: se mueve igual que la prima. "
                      "Amplitud: índice más alto − más bajo (qué tan marcada es la estacionalidad).",
                      html.Div(id="est-stats")),
            ], className="grid g-2-1"),
            html.Div([
                panel("Monto por mes y año", "Mapa de calor: entre más intenso el color, mayor el monto.",
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
            html.Div([panel(t, "", grafica(f"g-v{i}", 250), id_titulo=f"t-v{i}", cls="mini-panel")
                      for i, t in enumerate(["Reserva", "Prima 24M", "PR 24M", "Monto afianzado (MA)", "RFV MA", "Cesión"])],
                     className="grid g-3"),
            extra=html.Div(id="ramo-leyenda", className="leyenda")),

    seccion("tabla-sec", "06", "Tabla mensualizada", "Los números detrás de las gráficas, listos para descargar.",
            html.Div(id="tabla", className="card tabla-wrap"), dcc.Download(id="dl"),
            extra=html.Button([ic("bajar"), html.Span("Descargar Excel")], id="btn-xls", className="btn-pri")),
    html.Footer(id="pie", className="pie"),
], className="main")

app = Dash(__name__, title="PRISMA · Reservas FCST 2027", update_title=None)
app.layout = html.Div([
    dcc.Store(id="version", data=0), dcc.Store(id="tema", data="oscuro", storage_type="local"),
    rail, html.Div(id="overlay", className="overlay", n_clicks=0), drawer, main,
], id="app", className="app tema-oscuro")

app.index_string = """<!DOCTYPE html>
<html lang="es"><head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
.tema-oscuro { --bg:#0a0f14; --bg2:#0d151b; --card:rgba(18,28,36,.78); --card-solid:#101920; --borde:rgba(45,212,191,.16);
  --borde2:rgba(255,255,255,.07); --tx:#e9f2f3; --tx2:#a9b7bf; --tx3:#6f7f8a; --acc:#2dd4bf; --acc-soft:rgba(45,212,191,.14);
  --pos:#34d399; --pos-soft:rgba(52,211,153,.14); --neg:#f87171; --neg-soft:rgba(248,113,113,.14); --sombra:0 8px 30px rgba(0,0,0,.35);
  --glow:radial-gradient(1200px 500px at 10% -10%, rgba(45,212,191,.10), transparent 60%), radial-gradient(900px 400px at 100% 0%, rgba(56,135,229,.07), transparent 60%);
  color-scheme:dark; }
.tema-claro { --bg:#f4f1ec; --bg2:#ece7df; --card:#ffffff; --card-solid:#ffffff; --borde:rgba(234,106,31,.18);
  --borde2:rgba(0,0,0,.07); --tx:#1d232b; --tx2:#4b5563; --tx3:#8b919a; --acc:#ea6a1f; --acc-soft:rgba(234,106,31,.12);
  --pos:#16a34a; --pos-soft:rgba(22,163,74,.12); --neg:#dc2626; --neg-soft:rgba(220,38,38,.10); --sombra:0 6px 22px rgba(60,40,20,.08);
  --glow:radial-gradient(1200px 500px at 10% -10%, rgba(234,106,31,.07), transparent 60%);
  color-scheme:light; }
.app { --Dash-Fill-Inverse-Strong:var(--card-solid); --Dash-Fill-Interactive-Strong:var(--acc); --Dash-Fill-Interactive-Weak:var(--acc-soft);
  --Dash-Fill-Primary-Hover:var(--acc-soft); --Dash-Fill-Primary-Active:var(--acc-soft); --Dash-Fill-Disabled:var(--borde2);
  --Dash-Stroke-Strong:var(--borde); --Dash-Stroke-Weak:var(--borde2); --Dash-Text-Primary:var(--tx); --Dash-Text-Strong:var(--tx);
  --Dash-Text-Weak:var(--tx2); --Dash-Text-Disabled:var(--tx3); }
* { box-sizing:border-box; }
html { scroll-behavior:smooth; }
body { margin:0; font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif; -webkit-font-smoothing:antialiased; }
.app { min-height:100vh; background:var(--glow), var(--bg); background-attachment:fixed; color:var(--tx); }
.ic { display:inline-block; width:18px; height:18px; background:currentColor; flex:0 0 auto; }
%%ICONOS%%
/* --- riel izquierdo --- */
.rail { position:fixed; left:0; top:0; bottom:0; width:68px; z-index:40; display:flex; flex-direction:column; align-items:center;
  padding:16px 0; background:var(--bg2); border-right:1px solid var(--borde2); }
.rail-logo { text-decoration:none; margin-bottom:22px; }
.mark { width:38px; height:38px; border-radius:11px; display:flex; align-items:center; justify-content:center; font-weight:800;
  font-size:18px; color:var(--bg); background:linear-gradient(135deg,var(--acc),#5eead4); }
.tema-claro .mark { background:linear-gradient(135deg,var(--acc),#f6a15e); color:#fff; }
.rail-nav { display:flex; flex-direction:column; gap:6px; }
.rail-foot { margin-top:auto; display:flex; flex-direction:column; gap:6px; }
.rail-btn { position:relative; width:42px; height:42px; border-radius:11px; display:flex; align-items:center; justify-content:center;
  color:var(--tx3); background:none; border:0; cursor:pointer; text-decoration:none; }
.rail-btn:hover { color:var(--acc); background:var(--acc-soft); }
.tip { position:absolute; left:52px; white-space:nowrap; background:var(--card-solid); color:var(--tx); border:1px solid var(--borde);
  font-size:12px; padding:5px 9px; border-radius:7px; opacity:0; pointer-events:none; transform:translateX(-4px); transition:.15s; box-shadow:var(--sombra); }
.rail-btn:hover .tip { opacity:1; transform:none; }
/* --- panel de filtros --- */
.overlay { position:fixed; inset:0; background:rgba(0,0,0,.35); opacity:0; pointer-events:none; transition:.2s; z-index:45; }
.overlay.abierto { opacity:1; pointer-events:auto; }
.drawer { position:fixed; top:0; bottom:0; left:68px; width:300px; z-index:50; overflow-y:auto; padding:18px 18px 26px;
  background:var(--card-solid); border-right:1px solid var(--borde); box-shadow:var(--sombra);
  transform:translateX(calc(-100% - 90px)); visibility:hidden; transition:transform .25s ease, visibility .25s; }
.drawer.abierto { transform:none; visibility:visible; }
.dr-head { display:flex; align-items:center; justify-content:space-between; }
.dr-title { display:flex; gap:8px; align-items:center; font-weight:700; font-size:15px; color:var(--acc); }
.dr-sub { color:var(--tx3); font-size:12px; margin:6px 0 10px; }
.icon-btn { background:none; border:0; color:var(--tx3); cursor:pointer; padding:6px; border-radius:8px; display:flex; }
.icon-btn:hover { color:var(--tx); background:var(--acc-soft); }
.f-blk { padding:13px 0; border-top:1px solid var(--borde2); }
.f-lbl { font-size:10.5px; font-weight:700; letter-spacing:.09em; text-transform:uppercase; color:var(--tx3); margin-bottom:9px; }
.lista label { display:flex !important; align-items:center; gap:8px; padding:6px 9px; border-radius:8px; color:var(--tx2);
  font-size:13px; cursor:pointer; margin:1px 0; }
.lista label:hover { background:var(--acc-soft); }
.lista label:has(input:checked) { background:var(--acc-soft); color:var(--tx); font-weight:600; }
.lista input { accent-color:var(--acc); margin:0; }
.pills, .seg { display:flex; flex-wrap:wrap; gap:6px; }
.pills label, .seg label { display:inline-flex !important; align-items:center; justify-content:center; padding:5px 11px; border-radius:999px;
  font-size:12.5px; color:var(--tx2); border:1px solid var(--borde2); cursor:pointer; user-select:none; margin:0; }
.seg label { border-radius:8px; flex:1 1 calc(50% - 6px); }
.pills label:hover, .seg label:hover { border-color:var(--borde); }
.pills label:has(input:checked), .seg label:has(input:checked) { background:var(--acc-soft); border-color:var(--acc); color:var(--tx); font-weight:600; }
.pills input, .seg input { position:absolute; opacity:0; width:0; height:0; }
.pills.meses label { width:calc(25% - 5px); padding:5px 0; }
.mini-row { display:flex; gap:6px; margin-top:8px; }
.mini { background:none; border:1px solid var(--borde2); color:var(--tx3); border-radius:6px; font-size:11.5px; padding:3px 9px; cursor:pointer; }
.mini:hover { color:var(--tx); }
.upload { display:flex; gap:6px; align-items:center; justify-content:center; border:1px dashed var(--borde); border-radius:9px; padding:10px;
  font-size:12.5px; color:var(--tx2); cursor:pointer; } .upload:hover { border-color:var(--acc); color:var(--acc); }
.fuente { color:var(--tx3); font-size:11.5px; margin-top:8px; word-break:break-all; }
.btn-sec { width:100%; margin-top:14px; padding:9px; border-radius:9px; border:1px solid var(--borde2); background:none; color:var(--tx2); cursor:pointer; font:inherit; font-size:12.5px; }
.btn-sec:hover { border-color:var(--acc); color:var(--acc); }
/* --- contenido --- */
.main { margin-left:68px; padding:0 34px 40px; max-width:1680px; }
header.top { position:sticky; top:0; z-index:30; display:flex; align-items:center; gap:18px; padding:16px 0 14px; margin-bottom:6px;
  background:linear-gradient(var(--bg) 70%, transparent); }
.brand { font-size:28px; font-weight:800; letter-spacing:.14em; line-height:1;
  background:linear-gradient(90deg,var(--acc),#5eead4 60%,#7cc4ff); -webkit-background-clip:text; background-clip:text; color:transparent; }
.tema-claro .brand { background:linear-gradient(90deg,#c2410c,var(--acc) 50%,#f6a15e); -webkit-background-clip:text; background-clip:text; }
.brand-sub { color:var(--tx3); font-size:12.5px; margin-top:5px; letter-spacing:.02em; }
.top-right { margin-left:auto; display:flex; align-items:center; gap:10px; flex-wrap:wrap; justify-content:flex-end; }
.chips { display:flex; gap:6px; flex-wrap:wrap; cursor:pointer; justify-content:flex-end; }
.chip { font-size:11.5px; color:var(--tx2); background:var(--card); border:1px solid var(--borde2); border-radius:999px; padding:4px 10px; }
.chip b { color:var(--tx3); font-weight:500; margin-right:4px; }
.btn-filtros { display:flex; align-items:center; gap:7px; padding:8px 14px; border-radius:10px; font:inherit; font-size:13px; font-weight:600;
  color:var(--acc); background:var(--acc-soft); border:1px solid var(--borde); cursor:pointer; }
.btn-filtros:hover { border-color:var(--acc); }
section.bloque { margin-top:30px; scroll-margin-top:86px; }
.sec-head { display:flex; align-items:center; gap:14px; flex-wrap:wrap; margin-bottom:14px; }
.num { font-size:12px; font-weight:700; color:var(--acc); background:var(--acc-soft); border:1px solid var(--borde); border-radius:8px; padding:5px 8px; }
.sec-head h2 { font-size:19px; font-weight:700; margin:0; letter-spacing:-.01em; }
.sec-sub { color:var(--tx3); font-size:13px; margin:3px 0 0; }
.grid { display:grid; gap:16px; margin-bottom:16px; }
.g-2 { grid-template-columns:1fr 1fr; } .g-2-1 { grid-template-columns:minmax(0,2fr) minmax(0,1fr); } .g-3 { grid-template-columns:repeat(3,minmax(0,1fr)); }
@media (max-width:1200px) { .g-2,.g-2-1,.g-3 { grid-template-columns:1fr; } }
.card { position:relative; background:var(--card); border:1px solid var(--borde); border-radius:16px; box-shadow:var(--sombra);
  backdrop-filter:blur(6px); }
.panel { padding:16px 18px 10px; min-width:0; }
.panel-head { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; margin-bottom:4px; }
.panel h3 { font-size:14.5px; font-weight:650; margin:0; color:var(--tx); }
.ayuda { color:var(--tx3); font-size:12px; margin:4px 0 0; line-height:1.45; }
.mini-panel .ayuda { display:none; }
/* KPIs */
.kpis { display:grid; gap:16px; grid-template-columns:minmax(0,1.35fr) repeat(3,minmax(0,1fr)); grid-template-rows:auto auto; }
@media (max-width:1200px) { .kpis { grid-template-columns:repeat(2,minmax(0,1fr)); } }
.kpi { padding:16px 18px; overflow:hidden; }
.kpi::after { content:""; position:absolute; top:-1px; right:-1px; width:26px; height:26px; border-top-right-radius:16px;
  background:linear-gradient(225deg,var(--acc) 50%,transparent 51%); opacity:.9; }
.kpi .t { display:flex; align-items:center; gap:9px; color:var(--tx2); font-size:12.5px; font-weight:500; }
.kpi .t .ico { width:28px; height:28px; border-radius:8px; display:flex; align-items:center; justify-content:center; background:var(--acc-soft); color:var(--acc); }
.kpi .t .ico .ic { width:15px; height:15px; }
.kpi .v { font-size:clamp(20px,1.8vw,28px); font-weight:750; letter-spacing:-.02em; margin:12px 0 6px; white-space:nowrap; font-variant-numeric:tabular-nums; }
.kpi .aa { font-size:12px; color:var(--tx3); display:flex; gap:6px; align-items:center; flex-wrap:wrap; }
.kpi .pie-k { font-size:11.5px; color:var(--tx3); margin-top:8px; padding-top:8px; border-top:1px dashed var(--borde2); }
.kpi.hero { grid-row:span 2; display:flex; flex-direction:column; }
.kpi.hero .v { font-size:clamp(28px,2.6vw,40px); }
.kpi.hero .spark { margin-top:auto; }
.badge { font-weight:650; padding:2px 8px; border-radius:999px; font-size:11.5px; }
.badge.up { color:var(--pos); background:var(--pos-soft); } .badge.down { color:var(--neg); background:var(--neg-soft); }
.badge.neu { color:var(--tx3); background:var(--borde2); }
/* controles */
.ctls { display:flex; gap:12px; margin-left:auto; flex-wrap:wrap; }
.ctl { display:flex; flex-direction:column; gap:5px; min-width:220px; }
.ctl-sm { min-width:110px; }
.ctl label { font-size:10.5px; letter-spacing:.09em; color:var(--tx3); font-weight:700; }
/* lectura por año */
table.lect { width:100%; border-collapse:collapse; font-size:12.5px; margin-top:10px; font-variant-numeric:tabular-nums; }
table.lect th { text-align:right; color:var(--tx3); font-weight:600; font-size:11px; letter-spacing:.04em; padding:6px 6px; border-bottom:1px solid var(--borde2); }
table.lect td { text-align:right; padding:10px 6px; border-bottom:1px solid var(--borde2); color:var(--tx); }
table.lect th:first-child, table.lect td:first-child { text-align:left; }
.dot { display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:7px; }
.lect-nota { color:var(--tx3); font-size:12px; line-height:1.5; margin-top:12px; }
.lect-nota b { color:var(--tx); }
.leyenda { display:flex; gap:14px; margin-left:auto; flex-wrap:wrap; font-size:12px; color:var(--tx2); }
.leyenda span { display:flex; align-items:center; }
/* tabla */
.btn-pri { margin-left:auto; display:flex; align-items:center; gap:7px; background:var(--acc); color:var(--bg); border:0; border-radius:10px;
  padding:9px 15px; font:inherit; font-size:13px; font-weight:650; cursor:pointer; }
.tema-claro .btn-pri { color:#fff; }
.btn-pri:hover { filter:brightness(1.08); }
.tabla-wrap { overflow:auto; max-height:620px; }
table.t { border-collapse:collapse; width:100%; font-size:13px; font-variant-numeric:tabular-nums; }
table.t th { position:sticky; top:0; background:var(--card-solid); color:var(--tx3); font-weight:600; text-align:right; padding:12px 16px;
  border-bottom:1px solid var(--borde); font-size:12px; }
table.t th:first-child, table.t td:first-child { text-align:left; }
table.t td { padding:9px 16px; text-align:right; border-bottom:1px solid var(--borde2); color:var(--tx); }
table.t tr:hover td { background:var(--acc-soft); }
table.t .tot { font-weight:700; color:var(--acc); }
.aviso { background:rgba(250,178,25,.12); color:#d99a12; border:1px solid rgba(250,178,25,.35); border-radius:10px; padding:10px 14px; margin:8px 0; font-size:13px; }
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

app.clientside_callback(
    """function(n, tema) { return n ? (tema === 'claro' ? 'oscuro' : 'claro') : (tema || 'oscuro'); }""",
    Output("tema", "data"), Input("btn-tema", "n_clicks"), State("tema", "data"))

app.clientside_callback("""function(tema) { return 'app tema-' + (tema || 'oscuro'); }""",
                        Output("app", "className"), Input("tema", "data"))


@app.callback(Output("f-mes", "value"), Input("btn-mes-todos", "n_clicks"), Input("btn-mes-nada", "n_clicks"),
              prevent_initial_call=True)
def _meses_rapidos(_a, _b):
    return list(range(1, 13)) if ctx.triggered_id == "btn-mes-todos" else []


@app.callback(Output("f-concepto", "value"), Output("f-var", "value"), Output("f-ramo", "value", allow_duplicate=True),
              Output("f-anio", "value", allow_duplicate=True), Output("f-mes", "value", allow_duplicate=True),
              Output("f-unidad", "value"), Input("btn-reset", "n_clicks"), prevent_initial_call=True)
def _reset(_n):
    _, ramos, anios = catalogos(ESTADO["df"])
    conceptos = catalogos(ESTADO["df"])[0]
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
            Input("f-anio", "value"), Input("f-mes", "value"), Input("f-unidad", "value"),
            Input("version", "data"), Input("tema", "data")]


# ---- Callback principal ---------------------------------------------------------------
@app.callback(
    Output("chips", "children"), Output("aviso", "children"), Output("fuente", "children"), Output("pie", "children"),
    Output("kpis", "children"),
    Output("t-mens", "children"), Output("g-mens", "figure"), Output("t-ramo", "children"), Output("g-ramo", "figure"),
    Output("g-mom", "figure"), Output("t-conc", "children"), Output("g-conc", "figure"),
    *[Output(f"g-v{i}", "figure") for i in range(6)], Output("ramo-leyenda", "children"), Output("tabla", "children"),
    *ENTRADAS)
def actualizar(concepto, var, ramos, anios, meses, unidad, _ver, tema):
    T = TEMAS.get(tema or "oscuro", TEMAS["oscuro"])
    df = ESTADO["df"]
    _, ramos_todos, anios_todos = catalogos(df)
    ramos, anios, meses = sorted(ramos or []), sorted(anios or []), sorted(meses or [])
    div, suf = UNIDADES[unidad]
    ratio = var in RATIOS
    lbl = VARIABLES[var]
    yu = f"{unidad} de pesos" if unidad != "Pesos" else "Pesos"
    aviso = html.Div(ESTADO["error"], className="aviso") if ESTADO["error"] else None
    fuente = f"Fuente: {ESTADO['origen']}" if ESTADO["origen"] else ""
    pie = f"PRISMA · {ESTADO['origen'] or 'sin archivo'} · actualizado {datetime.now():%d/%m/%Y %H:%M}"
    per_txt = (f"{anios[0]}–{anios[-1]}" if len(anios) > 1 else str(anios[0])) if anios else "—"
    mes_txt = "Todos" if len(meses) == 12 else (", ".join(MESES[m - 1] for m in meses) if meses else "—")
    chips = [html.Span([html.B(k), v], className="chip") for k, v in
             [("Concepto", concepto), ("Variable", lbl), ("Ramos", ", ".join(ramos) if ramos else "—"),
              ("Año", per_txt), ("Mes", mes_txt), ("En", unidad)]]
    if not (ramos and anios and meses and concepto):
        v = vacia(T)
        return (chips, aviso, fuente, pie, [], lbl, v, "Por ramo", v, v, "Comparativo de conceptos", v,
                *[v] * 6, None, html.Div("Sin datos", className="ayuda", style={"padding": "16px"}))

    # --- KPIs ---
    def kpi(variable, icono, hero=False):
        r = variable in RATIOS
        if variable in FLUJOS:
            act = serie(df, concepto, variable, ramos, anios[-1:], meses)["VALOR"].sum()
            prev_s = serie(df, concepto, variable, ramos, [anios[-1] - 1], meses)
            prev = prev_s["VALOR"].sum() if not prev_s.empty else None
            det = f"Acumulado {anios[-1]}"
        else:
            s = serie(df, concepto, variable, ramos, anios_todos, list(range(1, 13)), por=("PERIODO",))
            s = s.dropna(subset=["VALOR"]).set_index("PERIODO")["VALOR"]
            dentro = [p for p in s.index if p // 100 in anios and p % 100 in meses]
            act = prev = None
            det = "Sin dato"
            if dentro:
                p = max(dentro)
                act, prev = s.get(p), s.get(p - 100)
                det = f"Saldo al cierre de {MESES[p % 100 - 1]} {p // 100}"
        badge, aa = html.Span("sin comparativo", className="badge neu"), "AA: N/A"
        if act is not None and prev is not None and not pd.isna(prev) and prev != 0:
            dv = (act - prev) * 100 if r else (act / prev - 1) * 100
            badge = html.Span(f"{'▲' if dv >= 0 else '▼'} {abs(dv):.1f}{' pp' if r else '%'}",
                              className="badge " + ("up" if dv >= 0 else "down"))
            aa = f"AA: {fmt(prev, unidad, r)}"
        hijos = [html.Div([html.Span(ic(icono), className="ico"), VARIABLES[variable]], className="t"),
                 html.Div(fmt(act, unidad, r), className="v"),
                 html.Div([html.Span(aa), badge], className="aa"),
                 html.Div(det, className="pie-k")]
        if hero:
            s = serie(df, concepto, variable, ramos, anios, meses).sort_values("FECHA")
            f = go.Figure(go.Scatter(x=s["FECHA"], y=s["VALOR"] / div, mode="lines", fill="tozeroy",
                                     line=dict(color=T["accent"], width=2.5, shape="spline"),
                                     hovertemplate="%{x|%m/%Y}: %{y:,.1f}" + suf + "<extra></extra>"))
            f.update_traces(fillcolor=_alpha(T["accent"], 0.15))
            f.update_layout(height=120, margin=dict(l=0, r=0, t=6, b=0), paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)", showlegend=False, hovermode="x")
            f.update_xaxes(visible=False, fixedrange=True)
            f.update_yaxes(visible=False, fixedrange=True, range=[s["VALOR"].min() / div * 0.9, s["VALOR"].max() / div * 1.04]
                           if s["VALOR"].notna().any() else None)
            hijos.insert(3, html.Div([html.Div("Tendencia del periodo filtrado", className="ayuda"),
                                      dcc.Graph(figure=f, config={"displayModeBar": False}, style={"height": "120px"})],
                                     className="spark"))
        return html.Div(hijos, className="card kpi" + (" hero" if hero else ""))

    kpis = [kpi("RAM", "escudo", hero=True), kpi("PRIMA 24M", "reloj"), kpi("PR 24M", "pie"), kpi("MA", "maletin"),
            kpi("RFV MA", "sube"), kpi("CESION", "cesion"), kpi("PT", "peso")]

    # --- Monto por mes ---
    tot = serie(df, concepto, var, ramos, anios, meses).sort_values("FECHA")
    yv = tot["VALOR"] if ratio else tot["VALOR"] / div
    fig = go.Figure()
    etiquetas = [(f"{v * 100:.1f}%" if ratio else f"{v:,.1f}") if pd.notna(v) else "" for v in yv]
    etiquetas = [e if len(tot) <= (24 if not ratio else 12) else "" for e in etiquetas]
    for a in anios:
        m = tot["FECHA"].dt.year == a
        if ratio:
            fig.add_scatter(x=tot.loc[m, "FECHA"], y=yv[m], name=str(a), mode="lines+markers+text",
                            line=dict(color=color_anio(a, anios_todos, T), width=2.5), marker=dict(size=8),
                            text=[e for e, k in zip(etiquetas, m) if k], textposition="top center",
                            textfont=dict(color=T["text2"], size=10), hovertemplate="%{y:.2%}<extra>" + str(a) + "</extra>")
        else:
            fig.add_bar(x=tot.loc[m, "FECHA"], y=yv[m], name=str(a), marker_color=color_anio(a, anios_todos, T),
                        marker_cornerradius=5, text=[e for e, k in zip(etiquetas, m) if k], textposition="outside",
                        textfont=dict(color=T["text2"], size=10), cliponaxis=False,
                        hovertemplate="%{y:,.1f}" + suf + "<extra>" + str(a) + "</extra>")
    if yv.notna().any():
        prom = yv.mean()
        fig.add_hline(y=prom, line=dict(color=T["text3"], width=1.2, dash="dash"),
                      annotation_text=f"Promedio {prom * 100:.1f}%" if ratio else f"Promedio {prom:,.1f}{suf}",
                      annotation_position="right", annotation_font=dict(color=T["text"], size=11),
                      annotation_bgcolor=T["card"], annotation_bordercolor=T["linea"], annotation_borderpad=4)
    estilo(fig, T, 380, None if ratio else yu, ratio, leyenda=len(anios) > 1)
    fig.update_layout(margin=dict(r=118))
    if not ratio and yv.notna().any():
        fig.update_yaxes(range=[0, yv.max() * 1.15])
    g_mens = fig
    t_mens = f"{lbl} por mes · {concepto}"

    # --- Por ramo (barras horizontales) ---
    base = filtrar(df, concepto, var, ramos, anios, meses)
    if ratio:
        pmax = base["PERIODO"].max()
        comp = serie(df, concepto, var, ramos, anios, meses, por=("PERIODO", "RAMO"))
        comp = comp[comp["PERIODO"] == pmax][["RAMO", "VALOR"]]
        t_ramo = f"Por ramo · cierre {MESES[pmax % 100 - 1]} {pmax // 100}" if pd.notna(pmax) else "Por ramo"
    elif var in FLUJOS:
        comp = base.groupby("RAMO", as_index=False)["VALOR"].sum()
        t_ramo = f"Por ramo · acumulado {per_txt}"
    else:
        pmax = base["PERIODO"].max()
        comp = base[base["PERIODO"] == pmax].groupby("RAMO", as_index=False)["VALOR"].sum()
        t_ramo = f"Por ramo · cierre {MESES[pmax % 100 - 1]} {pmax // 100}" if pd.notna(pmax) else "Por ramo"
    comp = comp.dropna().sort_values("VALOR")
    total_c = comp["VALOR"].sum()
    if ratio:
        txt = [f"{v * 100:.1f}%" for v in comp["VALOR"]]
        xv = comp["VALOR"]
    else:
        txt = [f"{v / div:,.1f}{suf} · {v / total_c * 100:.1f}%" if total_c else "" for v in comp["VALOR"]]
        xv = comp["VALOR"] / div
    fig = go.Figure(go.Bar(y=["Ramo " + r for r in comp["RAMO"]], x=xv, orientation="h", text=txt,
                           textposition="outside", cliponaxis=False, textfont=dict(color=T["text2"], size=11),
                           marker=dict(color=[color_ramo(r, ramos_todos, T) for r in comp["RAMO"]], cornerradius=5),
                           hovertemplate="%{y}: %{text}<extra></extra>"))
    estilo(fig, T, 380, leyenda=False, ratio=ratio)
    fig.update_layout(hovermode="closest", margin=dict(l=8, r=8, t=8, b=8), bargap=0.35)
    fig.update_xaxes(showticklabels=False, showgrid=False, range=[0, (xv.max() if len(xv) else 1) * 1.6])
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)", tickfont=dict(color=T["text"], size=12))
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
    estilo(fig, T, 250, "pp" if ratio else unidad, leyenda=False, ytick=",.1f")
    g_mom = fig

    # --- Conceptos ---
    fig = go.Figure()
    for i, c in enumerate([c for c in CONCEPTOS_ORDEN if c in set(df["CONCEPTO"])]):
        s = serie(df, c, var, ramos, anios, meses).sort_values("FECHA")
        y = s["VALOR"] if ratio else s["VALOR"] / div
        col = T["ramos"][i % len(T["ramos"])]
        fig.add_scatter(x=s["FECHA"], y=y, name=c, mode="lines", line=dict(color=col, width=3.5 if c == concepto else 2),
                        hovertemplate=("%{y:.1%}" if ratio else "%{y:,.1f}" + suf))
        if len(s) and pd.notna(y.iloc[-1]):
            fig.add_annotation(x=s["FECHA"].iloc[-1], y=y.iloc[-1], xanchor="left", xshift=8, showarrow=False,
                               text=f"<b>{c}</b> {fmt(s['VALOR'].iloc[-1], unidad, ratio)}", font=dict(color=col, size=11))
    estilo(fig, T, 360, None if ratio else yu, ratio, leyenda=False)
    fig.update_layout(margin=dict(l=8, r=170, t=10, b=8))
    g_conc = fig
    t_conc = f"{lbl} por concepto"

    # --- Detalle por ramo (small multiples) ---
    peq = []
    for v in ["RAM", "PRIMA 24M", "PR 24M", "MA", "RFV MA", "CESION"]:
        r_ = v in RATIOS
        fig = go.Figure()
        for r in ramos:
            s = serie(df, concepto, v, [r], anios, meses)
            if s["VALOR"].fillna(0).abs().sum() == 0:
                continue
            fig.add_scatter(x=s["FECHA"], y=s["VALOR"] if r_ else s["VALOR"] / div, name=f"Ramo {r}", mode="lines",
                            line=dict(color=color_ramo(r, ramos_todos, T), width=2),
                            hovertemplate="%{y:.1%}" if r_ else "%{y:,.1f}" + suf)
        estilo(fig, T, 250, None, r_, leyenda=False, compacto=True)
        peq.append(fig)
    leyenda = [html.Span([html.I(className="dot", style={"background": color_ramo(r, ramos_todos, T)}), f"Ramo {r}"])
               for r in ramos]

    # --- Tabla ---
    d = filtrar(df, concepto, var, ramos, anios, meses)
    tab = d.pivot_table(index="PERIODO", columns="RAMO", values="VALOR", aggfunc="sum")
    tab.columns = [f"Ramo {c}" for c in tab.columns]
    tab["Total"] = serie(df, concepto, var, ramos, anios, meses, por=("PERIODO",)).set_index("PERIODO")["VALOR"]
    vista = tab * 100 if ratio else tab / div
    f_ = (lambda x: "N/A" if pd.isna(x) else f"{x:,.2f}%") if ratio else (lambda x: "N/A" if pd.isna(x) else f"{x:,.1f}")
    filas = [html.Tr([html.Td(f"{MESES[p % 100 - 1]} {p // 100}")] +
                     [html.Td(f_(row[c]), className="tot" if c == "Total" else None) for c in vista.columns])
             for p, row in vista.iterrows()]
    tabla = html.Table([html.Thead(html.Tr([html.Th("Mes")] + [html.Th(c + (" (%)" if ratio else f" ({unidad})"),
                                                                       className="tot" if c == "Total" else None)
                                                               for c in vista.columns])),
                        html.Tbody(filas)], className="t")

    return (chips, aviso, fuente, pie, kpis, t_mens, g_mens, t_ramo, g_ramo, g_mom, t_conc, g_conc, *peq, leyenda, tabla)


def _alpha(hex_color, a):
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


# ---- Estacionalidad -------------------------------------------------------------------
@app.callback(
    Output("t-comp", "children"), Output("a-comp", "children"), Output("g-comp", "figure"),
    Output("est-stats", "children"), Output("t-heat", "children"), Output("g-heat", "figure"),
    Output("g-ramo-est", "figure"),
    Input("f-concepto", "value"), Input("f-var", "value"), Input("f-ramo", "value"), Input("f-mes", "value"),
    Input("f-unidad", "value"), Input("est-anios", "value"), Input("est-prima", "value"),
    Input("est-ramo-anio", "value"), Input("version", "data"), Input("tema", "data"))
def estacionalidad(concepto, var, ramos, meses, unidad, anios, prima, anio_ramo, _ver, tema):
    T = TEMAS.get(tema or "oscuro", TEMAS["oscuro"])
    df = ESTADO["df"]
    _, ramos_todos, anios_todos = catalogos(df)
    ramos, meses, anios = sorted(ramos or []), sorted(meses or []), sorted(anios or [])
    lbl, lblp = VARIABLES[var], PRIMAS[prima]
    if not (ramos and meses and anios and concepto):
        v = vacia(T, "Elige al menos un año arriba y revisa los filtros")
        return "Estacionalidad vs. prima", "", v, None, "Monto por mes y año", v, v
    div, suf = UNIDADES[unidad]
    ratio = var in RATIOS
    xm = [MESES[m - 1] for m in meses]

    # Variable vs prima, año por año en la misma gráfica
    iv = indice(df, concepto, var, ramos, anios, meses)
    ip = indice(df, concepto, prima, ramos, anios, meses)
    fig = go.Figure()
    for a in anios:
        col = color_anio(a, anios_todos, T)
        fig.add_scatter(x=xm, y=iv.loc[a].values, name=f"{a} · {lbl}", legendgroup=str(a), mode="lines+markers",
                        line=dict(color=col, width=3), marker=dict(size=8, line=dict(color=T["card"], width=1.5)),
                        hovertemplate="%{y:.2f}")
        if prima != var:
            fig.add_scatter(x=xm, y=ip.loc[a].values, name=f"{a} · {lblp}", legendgroup=str(a), mode="lines+markers",
                            line=dict(color=col, width=1.8, dash="dot"),
                            marker=dict(size=7, symbol="circle-open", line=dict(width=1.8)), hovertemplate="%{y:.2f}")
    fig.add_hline(y=1, line=dict(color=T["text3"], width=1, dash="dash"),
                  annotation_text="1.00 = mes promedio", annotation_position="bottom right",
                  annotation_font=dict(color=T["text3"], size=10))
    estilo(fig, T, 400, "Índice estacional", ytick=".2f")
    fig.update_layout(legend=dict(y=1.02))
    g_comp = fig
    t_comp = f"Estacionalidad: {lbl} vs. {lblp}"
    a_comp = (f"Línea continua: {lbl} · línea punteada: {lblp}. Cada color es un año. "
              "Índice 1.10 = ese mes está 10% arriba del promedio de su año.")

    # Lectura por año
    filas = []
    for a in anios:
        v_, p_ = iv.loc[a], ip.loc[a]
        ok = v_.notna() & p_.notna()
        corr = v_[ok].corr(p_[ok]) if ok.sum() > 2 else np.nan
        pico_v = xm[int(np.nanargmax(v_.values))] if v_.notna().any() else "—"
        pico_p = xm[int(np.nanargmax(p_.values))] if p_.notna().any() else "—"
        amp = lambda s: f"{s.max() - s.min():.2f}" if s.notna().any() else "—"
        filas.append(html.Tr([html.Td([html.Span(className="dot", style={"background": color_anio(a, anios_todos, T)}), str(a)]),
                              html.Td("—" if pd.isna(corr) else f"{corr:+.2f}"),
                              html.Td(f"{pico_v} / {pico_p}"), html.Td(amp(v_)), html.Td(amp(p_))]))
    stats = [html.Table([html.Thead(html.Tr([html.Th("Año"), html.Th("Correlación"), html.Th("Mes pico"),
                                             html.Th("Amplitud var."), html.Th("Amplitud prima")])),
                         html.Tbody(filas)], className="lect"),
             html.Div(["Mes pico = mes con el índice más alto (", html.B(lbl), " / ", html.B(lblp), "). "
                       "Una reserva es un saldo y suele moverse menos que la prima del mes."], className="lect-nota")]

    # Mapa de calor
    s = serie(df, concepto, var, ramos, anios, meses, por=("ANIO", "MES"))
    piv = s.pivot(index="ANIO", columns="MES", values="VALOR").reindex(index=anios, columns=meses)
    z = piv.values * (100 if ratio else 1 / div)
    fig = go.Figure(go.Heatmap(
        z=z, x=xm, y=[str(a) for a in piv.index], colorscale=[[i / (len(T["heat"]) - 1), c] for i, c in enumerate(T["heat"])],
        text=[["" if pd.isna(v) else (f"{v:.1f}%" if ratio else f"{v:,.0f}") for v in row] for row in z],
        texttemplate="%{text}", textfont=dict(size=11), xgap=4, ygap=4, showscale=False,
        hovertemplate="%{x} %{y}: %{text}" + ("" if ratio else suf) + "<extra></extra>"))
    estilo(fig, T, 300, leyenda=False, ytick="")
    fig.update_layout(hovermode="closest")
    fig.update_yaxes(type="category", gridcolor="rgba(0,0,0,0)", tickfont=dict(color=T["text"], size=12))
    g_heat = fig
    t_heat = f"{lbl} por mes y año" + ("" if ratio else f" ({unidad.lower()})")

    # Estacionalidad por ramo en el año elegido
    fig = go.Figure()
    a_r = anio_ramo if anio_ramo in anios_todos else (anios_todos or [None])[-1]
    for r in ramos:
        ir = indice(df, concepto, var, [r], [a_r], meses)
        if ir.empty or ir.iloc[0].isna().all():
            continue
        fig.add_scatter(x=xm, y=ir.iloc[0].values, name=f"Ramo {r}", mode="lines+markers",
                        line=dict(color=color_ramo(r, ramos_todos, T), width=2.2), marker=dict(size=6),
                        hovertemplate="%{y:.2f}")
    fig.add_hline(y=1, line=dict(color=T["text3"], width=1, dash="dash"))
    estilo(fig, T, 300, "Índice", ytick=".2f")
    return t_comp, a_comp, g_comp, stats, t_heat, g_heat, fig


# ---- Descarga a Excel -----------------------------------------------------------------
@app.callback(Output("dl", "data"), Input("btn-xls", "n_clicks"),
              *[State(i.component_id, i.component_property) for i in ENTRADAS[:6]], prevent_initial_call=True)
def descargar(_n, concepto, var, ramos, anios, meses, unidad):
    df = ESTADO["df"]
    ramos, anios, meses = sorted(ramos or []), sorted(anios or []), sorted(meses or [])
    d = filtrar(df, concepto, var, ramos, anios, meses)
    tab = d.pivot_table(index="PERIODO", columns="RAMO", values="VALOR", aggfunc="sum")
    tab.columns = [f"Ramo {c}" for c in tab.columns]
    tab["Total"] = serie(df, concepto, var, ramos, anios, meses, por=("PERIODO",)).set_index("PERIODO")["VALOR"]
    base = df[df["RAMO"].isin(ramos) & df["ANIO"].isin(anios) & df["MES"].isin(meses)].drop(columns="FECHA")
    base = base.assign(VARIABLE=base["VARIABLE"].map(VARIABLES))

    def escribir(buf):
        with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
            tab.to_excel(xw, sheet_name="Mensualizacion")
            base.to_excel(xw, sheet_name="Base_filtrada", index=False)

    return dcc.send_bytes(escribir, f"PRISMA_Reservas_{datetime.now():%Y%m%d}.xlsx")


# --------------------------------------------------------------------------------------
if __name__ == "__main__":
    url = f"http://127.0.0.1:{PUERTO}"
    print(f"\nPRISMA listo en {url}  (Ctrl + C para detener)\n")
    if not os.environ.get("RFV_NO_BROWSER"):
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    app.run(debug=False, port=PUERTO, host="127.0.0.1")
