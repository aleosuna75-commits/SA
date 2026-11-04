# -*- coding: utf-8 -*-
"""
Dashboard de Proyección de Reservas · FCST 2027   (Plotly Dash)
===============================================================
Lee BD_RFV_Proyeccion (hoja BD_Montos_RRC_SONR) y muestra la mensualización,
la estacionalidad (vs. la estacionalidad de la prima) y los montos, con filtros
en el menú de la izquierda: Concepto, Variable (Reserva, Prima 24M, PR 24M, MA,
RFV MA, Cesión, PT), Ramo, Año, Mes y Unidades.

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
# 1) Paquetería: se instala sola si falta (Dash 4 o superior, por el tema oscuro)
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
    "RAM": "Reserva (monto)",
    "PRIMA 24M": "Prima 24M",
    "PR 24M": "PR 24M",
    "MA": "MA (monto afianzado)",
    "RFV MA": "RFV MA",
    "CESION": "Cesión",
    "PT": "PT (prima del mes)",
}
PRIMAS = {"PT": "Prima tomada del mes (PT)", "PRIMA 24M": "Prima 24M"}
FLUJOS = {"PT"}            # se acumulan en el año; el resto son saldos (se toma el cierre)
RATIOS = {"CESION"}        # porcentajes: promedio ponderado por la reserva

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
UNIDADES = {"Pesos": (1, ""), "Miles": (1e3, " K"), "Millones": (1e6, " M")}

# Paleta categórica fija (validada para fondo oscuro y daltonismo); el color sigue a la entidad
COL_RAMO = {"130": "#3987e5", "140": "#d95926", "150": "#199e70", "160": "#c98500", "170": "#d55181"}
COL_CONCEPTO = {"RCONT": "#3987e5", "RFV BRUTO": "#d95926", "RFV IRR": "#199e70", "RFV NETO": "#c98500"}
COL_ANIO_LISTA = ["#199e70", "#d95926", "#3987e5", "#d55181", "#9085e9"]
SEQ_AZUL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
POS, NEG = "#3987e5", "#e66767"

BG, SIDE, CARD = "#0d0d0d", "#141413", "#1a1a19"
BORDE = "rgba(255,255,255,0.10)"
TXT, TXT2, TXT3 = "#ffffff", "#c3c2b7", "#898781"
GRID = "rgba(255,255,255,0.07)"


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
    ESTADO["error"] = f"No encontré un archivo con el patrón {PATRON} en: {CARPETA}. Cárgalo desde el menú izquierdo."
    ESTADO["df"] = pd.DataFrame(columns=["CONCEPTO", "PERIODO", "VALOR", "VARIABLE", "RAMO", "ANIO", "MES", "FECHA"])


def catalogos(df):
    conceptos = list(dict.fromkeys(df["CONCEPTO"]))
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
    piv = s.pivot(index="ANIO", columns="MES", values="VALOR").reindex(columns=meses)
    prom = piv.mean(axis=1).replace(0, np.nan)
    return piv.div(prom, axis=0)


def fmt(v, unidad, ratio=False, dec=1):
    if v is None or pd.isna(v):
        return "N/A"
    if ratio:
        return f"{v * 100:,.{dec}f}%"
    div, suf = UNIDADES[unidad]
    return f"${v / div:,.{dec if unidad != 'Pesos' else 0}f}{suf}"


def color_anio(a, anios_todos):
    return COL_ANIO_LISTA[anios_todos.index(a) % len(COL_ANIO_LISTA)] if a in anios_todos else TXT2


# ---- Estilo de gráficas ---------------------------------------------------------------
GRAPH_CFG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
             "toImageButtonOptions": {"format": "png", "scale": 2}}


def estilo(fig, h=340, titulo=None, ytitle=None, ratio=False, leyenda=True, ytick=None, compacto=False):
    fig.update_layout(
        height=h, paper_bgcolor=CARD, plot_bgcolor=CARD,
        font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif', color=TXT2, size=12),
        margin=dict(l=12, r=12, t=48 if titulo else 16, b=8),
        title=dict(text=titulo, font=dict(color=TXT, size=14), x=0.015, y=0.97) if titulo else None,
        hovermode="x unified", showlegend=leyenda,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1, font=dict(color=TXT2, size=11),
                    traceorder="normal", bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor="#262624", font=dict(color=TXT), bordercolor="#3a3a37"),
        bargap=0.28,
    )
    fig.update_xaxes(showgrid=False, linecolor="#2c2c2a", tickfont=dict(color=TXT3), zeroline=False)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, tickfont=dict(color=TXT3), title=ytitle,
                     title_font=dict(color=TXT3, size=11),
                     tickformat=ytick or (".0%" if ratio else ",.0f"))
    _meses_es(fig, 4 if compacto else 15)
    if compacto:
        fig.update_layout(legend=dict(yanchor="top", y=-0.16, xanchor="center", x=0.5, font=dict(size=10)),
                          margin=dict(l=8, r=8, t=40, b=8))
        fig.update_xaxes(tickangle=0)
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
        fig.update_xaxes(tickvals=vals, ticktext=[f"{MESES[f.month - 1]}<br>{f.year}" for f in vals])


def vacia(msg="Selecciona al menos un ramo, un año y un mes", h=340):
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False, font=dict(color=TXT3, size=13))
    fig.update_layout(height=h, paper_bgcolor=CARD, plot_bgcolor=CARD, margin=dict(l=10, r=10, t=10, b=10))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def tarjeta(id_, h=340):
    return html.Div(dcc.Graph(id=id_, config=GRAPH_CFG, style={"height": f"{h}px"}), className="card graf")


# ---- Layout ---------------------------------------------------------------------------
conceptos0, ramos0, anios0 = catalogos(ESTADO["df"])


def bloque(titulo, *hijos):
    return html.Div([html.Div(titulo, className="side-lbl"), *hijos], className="side-blk")


sidebar = html.Aside([
    html.Div([html.Span("▤", className="logo"), html.Div([html.Div("Reservas", className="brand"),
                                                         html.Div("FCST 2027", className="brand-sub")])],
             className="brand-row"),
    bloque("Concepto", dcc.RadioItems(id="f-concepto", options=conceptos0,
                                      value="RFV NETO" if "RFV NETO" in conceptos0 else (conceptos0 or [None])[0],
                                      className="lista")),
    bloque("Variable", dcc.RadioItems(id="f-var", options=[{"label": v, "value": k} for k, v in VARIABLES.items()],
                                      value="RAM", className="lista")),
    bloque("Ramo", dcc.Checklist(id="f-ramo", options=[{"label": f"Ramo {r}", "value": r} for r in ramos0],
                                 value=ramos0, className="pills")),
    bloque("Año", dcc.Checklist(id="f-anio", options=anios0, value=anios0[-1:], className="pills")),
    bloque("Mes", dcc.Checklist(id="f-mes", options=[{"label": m, "value": i + 1} for i, m in enumerate(MESES)],
                                value=list(range(1, 13)), className="pills meses"),
           html.Div([html.Button("Todos", id="btn-mes-todos", className="mini"),
                     html.Button("Ninguno", id="btn-mes-nada", className="mini")], className="mini-row")),
    bloque("Unidades", dcc.RadioItems(id="f-unidad", options=list(UNIDADES), value="Millones", className="pills")),
    bloque("Archivo", dcc.Upload(id="upload", children=html.Div(["Arrastra o ", html.B("elige"), " otra versión"]),
                                 className="upload", accept=".xlsx,.xlsm,.xls"),
           html.Div(id="fuente", className="fuente")),
], className="sidebar")

NAV = [("mens", "Mensualización"), ("est", "Estacionalidad"), ("conc", "Conceptos"),
       ("vars", "Variables por ramo"), ("tabla-sec", "Tabla")]

main = html.Main([
    html.Header([
        html.Div([html.H1("Proyección de Reservas · FCST 2027"),
                  html.Div(id="chips", className="chips")]),
        html.Nav([html.A(t, href=f"#{i}") for i, t in NAV], className="secs"),
    ], className="top"),
    html.Div(id="aviso"),
    html.Div(id="kpis", className="grid kpis"),

    html.Section([
        html.Div([html.H2("Mensualización"), html.Span(id="sub-mens", className="sub")], className="sec-head"),
        html.Div([tarjeta("g-mens", 420), tarjeta("g-donut", 420)], className="grid g-2-1"),
        tarjeta("g-mom", 300),
    ], id="mens", className="bloque"),

    html.Section([
        html.Div([
            html.H2("Estacionalidad"), html.Span("índice = mes ÷ promedio de su año", className="sub"),
            html.Div([
                html.Div([html.Label("AÑOS"),
                          dcc.Dropdown(id="est-anios", options=[{"label": str(a), "value": a} for a in anios0],
                                       value=anios0, multi=True, clearable=False, searchable=False,
                                       placeholder="Elige años",
                                       labels={"select_all": "Seleccionar todos", "deselect_all": "Quitar todos",
                                               "selected_count": "{num_selected} años"})], className="ctl"),
                html.Div([html.Label("PRIMA A COMPARAR"),
                          dcc.Dropdown(id="est-prima", options=[{"label": v, "value": k} for k, v in PRIMAS.items()],
                                       value="PT", clearable=False, searchable=False)], className="ctl"),
            ], className="ctls"),
        ], className="sec-head"),
        html.Div([tarjeta("g-heat", 340), tarjeta("g-idx", 340)], className="grid g-2"),
        html.H3("Estacionalidad vs. prima", className="med"),
        html.Div([tarjeta("g-idx-var", 330), tarjeta("g-idx-prima", 330)], className="grid g-2"),
        html.Div([tarjeta("g-comp", 340), html.Div(id="comp-kpis", className="card comp")], className="grid g-2-1"),
        tarjeta("g-idx-ramo", 330),
    ], id="est", className="bloque"),

    html.Section([
        html.Div([html.H2("Conceptos"), html.Span("RCONT · RFV BRUTO · RFV IRR · RFV NETO", className="sub")],
                 className="sec-head"),
        tarjeta("g-conc", 400),
    ], id="conc", className="bloque"),

    html.Section([
        html.Div([html.H2("Variables por ramo"), html.Span(id="sub-vars", className="sub")], className="sec-head"),
        html.Div([tarjeta(f"g-v{i}", 310) for i in range(6)], className="grid g-3"),
    ], id="vars", className="bloque"),

    html.Section([
        html.Div([html.H2("Tabla mensualizada"), html.Span(id="sub-tabla", className="sub"),
                  html.Button("⬇ Descargar a Excel", id="btn-xls", className="btn")], className="sec-head"),
        html.Div(id="tabla", className="card tabla-wrap"),
        dcc.Download(id="dl"),
    ], id="tabla-sec", className="bloque"),
], className="main")

app = Dash(__name__, title="Reservas FCST 2027", update_title=None)
app.layout = html.Div([dcc.Store(id="version", data=0), sidebar, main], className="app")

app.index_string = """<!DOCTYPE html>
<html lang="es"><head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>
:root { color-scheme: dark;
  --Dash-Fill-Inverse-Strong:#1f1f1d; --Dash-Fill-Interactive-Strong:#3987e5; --Dash-Fill-Interactive-Weak:rgba(57,135,229,.12);
  --Dash-Fill-Primary-Hover:rgba(255,255,255,.06); --Dash-Fill-Primary-Active:rgba(57,135,229,.18);
  --Dash-Fill-Disabled:rgba(255,255,255,.06); --Dash-Stroke-Strong:rgba(255,255,255,.22); --Dash-Stroke-Weak:rgba(255,255,255,.10);
  --Dash-Text-Primary:#ffffff; --Dash-Text-Strong:#ffffff; --Dash-Text-Weak:#c3c2b7; --Dash-Text-Disabled:#898781;
  --Dash-Shading-Strong:rgba(0,0,0,.6); --Dash-Shading-Weak:rgba(0,0,0,.4); }
* { box-sizing:border-box; }
html { scroll-behavior:smooth; }
body { margin:0; background:#0d0d0d; color:#fff; font-family:system-ui,-apple-system,"Segoe UI",sans-serif; }
.app { display:flex; min-height:100vh; }
/* --- menú izquierdo --- */
.sidebar { position:sticky; top:0; height:100vh; overflow-y:auto; width:268px; flex:0 0 268px; background:#141413;
  border-right:1px solid rgba(255,255,255,.08); padding:20px 18px 28px; }
.brand-row { display:flex; gap:10px; align-items:center; margin-bottom:14px; }
.logo { width:34px; height:34px; border-radius:9px; background:rgba(57,135,229,.18); color:#9ec5f4; display:inline-flex;
  align-items:center; justify-content:center; font-size:18px; }
.brand { font-weight:700; font-size:16px; } .brand-sub { color:#898781; font-size:12px; }
.side-blk { padding:14px 0 12px; border-top:1px solid rgba(255,255,255,.07); }
.side-lbl { font-size:11px; font-weight:650; letter-spacing:.08em; text-transform:uppercase; color:#9ec5f4; margin-bottom:9px; }
.lista label { display:flex !important; align-items:center; gap:8px; padding:5px 8px; border-radius:7px; color:#c3c2b7;
  font-size:13px; cursor:pointer; margin:1px 0; }
.lista label:hover { background:rgba(255,255,255,.05); }
.lista label:has(input:checked) { background:rgba(57,135,229,.16); color:#fff; }
.lista input { accent-color:#3987e5; margin:0; }
.pills { display:flex; flex-wrap:wrap; gap:6px; }
.pills label { display:inline-flex !important; align-items:center; padding:5px 11px; border-radius:999px; font-size:12.5px;
  color:#c3c2b7; border:1px solid rgba(255,255,255,.12); cursor:pointer; user-select:none; margin:0; }
.pills label:hover { background:rgba(255,255,255,.06); }
.pills label:has(input:checked) { background:rgba(57,135,229,.20); border-color:rgba(57,135,229,.55); color:#fff; }
.pills input { position:absolute; opacity:0; width:0; height:0; }
.pills.meses label { width:calc(25% - 5px); justify-content:center; padding:5px 0; }
.mini-row { display:flex; gap:6px; margin-top:8px; }
.mini { background:none; border:1px solid rgba(255,255,255,.12); color:#898781; border-radius:6px; font-size:11.5px;
  padding:3px 9px; cursor:pointer; } .mini:hover { color:#fff; }
.upload { border:1px dashed rgba(255,255,255,.2); border-radius:9px; padding:10px; text-align:center; font-size:12px;
  color:#898781; cursor:pointer; } .upload:hover { border-color:#3987e5; color:#c3c2b7; }
.fuente { color:#898781; font-size:11.5px; margin-top:8px; word-break:break-all; }
/* --- contenido --- */
.main { flex:1; min-width:0; padding:0 28px 40px; }
header.top { position:sticky; top:0; z-index:20; background:rgba(13,13,13,.94); backdrop-filter:blur(4px); display:flex;
  align-items:center; gap:14px; flex-wrap:wrap; padding:16px 0 12px; border-bottom:1px solid #2c2c2a; margin-bottom:18px; }
h1 { font-size:20px; font-weight:650; margin:0 0 6px; }
.chips { display:flex; gap:6px; flex-wrap:wrap; }
.chip { font-size:11.5px; color:#c3c2b7; border:1px solid rgba(255,255,255,.12); border-radius:999px; padding:2px 9px; }
nav.secs { display:flex; gap:4px; margin-left:auto; flex-wrap:wrap; }
nav.secs a { color:#c3c2b7; text-decoration:none; font-size:12.5px; padding:5px 11px; border-radius:999px; }
nav.secs a:hover { background:rgba(255,255,255,.06); color:#fff; }
section.bloque { margin-top:30px; scroll-margin-top:90px; }
.sec-head { display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:12px; }
.sec-head h2 { font-size:17px; font-weight:650; margin:0; }
.sub { color:#898781; font-size:12.5px; }
h3.med { font-size:12.5px; font-weight:650; color:#9ec5f4; letter-spacing:.06em; text-transform:uppercase; margin:20px 0 10px; }
.grid { display:grid; gap:14px; margin-bottom:14px; }
.kpis { grid-template-columns:repeat(7,minmax(0,1fr)); }
@media (max-width:1500px) { .kpis { grid-template-columns:repeat(4,minmax(0,1fr)); } }
.kpi .v { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.g-2 { grid-template-columns:1fr 1fr; } .g-2-1 { grid-template-columns:2fr 1fr; } .g-3 { grid-template-columns:repeat(3,1fr); }
@media (max-width:1250px) { .g-2,.g-2-1,.g-3 { grid-template-columns:1fr; } }
.card { background:#1a1a19; border:1px solid rgba(255,255,255,.10); border-radius:12px; }
.graf { padding:6px; overflow:hidden; }
.kpi { padding:15px 17px; }
.kpi .t { color:#c3c2b7; font-size:12px; margin-bottom:8px; display:flex; align-items:center; gap:7px; }
.kpi .t i { width:22px; height:22px; border-radius:6px; display:inline-flex; align-items:center; justify-content:center;
  font-style:normal; font-size:12px; background:rgba(57,135,229,.16); color:#9ec5f4; }
.kpi .v { font-size:clamp(17px,1.45vw,24px); font-weight:650; letter-spacing:-.02em; }
.kpi .d { font-size:12px; margin-top:7px; color:#898781; }
b.up,b.down,b.neu { font-weight:600; padding:2px 7px; border-radius:999px; font-size:11.5px; margin-right:4px; }
.up { color:#7dd87d; background:rgba(12,163,12,.14); } .down { color:#f09a9a; background:rgba(208,59,59,.16); }
.neu { color:#898781; background:rgba(137,135,129,.15); }
.ctls { display:flex; gap:12px; margin-left:auto; flex-wrap:wrap; }
.ctl { display:flex; flex-direction:column; gap:4px; min-width:230px; }
.ctl label { font-size:10.5px; letter-spacing:.08em; color:#898781; font-weight:650; }
.comp { padding:18px 20px; display:flex; flex-direction:column; gap:14px; justify-content:center; }
.comp .row { display:flex; justify-content:space-between; align-items:baseline; border-bottom:1px solid rgba(255,255,255,.07);
  padding-bottom:10px; } .comp .row:last-child { border:0; }
.comp .k { color:#c3c2b7; font-size:12.5px; } .comp .n { font-size:20px; font-weight:650; }
.comp .note { color:#898781; font-size:12px; line-height:1.45; }
.btn { margin-left:auto; background:rgba(57,135,229,.16); color:#9ec5f4; border:1px solid rgba(57,135,229,.4);
  border-radius:8px; padding:7px 14px; font-size:12.5px; cursor:pointer; } .btn:hover { background:rgba(57,135,229,.28); }
.tabla-wrap { overflow:auto; max-height:640px; }
table.t { border-collapse:collapse; width:100%; font-size:12.5px; font-variant-numeric:tabular-nums; }
table.t th { position:sticky; top:0; background:#222220; color:#c3c2b7; font-weight:600; text-align:right; padding:9px 14px;
  border-bottom:1px solid rgba(255,255,255,.12); }
table.t th:first-child, table.t td:first-child { text-align:left; }
table.t td { padding:7px 14px; text-align:right; border-bottom:1px solid rgba(255,255,255,.05); color:#e9e8e3; }
table.t tr:hover td { background:rgba(255,255,255,.03); }
table.t td.tot, table.t th.tot { font-weight:650; color:#fff; background:rgba(57,135,229,.07); }
.aviso { background:rgba(250,178,25,.12); color:#fab219; border:1px solid rgba(250,178,25,.3); border-radius:10px;
  padding:10px 14px; margin-bottom:14px; font-size:13px; }
</style></head>
<body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>"""


# ---- Callbacks ------------------------------------------------------------------------
@app.callback(Output("f-mes", "value"), Input("btn-mes-todos", "n_clicks"), Input("btn-mes-nada", "n_clicks"),
              prevent_initial_call=True)
def _meses_rapidos(_a, _b):
    return list(range(1, 13)) if ctx.triggered_id == "btn-mes-todos" else []


@app.callback(Output("version", "data"), Output("f-concepto", "options"), Output("f-ramo", "options"),
              Output("f-ramo", "value"), Output("f-anio", "options"), Output("f-anio", "value"),
              Output("est-anios", "options"), Output("est-anios", "value"),
              Input("upload", "contents"), State("upload", "filename"), State("version", "data"),
              prevent_initial_call=True)
def _subir(contents, nombre, ver):
    if not contents:
        return (no_update,) * 8
    try:
        df = cargar(base64.b64decode(contents.split(",", 1)[1]))
    except Exception as e:  # archivo con otro formato
        ESTADO["error"] = f"No pude leer {nombre}: {e}"
        return (ver + 1,) + (no_update,) * 7
    ESTADO.update(df=df, origen=nombre, error="")
    conceptos, ramos, anios = catalogos(df)
    return (ver + 1, conceptos, [{"label": f"Ramo {r}", "value": r} for r in ramos], ramos, anios, anios[-1:],
            [{"label": str(a), "value": a} for a in anios], anios)


ENTRADAS = [Input("f-concepto", "value"), Input("f-var", "value"), Input("f-ramo", "value"),
            Input("f-anio", "value"), Input("f-mes", "value"), Input("f-unidad", "value"), Input("version", "data")]


@app.callback(
    Output("chips", "children"), Output("aviso", "children"), Output("fuente", "children"), Output("kpis", "children"),
    Output("sub-mens", "children"), Output("g-mens", "figure"), Output("g-donut", "figure"), Output("g-mom", "figure"),
    Output("g-conc", "figure"), Output("sub-vars", "children"),
    *[Output(f"g-v{i}", "figure") for i in range(6)],
    Output("sub-tabla", "children"), Output("tabla", "children"),
    *ENTRADAS)
def actualizar(concepto, var, ramos, anios, meses, unidad, _ver):
    df = ESTADO["df"]
    ramos, anios, meses = sorted(ramos or []), sorted(anios or []), sorted(meses or [])
    div, suf = UNIDADES[unidad]
    ratio = var in RATIOS
    lbl = VARIABLES[var]
    aviso = html.Div(ESTADO["error"], className="aviso") if ESTADO["error"] else None
    fuente = f"Fuente: {ESTADO['origen']}" if ESTADO["origen"] else ""
    per_txt = (f"{anios[0]}–{anios[-1]}" if len(anios) > 1 else str(anios[0])) if anios else "—"
    chips = [html.Span(t, className="chip") for t in
             [concepto, lbl, "Ramos " + (", ".join(ramos) if ramos else "—"), per_txt, unidad]]
    if not (ramos and anios and meses and concepto):
        v = vacia()
        return (chips, aviso, fuente, [], "", v, v, v, v, "", *[v] * 6, "", html.Div("Sin datos", className="sub"))

    todos = sorted(df["ANIO"].unique())
    yu = f"{unidad} MXN"

    # --- KPIs ---
    def kpi(variable, icono):
        r = variable in RATIOS
        if variable in FLUJOS:
            act = serie(df, concepto, variable, ramos, anios[-1:], meses)["VALOR"].sum()
            prev_s = serie(df, concepto, variable, ramos, [anios[-1] - 1], meses)
            prev = prev_s["VALOR"].sum() if not prev_s.empty else None
            det = f"Acumulado {anios[-1]}"
        else:
            s = serie(df, concepto, variable, ramos, todos, list(range(1, 13)), por=("PERIODO",))
            s = s.dropna(subset=["VALOR"]).set_index("PERIODO")["VALOR"]
            dentro = [p for p in s.index if p // 100 in anios and p % 100 in meses]
            if not dentro:
                act = prev = None
                det = "Sin dato"
            else:
                p = max(dentro)
                act, prev = s.get(p), s.get(p - 100)
                det = f"Cierre {MESES[p % 100 - 1]} {p // 100}"
        badge = html.B("s/c", className="neu")
        if act is not None and prev not in (None, 0) and not pd.isna(prev):
            dv = (act - prev) * 100 if r else (act / prev - 1) * 100
            badge = html.B(f"{'+' if dv >= 0 else '−'}{abs(dv):.1f}{' pp' if r else '%'}",
                           className="up" if dv >= 0 else "down")
        corto = {"MA": "MA", "PT": "PT del mes", "RAM": "Reserva"}.get(variable, VARIABLES[variable])
        return html.Div([html.Div([html.I(icono), corto], className="t"),
                         html.Div(fmt(act, unidad, r), className="v"),
                         html.Div([badge, f"vs año ant. · {det}"], className="d")], className="card kpi")

    kpis = [kpi(v, i) for v, i in [("RAM", "◆"), ("PRIMA 24M", "◷"), ("PR 24M", "◔"), ("MA", "▣"),
                                    ("RFV MA", "◈"), ("CESION", "⇄"), ("PT", "＄")]]

    # --- Mensualización ---
    fig = go.Figure()
    tot = serie(df, concepto, var, ramos, anios, meses)
    if ratio:
        for r in ramos:
            s = serie(df, concepto, var, [r], anios, meses)
            fig.add_scatter(x=s["FECHA"], y=s["VALOR"], name=f"Ramo {r}", mode="lines+markers",
                            line=dict(color=COL_RAMO.get(r), width=2), marker=dict(size=7),
                            hovertemplate="%{y:.1%}")
        fig.add_scatter(x=tot["FECHA"], y=tot["VALOR"], name="Total ponderado", mode="lines",
                        line=dict(color=TXT, width=2, dash="dot"), hovertemplate="%{y:.1%}")
    else:
        for r in ramos:
            s = serie(df, concepto, var, [r], anios, meses)
            fig.add_bar(x=s["FECHA"], y=s["VALOR"] / div, name=f"Ramo {r}", marker_color=COL_RAMO.get(r),
                        marker_line=dict(color=CARD, width=1), hovertemplate="%{y:,.1f}" + suf)
        fig.add_scatter(x=tot["FECHA"], y=tot["VALOR"] / div, mode="text", showlegend=False, name="Total",
                        text=[f"{v:,.0f}" if len(tot) <= 15 else "" for v in tot["VALOR"] / div],
                        textposition="top center", textfont=dict(color=TXT2, size=10),
                        hovertemplate="<b>Total %{y:,.1f}" + suf + "</b>")
        fig.update_layout(barmode="stack")
    estilo(fig, 420, f"{lbl} mensual por ramo", None if ratio else yu, ratio)
    g_mens = fig

    base = filtrar(df, concepto, "RAM" if ratio else var, ramos, anios, meses)
    if var in FLUJOS:
        comp, sub = base.groupby("RAMO", as_index=False)["VALOR"].sum(), "Acumulado"
    else:
        pmax = base["PERIODO"].max()
        comp = base[base["PERIODO"] == pmax].groupby("RAMO", as_index=False)["VALOR"].sum()
        sub = f"Cierre {MESES[pmax % 100 - 1]} {pmax // 100}" if pd.notna(pmax) else ""
    comp = comp[comp["VALOR"] > 0]
    fig = go.Figure(go.Pie(labels=["Ramo " + r for r in comp["RAMO"]], values=comp["VALOR"] / div, hole=0.64,
                           marker=dict(colors=[COL_RAMO.get(r) for r in comp["RAMO"]], line=dict(color=CARD, width=2)),
                           sort=False, textinfo="percent", textposition="inside", textfont=dict(color="#fff"),
                           insidetextorientation="horizontal",
                           hovertemplate="%{label}: %{value:,.1f}" + suf + " (%{percent})<extra></extra>"))
    fig.add_annotation(text=f"<b>{fmt(comp['VALOR'].sum(), unidad)}</b><br><span style='font-size:11px;color:{TXT3}'>"
                            f"{sub}</span>", showarrow=False, font=dict(color=TXT, size=17))
    estilo(fig, 420, "Composición por ramo" + (" · reserva" if ratio else ""))
    fig.update_layout(hovermode="closest", legend=dict(orientation="h", y=-0.08, x=0.5, xanchor="center", yanchor="top"))
    g_donut = fig

    t = tot.sort_values("FECHA").copy()
    t["DELTA"] = t["VALOR"].diff() * (100 if ratio else 1 / div)
    fig = go.Figure(go.Bar(x=t["FECHA"], y=t["DELTA"], name="Variación",
                           marker_color=[POS if v >= 0 else NEG for v in t["DELTA"].fillna(0)],
                           hovertemplate=("%{y:+.2f} pp" if ratio else "%{y:+,.1f}" + suf) + "<extra></extra>"))
    estilo(fig, 300, f"Variación mes contra mes · {lbl}", "pp" if ratio else unidad, leyenda=False, ytick=",.1f")
    g_mom = fig

    # --- Conceptos ---
    fig = go.Figure()
    for c in [c for c in COL_CONCEPTO if c in set(df["CONCEPTO"])]:
        s = serie(df, c, var, ramos, anios, meses)
        fig.add_scatter(x=s["FECHA"], y=s["VALOR"] if ratio else s["VALOR"] / div, name=c, mode="lines+markers",
                        line=dict(color=COL_CONCEPTO[c], width=3 if c == concepto else 2), marker=dict(size=6),
                        hovertemplate="%{y:.1%}" if ratio else "%{y:,.1f}" + suf)
    estilo(fig, 400, f"{lbl} por concepto", None if ratio else yu, ratio)
    g_conc = fig

    # --- Variables por ramo (small multiples) ---
    peq = []
    for v in ["RAM", "PRIMA 24M", "PR 24M", "MA", "RFV MA", "CESION"]:
        r_ = v in RATIOS
        fig = go.Figure()
        for r in ramos:
            s = serie(df, concepto, v, [r], anios, meses)
            if s["VALOR"].fillna(0).abs().sum() == 0:
                continue
            fig.add_scatter(x=s["FECHA"], y=s["VALOR"] if r_ else s["VALOR"] / div, name=f"Ramo {r}", mode="lines",
                            line=dict(color=COL_RAMO.get(r), width=2),
                            hovertemplate="%{y:.1%}" if r_ else "%{y:,.1f}" + suf)
        estilo(fig, 310, VARIABLES[v], None if r_ else yu, r_, compacto=True)
        peq.append(fig)

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
    tabla = html.Table([html.Thead(html.Tr([html.Th("Mes")] + [html.Th(c, className="tot" if c == "Total" else None)
                                                               for c in vista.columns])),
                        html.Tbody(filas)], className="t")

    return (chips, aviso, fuente, kpis,
            f"{concepto} · {lbl} · {'%' if ratio else yu}", g_mens, g_donut, g_mom,
            g_conc, f"Concepto {concepto} · Cesión en % (total ponderado por reserva)", *peq,
            f"{lbl} · {concepto} · {'%' if ratio else yu}" + (" · total ponderado" if ratio else ""), tabla)


@app.callback(
    Output("g-heat", "figure"), Output("g-idx", "figure"), Output("g-idx-var", "figure"),
    Output("g-idx-prima", "figure"), Output("g-comp", "figure"), Output("comp-kpis", "children"),
    Output("g-idx-ramo", "figure"),
    Input("f-concepto", "value"), Input("f-var", "value"), Input("f-ramo", "value"), Input("f-mes", "value"),
    Input("f-unidad", "value"), Input("est-anios", "value"), Input("est-prima", "value"), Input("version", "data"))
def estacionalidad(concepto, var, ramos, meses, unidad, anios, prima, _ver):
    df = ESTADO["df"]
    ramos, meses, anios = sorted(ramos or []), sorted(meses or []), sorted(anios or [])
    if not (ramos and meses and anios and concepto):
        v = vacia("Selecciona ramos, meses y al menos un año")
        return v, v, v, v, v, [], v
    div, suf = UNIDADES[unidad]
    ratio = var in RATIOS
    lbl, lblp = VARIABLES[var], PRIMAS[prima]
    todos = sorted(int(a) for a in df["ANIO"].unique())
    xm = [MESES[m - 1] for m in meses]
    rango_txt = ", ".join(map(str, anios))

    # Mapa de calor
    s = serie(df, concepto, var, ramos, anios, meses, por=("ANIO", "MES"))
    piv = s.pivot(index="ANIO", columns="MES", values="VALOR").reindex(columns=meses)
    z = piv.values * (100 if ratio else 1 / div)
    fig = go.Figure(go.Heatmap(
        z=z, x=xm, y=[str(a) for a in piv.index],
        colorscale=[[i / (len(SEQ_AZUL) - 1), c] for i, c in enumerate(SEQ_AZUL)],
        text=[["" if pd.isna(v) else (f"{v:.1f}%" if ratio else f"{v:,.0f}") for v in row] for row in z],
        texttemplate="%{text}", textfont=dict(size=10), xgap=3, ygap=3,
        hovertemplate="%{y} %{x}: %{text}" + ("" if ratio else suf) + "<extra></extra>",
        colorbar=dict(thickness=8, outlinewidth=0, tickfont=dict(color=TXT3))))
    estilo(fig, 340, f"Mapa de calor año × mes · {lbl}", leyenda=False, ytick="")
    fig.update_layout(hovermode="closest")
    fig.update_yaxes(type="category", gridcolor=CARD)
    g_heat = fig

    # Índices
    iv = indice(df, concepto, var, ramos, anios, meses)
    ip = indice(df, concepto, prima, ramos, anios, meses)

    def fig_idx(piv_idx, titulo, h=340, rango=None):
        f = go.Figure()
        for a in piv_idx.index:
            f.add_scatter(x=xm, y=piv_idx.loc[a].values, name=str(a), mode="lines+markers",
                          line=dict(color=color_anio(a, todos), width=2.5 if a == max(anios) else 2),
                          marker=dict(size=7), hovertemplate="%{y:.3f}")
        f.add_hline(y=1, line=dict(color=TXT3, width=1, dash="dash"))
        estilo(f, h, titulo, "Índice", ytick=".2f")
        if rango:
            f.update_yaxes(range=rango)
        return f

    g_idx = fig_idx(iv, f"Índice estacional · {lbl} · {rango_txt}")
    lo = np.nanmin([np.nanmin(iv.values) if iv.size else 1, np.nanmin(ip.values) if ip.size else 1])
    hi = np.nanmax([np.nanmax(iv.values) if iv.size else 1, np.nanmax(ip.values) if ip.size else 1])
    pad = (hi - lo) * 0.08 if np.isfinite(hi - lo) and hi > lo else 0.1
    rango = [lo - pad, hi + pad] if np.isfinite(lo) and np.isfinite(hi) else None
    g_iv = fig_idx(iv, f"{lbl} · índice estacional", 330, rango)
    g_ip = fig_idx(ip, f"{lblp} · índice estacional", 330, rango)

    # Perfil promedio de los años elegidos: variable vs prima
    pv, pp = iv.mean(axis=0), ip.mean(axis=0)
    fig = go.Figure()
    fig.add_bar(x=xm, y=pp.values, name=lblp, marker_color="#5f6b84", marker_line=dict(color=CARD, width=1),
                hovertemplate="%{y:.3f}")
    fig.add_scatter(x=xm, y=pv.values, name=lbl, mode="lines+markers", line=dict(color="#3987e5", width=3),
                    marker=dict(size=8, line=dict(color=CARD, width=2)), hovertemplate="%{y:.3f}")
    fig.add_hline(y=1, line=dict(color=TXT3, width=1, dash="dash"))
    titulo = f"Perfil estacional {'promedio ' + rango_txt if len(anios) > 1 else rango_txt}: {lbl} vs. prima"
    estilo(fig, 340, titulo, "Índice", ytick=".2f")
    g_comp = fig

    ok = pv.notna() & pp.notna()
    corr = pv[ok].corr(pp[ok]) if ok.sum() > 2 else np.nan
    amp_v = (pv.max() - pv.min()) if pv.notna().any() else np.nan
    amp_p = (pp.max() - pp.min()) if pp.notna().any() else np.nan
    mx_v = xm[int(np.nanargmax(pv.values))] if pv.notna().any() else "—"
    mx_p = xm[int(np.nanargmax(pp.values))] if pp.notna().any() else "—"

    def fila(k, n):
        return html.Div([html.Span(k, className="k"), html.Span(n, className="n")], className="row")

    comp_kpis = [
        fila("Correlación de perfiles", "N/A" if pd.isna(corr) else f"{corr:+.2f}"),
        fila(f"Amplitud {lbl}", "N/A" if pd.isna(amp_v) else f"{amp_v:.2f}"),
        fila(f"Amplitud {lblp}", "N/A" if pd.isna(amp_p) else f"{amp_p:.2f}"),
        fila("Mes pico (variable / prima)", f"{mx_v} / {mx_p}"),
        html.Div("Correlación cercana a +1: la variable sigue el patrón mensual de la prima. Amplitud = índice máximo − "
                 "mínimo; una reserva de saldo suele ser más estable que la prima mensual.", className="note"),
    ]

    # Índice por ramo (perfil promedio de los años elegidos)
    fig = go.Figure()
    for r in ramos:
        ir = indice(df, concepto, var, [r], anios, meses)
        if ir.dropna(how="all").empty:
            continue
        prof = ir.mean(axis=0)
        if prof.isna().all():
            continue
        fig.add_scatter(x=xm, y=prof.values, name=f"Ramo {r}", mode="lines+markers",
                        line=dict(color=COL_RAMO.get(r), width=2), marker=dict(size=7), hovertemplate="%{y:.3f}")
    fig.add_hline(y=1, line=dict(color=TXT3, width=1, dash="dash"))
    estilo(fig, 330, f"Índice estacional por ramo · {lbl} · "
                     f"{'promedio ' + rango_txt if len(anios) > 1 else rango_txt}", "Índice", ytick=".2f")
    return g_heat, g_idx, g_iv, g_ip, g_comp, comp_kpis, fig


@app.callback(Output("dl", "data"), Input("btn-xls", "n_clicks"), *[State(i.component_id, i.component_property)
                                                                     for i in ENTRADAS[:6]], prevent_initial_call=True)
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

    return dcc.send_bytes(escribir, f"Dashboard_Reservas_{datetime.now():%Y%m%d}.xlsx")


# --------------------------------------------------------------------------------------
if __name__ == "__main__":
    url = f"http://127.0.0.1:{PUERTO}"
    print(f"\nDashboard listo en {url}  (Ctrl + C para detener)\n")
    if not os.environ.get("RFV_NO_BROWSER"):
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    app.run(debug=False, port=PUERTO, host="127.0.0.1")
