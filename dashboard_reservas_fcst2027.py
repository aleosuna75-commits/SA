# -*- coding: utf-8 -*-
"""
Dashboard de Proyección de Reservas · FCST 2027
================================================
Lee BD_RFV_Proyeccion (hoja BD_Montos_RRC_SONR) y muestra la mensualización,
la estacionalidad y los montos, con filtros en el menú de la izquierda:
Concepto, Variable (Reserva, PT, Prima 24M, PR 24M, MA, RFV MA, Cesión), Ramo, Año y Mes.

CÓMO EJECUTARLO DESDE VS CODE
    1) Abre este archivo en VS Code.
    2) Dale "Run Python File" (▶ arriba a la derecha) o en la terminal:
           python dashboard_reservas_fcst2027.py
    3) La primera vez instala solo los paquetes que falten (streamlit, plotly,
       pandas, openpyxl, xlsxwriter) y abre el dashboard en el navegador
       (http://localhost:8501). Para detenerlo: Ctrl + C en la terminal.
"""

import importlib.util
import os
import subprocess
import sys

# --------------------------------------------------------------------------------------
# 1) Paquetería: se instala sola si falta
# --------------------------------------------------------------------------------------
_PAQUETES = {  # módulo -> paquete de pip
    "streamlit": "streamlit",
    "plotly": "plotly",
    "pandas": "pandas",
    "openpyxl": "openpyxl",
    "xlsxwriter": "xlsxwriter",
}
_faltan = [pip for mod, pip in _PAQUETES.items() if importlib.util.find_spec(mod) is None]
if _faltan:
    print(f"Instalando paquetes faltantes: {', '.join(_faltan)} ...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", *_faltan])


# --------------------------------------------------------------------------------------
# 2) Si se corre con "python archivo.py", se relanza con Streamlit automáticamente
# --------------------------------------------------------------------------------------
def _dentro_de_streamlit() -> bool:
    try:
        from streamlit import runtime
        return runtime.exists()
    except Exception:
        return False


if __name__ == "__main__" and not _dentro_de_streamlit():
    sys.exit(subprocess.call([
        sys.executable, "-m", "streamlit", "run", os.path.abspath(__file__),
        "--theme.base", "dark",
        "--browser.gatherUsageStats", "false",
    ]))

# --------------------------------------------------------------------------------------
# 3) App
# --------------------------------------------------------------------------------------
import glob
import io
import re
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ---- Ruta del archivo -----------------------------------------------------------------
CARPETA = (r"C:\Users\asunad\OneDrive - GPV\Archivos de Maria Osmara Camacho Lopez - "
           r"Planeación Financiera\Presupuestos\2027\5_Generacion\4_Reservas\Outputs")
PATRON = "BD*RFV*Proyeccion*.xls*"      # acepta "BD_RFV_Proyeccion", "BD_ RFV_Proyeccion", etc.
HOJA = "BD_Montos_RRC_SONR"

# ---- Catálogos ------------------------------------------------------------------------
VARIABLES = {  # etiqueta en pantalla -> prefijo de la columna en la BD
    "Reserva (monto)": "RAM",
    "Prima 24M": "PRIMA 24M",
    "PR 24M": "PR 24M",
    "MA (monto afianzado)": "MA",
    "RFV MA": "RFV MA",
    "Cesión": "CESION",
    "PT (prima tomada del mes)": "PT",
}
FLUJOS = {"PT"}            # se acumulan en el año; el resto son saldos (se toma el cierre)
RATIOS = {"CESION"}        # porcentajes: promedio ponderado por la reserva

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
UNIDADES = {"Pesos": 1, "Miles": 1e3, "Millones": 1e6}
SUFIJO = {"Pesos": "", "Miles": " K", "Millones": " M"}

# Paleta categórica fija (validada para modo oscuro y daltonismo); el color sigue al ramo
COL_RAMO = {"130": "#3987e5", "140": "#d95926", "150": "#199e70", "160": "#c98500", "170": "#d55181"}
COL_CONCEPTO = {"RCONT": "#3987e5", "RFV BRUTO": "#d95926", "RFV IRR": "#199e70", "RFV NETO": "#c98500"}
SEQ_AZUL = ["#0d366b", "#104281", "#184f95", "#1c5cab", "#256abf", "#2a78d6", "#3987e5",
            "#5598e7", "#6da7ec", "#86b6ef", "#9ec5f4", "#cde2fb"]
POS, NEG = "#3987e5", "#e66767"

BG, CARD, BORDE = "#0e1422", "#161e30", "#24304a"
TXT, TXT2, TXT3 = "#eef1f7", "#b6bfd1", "#7d879c"

_v = tuple(int(x) for x in re.findall(r"\d+", st.__version__)[:2])
ANCHO = {"width": "stretch"} if _v >= (1, 50) else {"use_container_width": True}   # compatible con versiones viejas

st.set_page_config(page_title="Reservas FCST 2027", page_icon="📊", layout="wide",
                   initial_sidebar_state="expanded")

st.markdown(f"""
<style>
  .stApp {{ background:{BG}; }}
  section[data-testid="stSidebar"] {{ background:#0b4f9c; min-width:290px; }}
  section[data-testid="stSidebar"] * {{ color:#ffffff !important; }}
  section[data-testid="stSidebar"] [data-baseweb="select"] > div,
  section[data-testid="stSidebar"] [data-baseweb="tag"] {{ background:#0a3f7d !important; border-color:#6da7ec !important; }}
  section[data-testid="stSidebar"] h3 {{ font-size:0.95rem; letter-spacing:.02em; margin:0.9rem 0 0.2rem 0; }}
  .block-container {{ padding-top:1.2rem; padding-bottom:2rem; }}
  .hdr {{ display:flex; align-items:center; justify-content:space-between; background:linear-gradient(90deg,#14213d,#0e1422);
          border:1px solid {BORDE}; border-radius:12px; padding:14px 22px; margin-bottom:14px; }}
  .hdr h1 {{ font-size:1.7rem; margin:0; color:{TXT}; font-weight:800; }}
  .hdr .sub {{ color:{TXT2}; font-size:.9rem; }}
  .chip {{ display:inline-block; background:#1c2a45; border:1px solid {BORDE}; color:{TXT2};
           border-radius:999px; padding:4px 12px; margin-left:6px; font-size:.8rem; }}
  .kpi {{ background:{CARD}; border:1px solid {BORDE}; border-radius:12px; padding:14px 16px; height:100%; }}
  .kpi .lbl {{ color:{TXT2}; font-size:.8rem; font-weight:600; text-transform:uppercase; letter-spacing:.04em; }}
  .kpi .val {{ color:{TXT}; font-size:1.65rem; font-weight:800; margin:4px 0 2px 0; }}
  .kpi .det {{ color:{TXT3}; font-size:.78rem; }}
  .up {{ color:#5598e7; font-weight:700; }} .down {{ color:#e66767; font-weight:700; }}
  div[data-testid="stTabs"] button p {{ font-size:.95rem; font-weight:600; }}
  .nota {{ color:{TXT3}; font-size:.78rem; }}
</style>
""", unsafe_allow_html=True)


# ---- Carga de datos -------------------------------------------------------------------
def buscar_archivo() -> str | None:
    candidatos = []
    for carpeta in (os.environ.get("RFV_CARPETA"), CARPETA, os.path.dirname(os.path.abspath(__file__))):
        if carpeta and os.path.isdir(carpeta):
            candidatos += [f for f in glob.glob(os.path.join(carpeta, PATRON))
                           if not os.path.basename(f).startswith("~$")]
        if candidatos:
            break
    return max(candidatos, key=os.path.getmtime) if candidatos else None


@st.cache_data(show_spinner="Leyendo la base de proyección...")
def cargar(contenido: bytes) -> pd.DataFrame:
    raw = pd.read_excel(io.BytesIO(contenido), sheet_name=HOJA, header=None)
    # renglón de encabezados = el que trae "CONCEPTO"
    fila = raw.index[raw.apply(lambda r: r.astype(str).str.strip().eq("CONCEPTO").any(), axis=1)][0]
    raw.columns = [str(c).strip() for c in raw.iloc[fila]]
    raw = raw.iloc[fila + 1:]
    raw = raw.loc[:, [c for c in raw.columns if c not in ("nan", "None")]]
    raw = raw.dropna(subset=["CONCEPTO", "PERIODO"])
    raw["PERIODO"] = pd.to_numeric(raw["PERIODO"], errors="coerce")
    raw = raw.dropna(subset=["PERIODO"])
    raw["PERIODO"] = raw["PERIODO"].astype(int)
    raw["CONCEPTO"] = raw["CONCEPTO"].astype(str).str.strip()

    patron = re.compile(r"^(.+?)[ _](\d{3})$")
    cols_val = [c for c in raw.columns if patron.match(c)]
    df = raw.melt(id_vars=["CONCEPTO", "PERIODO"], value_vars=cols_val, var_name="COL", value_name="VALOR")
    ext = df["COL"].str.extract(patron)
    df["VARIABLE"] = ext[0].str.strip()
    df["RAMO"] = ext[1]
    df["VALOR"] = pd.to_numeric(df["VALOR"], errors="coerce")      # "N/A" -> vacío
    df["ANIO"] = df["PERIODO"] // 100
    df["MES"] = df["PERIODO"] % 100
    df["FECHA"] = pd.to_datetime(dict(year=df["ANIO"], month=df["MES"], day=1))
    return df.drop(columns="COL")


archivo = buscar_archivo()
with st.sidebar:
    st.markdown("## 📊 Reservas FCST 2027")
    subido = st.file_uploader("Cargar otra versión del archivo (opcional)", type=["xlsx", "xlsm", "xls"])

if subido is not None:
    contenido, origen = subido.getvalue(), subido.name
elif archivo:
    with open(archivo, "rb") as fh:          # se lee en memoria: funciona aunque esté abierto en Excel
        contenido = fh.read()
    origen = os.path.basename(archivo)
else:
    st.error(f"No encontré un archivo con el patrón **{PATRON}** en:\n\n`{CARPETA}`\n\n"
             "Revisa la ruta (variable CARPETA al inicio del script) o carga el archivo desde el menú izquierdo.")
    st.stop()

datos = cargar(contenido)
conceptos = list(dict.fromkeys(datos["CONCEPTO"]))
conceptos_base = [c for c in conceptos if not c.startswith("BACKTESTING")]
ramos = sorted(datos["RAMO"].unique())
anios = sorted(datos["ANIO"].unique())

# ---- Menú izquierdo (filtros) ---------------------------------------------------------
with st.sidebar:
    st.markdown("### Concepto")
    concepto = st.radio("Concepto", conceptos, index=conceptos.index("RFV NETO") if "RFV NETO" in conceptos else 0,
                        label_visibility="collapsed")
    st.markdown("### Variable")
    var_lbl = st.radio("Variable", list(VARIABLES), label_visibility="collapsed")
    var = VARIABLES[var_lbl]
    st.markdown("### Ramo")
    sel_ramos = [r for r in ramos if st.checkbox(f"Ramo {r}", value=True, key=f"ramo_{r}")]
    st.markdown("### Año")
    anios_conc = sorted(datos.loc[datos["CONCEPTO"] == concepto, "ANIO"].unique())
    sel_anios = st.multiselect("Año", anios_conc, default=[max(anios_conc)], label_visibility="collapsed")
    st.markdown("### Mes")
    sel_meses_lbl = st.multiselect("Mes", MESES, default=MESES, label_visibility="collapsed")
    sel_meses = [MESES.index(m) + 1 for m in sel_meses_lbl]
    st.markdown("### Unidades")
    unidad = st.radio("Unidades", list(UNIDADES), index=2, horizontal=True, label_visibility="collapsed")
    st.caption(f"Fuente: {origen}")

if not (sel_ramos and sel_anios and sel_meses):
    st.warning("Selecciona al menos un ramo, un año y un mes en el menú de la izquierda.")
    st.stop()

DIV, SUF = UNIDADES[unidad], SUFIJO[unidad]
ES_RATIO = var in RATIOS


def fmt(v, ratio=False, dec=1):
    if v is None or pd.isna(v):
        return "N/A"
    if ratio:
        return f"{v * 100:,.{dec}f}%"
    return f"${v / DIV:,.{dec if unidad != 'Pesos' else 0}f}{SUF}"


# ---- Filtros y agregación -------------------------------------------------------------
def filtrar(conc=None, variable=None, rs=None, ys=None, ms=None):
    d = datos
    if conc is not None:
        d = d[d["CONCEPTO"].isin([conc] if isinstance(conc, str) else conc)]
    if variable is not None:
        d = d[d["VARIABLE"] == variable]
    d = d[d["RAMO"].isin(rs or sel_ramos)]
    d = d[d["ANIO"].isin(ys or sel_anios)]
    d = d[d["MES"].isin(ms or sel_meses)]
    return d


def serie(conc, variable, por=("FECHA",), rs=None, ys=None, ms=None) -> pd.DataFrame:
    """Suma por ramo; para Cesión, promedio ponderado por la reserva (RAM) del mismo concepto."""
    por = list(por)
    d = filtrar(conc, variable, rs, ys, ms)
    if variable in RATIOS:
        w = filtrar(conc, "RAM", rs, ys, ms)[["CONCEPTO", "PERIODO", "RAMO", "VALOR"]].rename(columns={"VALOR": "W"})
        d = d.merge(w, on=["CONCEPTO", "PERIODO", "RAMO"], how="left")
        d = d.dropna(subset=["VALOR"])
        d["VW"] = d["VALOR"] * d["W"].fillna(0)
        g = d.groupby(por, as_index=False).agg(VW=("VW", "sum"), W=("W", "sum"), M=("VALOR", "mean"))
        g["VALOR"] = (g["VW"] / g["W"]).where(g["W"] > 0, g["M"])
        return g[por + ["VALOR"]]
    return d.groupby(por, as_index=False)["VALOR"].sum(min_count=1)


def layout(fig, h=360, titulo=None, ytitle=None, ratio=False, leyenda=True):
    fig.update_layout(
        template="plotly_dark", height=h, paper_bgcolor=CARD, plot_bgcolor=CARD,
        font=dict(color=TXT2, size=12), margin=dict(l=10, r=10, t=50 if titulo else 20, b=10),
        title=dict(text=titulo, font=dict(color=TXT, size=15), x=0.01) if titulo else None,
        hovermode="x unified", showlegend=leyenda,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1, font=dict(color=TXT2)),
        hoverlabel=dict(bgcolor="#1c2a45", font_color=TXT, bordercolor=BORDE),
        bargap=0.25,
    )
    fig.update_xaxes(showgrid=False, linecolor=BORDE, tickfont=dict(color=TXT3))
    fig.update_yaxes(gridcolor="#222c42", zeroline=False, tickfont=dict(color=TXT3), title=ytitle,
                     tickformat=".0%" if ratio else ",.0f")
    fig.update_layout(legend_traceorder="normal")
    _meses_es(fig)
    return fig


def _meses_es(fig):
    """Etiquetas de mes en español en los ejes de fecha."""
    fechas = set()
    for tr in fig.data:
        xs = getattr(tr, "x", None)
        if xs is not None and len(xs) and isinstance(xs[0], (pd.Timestamp, datetime, np.datetime64)):
            fechas.update(pd.to_datetime(list(xs)))
    if not fechas:
        return
    fechas = sorted(fechas)
    paso = 1 if len(fechas) <= 15 else 3
    vals = fechas[::paso]
    fig.update_xaxes(tickvals=vals, ticktext=[f"{MESES[f.month - 1]}<br>{f.year}" for f in vals])


def valores(s):
    return s if ES_RATIO else s / DIV


# ---- Encabezado -----------------------------------------------------------------------
periodo_txt = f"{min(sel_anios)}–{max(sel_anios)}" if len(sel_anios) > 1 else str(sel_anios[0])
st.markdown(f"""
<div class="hdr">
  <div><h1>Proyección de Reservas · FCST 2027</h1>
  <div class="sub">Mensualización, estacionalidad y montos por ramo</div></div>
  <div><span class="chip">{concepto}</span><span class="chip">{var_lbl}</span>
  <span class="chip">Ramos {', '.join(sel_ramos)}</span><span class="chip">{periodo_txt}</span>
  <span class="chip">{unidad}</span></div>
</div>""", unsafe_allow_html=True)

# ---- KPIs -----------------------------------------------------------------------------
ult_anio = max(sel_anios)


def kpi_saldo(variable):
    """Cierre del último mes filtrado y variación vs. el mismo mes del año anterior."""
    s = serie(concepto, variable, por=("PERIODO",), ys=list(datos["ANIO"].unique()))
    s = s.dropna(subset=["VALOR"]).set_index("PERIODO")["VALOR"]
    dentro = [p for p in s.index if p // 100 in sel_anios and p % 100 in sel_meses]
    if not dentro:
        return None, None, None
    p = max(dentro)
    act, prev = s.get(p), s.get(p - 100)
    return act, prev, p


def tarjeta(col, titulo, variable):
    ratio = variable in RATIOS
    if variable in FLUJOS:
        s = serie(concepto, variable, por=("ANIO",))
        act = s.loc[s["ANIO"] == ult_anio, "VALOR"].sum()
        prev_s = serie(concepto, variable, por=("ANIO",), ys=[ult_anio - 1])
        prev = prev_s["VALOR"].sum() if not prev_s.empty else None
        det = f"Acumulado {ult_anio}"
    else:
        act, prev, p = kpi_saldo(variable)
        det = f"Cierre {MESES[p % 100 - 1]} {p // 100}" if p else "Sin dato"
    var_txt = ""
    if act is not None and prev not in (None, 0) and not pd.isna(prev):
        if ratio:
            dv = (act - prev) * 100
            var_txt = f'<span class="{"up" if dv >= 0 else "down"}">{"▲" if dv >= 0 else "▼"} {abs(dv):.1f} pp</span> vs año ant.'
        else:
            dv = act / prev - 1
            var_txt = f'<span class="{"up" if dv >= 0 else "down"}">{"▲" if dv >= 0 else "▼"} {abs(dv) * 100:.1f}%</span> vs año ant.'
    col.markdown(f'<div class="kpi"><div class="lbl">{titulo}</div><div class="val">{fmt(act, ratio)}</div>'
                 f'<div class="det">{det} · {var_txt}</div></div>', unsafe_allow_html=True)


k = st.columns(6)
for c, (t, v) in zip(k, [("Reserva", "RAM"), ("Prima 24M", "PRIMA 24M"), ("PR 24M", "PR 24M"),
                         ("MA", "MA"), ("RFV MA", "RFV MA"), ("Cesión", "CESION")]):
    tarjeta(c, t, v)
st.write("")

# ---- Pestañas -------------------------------------------------------------------------
t1, t2, t3, t4, t5 = st.tabs(["📅 Mensualización", "🌊 Estacionalidad", "🧩 Conceptos y backtesting",
                              "📐 Variables por ramo", "📋 Tabla"])

# === 1) Mensualización ===
with t1:
    c1, c2 = st.columns([2.2, 1])
    with c1:
        fig = go.Figure()
        if ES_RATIO:
            for r in sel_ramos:
                s = serie(concepto, var, rs=[r])
                fig.add_scatter(x=s["FECHA"], y=s["VALOR"], name=f"Ramo {r}", mode="lines+markers",
                                line=dict(color=COL_RAMO.get(r), width=2), marker=dict(size=7))
            tot = serie(concepto, var)
            fig.add_scatter(x=tot["FECHA"], y=tot["VALOR"], name="Total ponderado", mode="lines",
                            line=dict(color=TXT, width=2, dash="dot"))
        else:
            for r in sel_ramos:
                s = serie(concepto, var, rs=[r])
                fig.add_bar(x=s["FECHA"], y=valores(s["VALOR"]), name=f"Ramo {r}", marker_color=COL_RAMO.get(r),
                            marker_line=dict(color=CARD, width=1),
                            hovertemplate="%{y:,.1f}" + SUF + "<extra>Ramo " + r + "</extra>")
            tot = serie(concepto, var)
            fig.add_scatter(x=tot["FECHA"], y=valores(tot["VALOR"]), name="Total", mode="markers+text",
                            marker=dict(size=1, color=TXT), showlegend=False, text=[f"{v:,.0f}" for v in valores(tot["VALOR"])],
                            textposition="top center", textfont=dict(color=TXT2, size=10),
                            hovertemplate="Total: %{y:,.1f}" + SUF + "<extra></extra>")
            fig.update_layout(barmode="stack")
        layout(fig, 420, f"{var_lbl} mensual por ramo · {concepto}", None if ES_RATIO else f"{unidad} MXN", ES_RATIO)
        st.plotly_chart(fig, **ANCHO)
    with c2:
        _, _, p_cierre = kpi_saldo("RAM")
        base = filtrar(concepto, "RAM" if ES_RATIO else var)
        if var in FLUJOS:
            comp = base.groupby("RAMO", as_index=False)["VALOR"].sum()
            sub = f"Acumulado del filtro"
        else:
            comp = base[base["PERIODO"] == base["PERIODO"].max()].groupby("RAMO", as_index=False)["VALOR"].sum()
            pmax = base["PERIODO"].max()
            sub = f"Cierre {MESES[pmax % 100 - 1]} {pmax // 100}" if pd.notna(pmax) else ""
        comp = comp[comp["VALOR"] > 0]
        fig = go.Figure(go.Pie(labels=["Ramo " + r for r in comp["RAMO"]], values=comp["VALOR"] / DIV, hole=0.62,
                               marker=dict(colors=[COL_RAMO.get(r) for r in comp["RAMO"]], line=dict(color=CARD, width=2)),
                               sort=False, textinfo="percent", textposition="inside", textfont=dict(color="#ffffff"),
                               hovertemplate="%{label}: %{value:,.1f}" + SUF + " (%{percent})<extra></extra>"))
        tot_c = comp["VALOR"].sum()
        fig.add_annotation(text=f"<b>{fmt(tot_c)}</b><br><span style='font-size:11px'>{sub}</span>",
                           showarrow=False, font=dict(color=TXT, size=16))
        layout(fig, 420, "Composición por ramo" + (" (reserva)" if ES_RATIO else ""))
        fig.update_layout(hovermode="closest", legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center"))
        st.plotly_chart(fig, **ANCHO)

    # variación mensual
    tot = serie(concepto, var).sort_values("FECHA")
    if ES_RATIO:
        tot["DELTA"] = tot["VALOR"].diff() * 100
        ylab, hov = "Variación (pp)", "%{y:+.2f} pp"
    else:
        tot["DELTA"] = tot["VALOR"].diff() / DIV
        ylab, hov = f"Variación ({unidad})", "%{y:+,.1f}" + SUF
    fig = go.Figure(go.Bar(x=tot["FECHA"], y=tot["DELTA"], marker_color=[POS if v >= 0 else NEG for v in tot["DELTA"].fillna(0)],
                           hovertemplate=hov + "<extra></extra>", name="Variación"))
    layout(fig, 300, f"Variación mes contra mes · {var_lbl}", ylab, leyenda=False)
    fig.update_yaxes(tickformat=",.1f")
    st.plotly_chart(fig, **ANCHO)

# === 2) Estacionalidad ===
with t2:
    todos = sorted(datos.loc[datos["CONCEPTO"] == concepto, "ANIO"].unique())
    s = serie(concepto, var, por=("ANIO", "MES"), ys=todos)
    st.markdown('<div class="nota">Esta pestaña compara todos los años disponibles del concepto para ver el patrón estacional.</div>', unsafe_allow_html=True)
    piv = s.pivot(index="ANIO", columns="MES", values="VALOR").reindex(columns=sel_meses)
    c1, c2 = st.columns(2)
    with c1:
        z = piv.values * (100 if ES_RATIO else 1 / DIV)
        fig = go.Figure(go.Heatmap(
            z=z, x=[MESES[m - 1] for m in piv.columns], y=[str(a) for a in piv.index],
            colorscale=[[i / (len(SEQ_AZUL) - 1), c] for i, c in enumerate(reversed(SEQ_AZUL))],
            text=[[("" if pd.isna(v) else (f"{v:.1f}%" if ES_RATIO else f"{v:,.0f}")) for v in row] for row in z],
            texttemplate="%{text}", textfont=dict(size=10), xgap=2, ygap=2,
            hovertemplate="%{y} %{x}: %{text}" + ("" if ES_RATIO else SUF) + "<extra></extra>",
            colorbar=dict(thickness=10, tickfont=dict(color=TXT3))))
        layout(fig, 360, f"Mapa de calor año × mes · {var_lbl}", leyenda=False)
        fig.update_layout(hovermode="closest")
        fig.update_yaxes(tickformat=None, type="category", gridcolor=CARD)
        st.plotly_chart(fig, **ANCHO)
    with c2:
        fig = go.Figure()
        col_anio = ["#86b6ef", "#d95926", "#c98500", "#199e70", "#d55181"]
        for i, a in enumerate(piv.index):
            fila = piv.loc[a]
            idx = fila / fila.mean() if fila.mean() else fila
            fig.add_scatter(x=[MESES[m - 1] for m in piv.columns], y=idx, name=str(a), mode="lines+markers",
                            line=dict(color=col_anio[i % len(col_anio)], width=2, dash="dot" if a < ult_anio else "solid"),
                            marker=dict(size=7), hovertemplate="%{y:.3f}<extra>" + str(a) + "</extra>")
        fig.add_hline(y=1, line=dict(color=TXT3, width=1, dash="dash"))
        layout(fig, 360, "Índice estacional (mes ÷ promedio del año)", "Índice")
        fig.update_yaxes(tickformat=".2f")
        st.plotly_chart(fig, **ANCHO)

    # mezcla mensual por ramo (peso de cada mes en el año)
    fig = go.Figure()
    for r in sel_ramos:
        sr = serie(concepto, var, por=("ANIO", "MES"), rs=[r])
        sr = sr[sr["ANIO"] == ult_anio]
        if sr["VALOR"].abs().sum() == 0:
            continue
        y = sr["VALOR"] / sr["VALOR"].mean()
        fig.add_scatter(x=[MESES[m - 1] for m in sr["MES"]], y=y, name=f"Ramo {r}", mode="lines+markers",
                        line=dict(color=COL_RAMO.get(r), width=2), marker=dict(size=7))
    fig.add_hline(y=1, line=dict(color=TXT3, width=1, dash="dash"))
    layout(fig, 320, f"Índice estacional por ramo · {ult_anio}", "Índice")
    fig.update_yaxes(tickformat=".2f")
    st.plotly_chart(fig, **ANCHO)
    st.markdown('<div class="nota">Índice &gt; 1: el mes está por arriba del promedio de su año; &lt; 1: por debajo. '
                'Ramos sin monto en el año se omiten.</div>', unsafe_allow_html=True)

# === 3) Conceptos y backtesting ===
with t3:
    fig = go.Figure()
    for c in conceptos_base:
        s = serie(c, var)
        fig.add_scatter(x=s["FECHA"], y=valores(s["VALOR"]), name=c, mode="lines+markers",
                        line=dict(color=COL_CONCEPTO.get(c, TXT2), width=2), marker=dict(size=6))
        bt = "BACKTESTING " + c
        if bt in conceptos:
            sb = serie(bt, var)
            if not sb.dropna().empty:
                fig.add_scatter(x=sb["FECHA"], y=valores(sb["VALOR"]), name=bt, mode="lines",
                                line=dict(color=COL_CONCEPTO.get(c, TXT2), width=2, dash="dot"))
    layout(fig, 420, f"{var_lbl} por concepto (línea punteada = backtesting)",
           None if ES_RATIO else f"{unidad} MXN", ES_RATIO)
    st.plotly_chart(fig, **ANCHO)

    # Proyección vs backtesting del concepto seleccionado
    base_c = concepto.replace("BACKTESTING ", "")
    bt_c = "BACKTESTING " + base_c
    if bt_c in conceptos:
        ys_bt = sorted(datos.loc[datos["CONCEPTO"] == bt_c, "ANIO"].unique())
        a = serie(base_c, var, por=("FECHA",), ys=ys_bt)
        b = serie(bt_c, var, por=("FECHA",), ys=ys_bt)
        m = a.merge(b, on="FECHA", suffixes=("_P", "_B"))
        fig = go.Figure()
        fig.add_bar(x=m["FECHA"], y=valores(m["VALOR_P"]), name=base_c, marker_color=COL_CONCEPTO.get(base_c, POS))
        fig.add_bar(x=m["FECHA"], y=valores(m["VALOR_B"]), name=bt_c, marker_color="#5f6b84")
        layout(fig, 340, f"{base_c} vs. backtesting · {', '.join(map(str, ys_bt))}",
               None if ES_RATIO else f"{unidad} MXN", ES_RATIO)
        fig.update_layout(barmode="group")
        st.plotly_chart(fig, **ANCHO)
        if not ES_RATIO and not m.empty:
            dif = (m["VALOR_P"].iloc[-1] / m["VALOR_B"].iloc[-1] - 1) if m["VALOR_B"].iloc[-1] else float("nan")
            st.markdown(f'<div class="nota">Cierre {m["FECHA"].iloc[-1]:%b %Y}: {base_c} {fmt(m["VALOR_P"].iloc[-1])} '
                        f'vs. backtesting {fmt(m["VALOR_B"].iloc[-1])} ({dif * 100:+.1f}%).</div>', unsafe_allow_html=True)

# === 4) Variables por ramo (small multiples) ===
with t4:
    st.markdown(f'<div class="nota">Concepto: {concepto}. Prima 24M, PR 24M, MA y RFV MA son insumos del cálculo; '
                'Cesión en % (ponderada por reserva en el total).</div>', unsafe_allow_html=True)
    pares = [("Reserva (monto)", "RAM"), ("Prima 24M", "PRIMA 24M"), ("PR 24M", "PR 24M"),
             ("MA (monto afianzado)", "MA"), ("RFV MA", "RFV MA"), ("Cesión", "CESION")]
    for i in range(0, len(pares), 2):
        cols = st.columns(2)
        for col, (lbl, v) in zip(cols, pares[i:i + 2]):
            ratio = v in RATIOS
            fig = go.Figure()
            for r in sel_ramos:
                s = serie(concepto, v, rs=[r])
                if s["VALOR"].fillna(0).abs().sum() == 0:
                    continue
                fig.add_scatter(x=s["FECHA"], y=s["VALOR"] if ratio else s["VALOR"] / DIV, name=f"Ramo {r}",
                                mode="lines", line=dict(color=COL_RAMO.get(r), width=2))
            layout(fig, 300, lbl, None if ratio else f"{unidad} MXN", ratio)
            col.plotly_chart(fig, **ANCHO)

# === 5) Tabla ===
with t5:
    d = filtrar(concepto, var)
    tab = d.pivot_table(index="PERIODO", columns="RAMO", values="VALOR", aggfunc="sum")
    tab.columns = [f"Ramo {c}" for c in tab.columns]
    tot = serie(concepto, var, por=("PERIODO",)).set_index("PERIODO")["VALOR"]
    tab["Total" + (" ponderado" if ES_RATIO else "")] = tot
    tab.index = [f"{MESES[p % 100 - 1]} {p // 100}" for p in tab.index]
    vista = tab * 100 if ES_RATIO else tab / DIV
    st.markdown(f"**{var_lbl} · {concepto}** — {'%' if ES_RATIO else unidad + ' MXN'}")
    st.dataframe(vista.style.format("{:,.2f}" if ES_RATIO else "{:,.1f}", na_rep="N/A"),
                 **ANCHO, height=min(40 + 35 * len(vista), 700))

    # descarga: base larga filtrada + pivote
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        vista.to_excel(xw, sheet_name="Mensualizacion")
        filtrar(conceptos, None).query("VARIABLE in @VARIABLES.values()").drop(columns="FECHA") \
            .to_excel(xw, sheet_name="Base_filtrada", index=False)
    st.download_button("⬇️ Descargar a Excel", buf.getvalue(),
                       file_name=f"Dashboard_Reservas_{datetime.now():%Y%m%d}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
