# =====================================================
# DASHBOARD_HTML - Genera el dashboard visual del RFCST
# =====================================================
# Modulo auxiliar de VAL_RFCST26.py. Produce un HTML
# autocontenido (sin dependencias externas) con tema
# oscuro: KPIs, barras por LN, dona de semaforos y
# tabla de excepciones.
# =====================================================

import math

import numpy as np
import pandas as pd

# Paleta (modo oscuro validado)
C_SURFACE = "#1a1a19"
C_PAGE = "#0d0d0d"
C_INK = "#ffffff"
C_INK2 = "#c3c2b7"
C_MUTED = "#898781"
C_GRID = "#2c2c2a"
C_BASE = "#383835"
C_BORDER = "rgba(255,255,255,0.10)"

S1 = "#3987e5"   # azul    - Forecast
S2 = "#d95926"   # naranja - Presupuesto
S3 = "#199e70"   # aqua    - Real 2025

C_VERDE = "#0ca30c"
C_AMARILLO = "#fab219"
C_ROJO = "#d03b3b"
C_SIN_DATO = "#57565282"


def _fmt_m(v, dec=1):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return "s/d"
    return f"{v / 1e6:,.{dec}f} M"


def _fmt_pct(v, dec=1, signo=False):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return "s/d"
    if v > 9.99:
        return "&gt;999%"
    if v < -9.99:
        return "&lt;-999%"
    s = "+" if (signo and v > 0) else ""
    return f"{s}{v * 100:,.{dec}f}%"


def _nice_ticks(vmax, n=4):
    if vmax <= 0:
        return [0, 1]
    paso_bruto = vmax / n
    mag = 10 ** math.floor(math.log10(paso_bruto))
    for m in (1, 2, 2.5, 5, 10):
        if paso_bruto <= m * mag:
            paso = m * mag
            break
    ticks = []
    t = 0
    while t < vmax + paso * 0.999:
        ticks.append(t)
        t += paso
    return ticks


def _barra_redondeada(x, y, w, h, r=4):
    """Path de barra vertical con esquinas superiores redondeadas,
    anclada a la linea base."""
    if h <= 0.5:
        return ""
    r = min(r, w / 2, h)
    x2 = x + w
    yb = y + h
    return (
        f'M {x:.1f} {yb:.1f} L {x:.1f} {y + r:.1f} '
        f'Q {x:.1f} {y:.1f} {x + r:.1f} {y:.1f} '
        f'L {x2 - r:.1f} {y:.1f} '
        f'Q {x2:.1f} {y:.1f} {x2:.1f} {y + r:.1f} '
        f'L {x2:.1f} {yb:.1f} Z'
    )


def barras_agrupadas(categorias, series, width=980, height=320,
                     etiqueta_serie=0):
    """SVG de barras agrupadas.

    series: lista de dicts {nombre, color, valores}. Los valores NaN
    se dibujan como hueco. Solo la serie `etiqueta_serie` lleva
    etiqueta directa de valor (etiquetado selectivo).
    """
    mL, mR, mT, mB = 56, 12, 14, 46
    pw, ph = width - mL - mR, height - mT - mB

    vmax = 0
    for s in series:
        for v in s["valores"]:
            if v is not None and not (isinstance(v, float) and math.isnan(v)):
                vmax = max(vmax, v)
    ticks = _nice_ticks(vmax)
    vmax_t = ticks[-1]

    def ya(v):
        return mT + ph - (v / vmax_t) * ph

    nc, ns = len(categorias), len(series)
    grupo_w = pw / nc
    gap_barras = 2
    bw = min(34, (grupo_w * 0.72 - gap_barras * (ns - 1)) / ns)
    total_w = bw * ns + gap_barras * (ns - 1)

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" '
           f'aria-label="Barras por linea de negocio">']

    for t in ticks:
        y = ya(t)
        out.append(f'<line x1="{mL}" y1="{y:.1f}" x2="{width - mR}" '
                   f'y2="{y:.1f}" stroke="{C_GRID}" stroke-width="1"/>')
        out.append(f'<text x="{mL - 8}" y="{y + 3.5:.1f}" text-anchor="end" '
                   f'class="tick">{_fmt_m(t, 0)}</text>')

    for i, cat in enumerate(categorias):
        gx = mL + i * grupo_w + (grupo_w - total_w) / 2
        out.append(f'<text x="{mL + i * grupo_w + grupo_w / 2:.1f}" '
                   f'y="{height - mB + 18}" text-anchor="middle" '
                   f'class="cat">{cat}</text>')
        for k, s in enumerate(series):
            v = s["valores"][i]
            if v is None or (isinstance(v, float) and math.isnan(v)):
                continue
            x = gx + k * (bw + gap_barras)
            y = ya(max(v, 0))
            h = mT + ph - y
            path = _barra_redondeada(x, y, bw, h)
            if path:
                out.append(
                    f'<path d="{path}" fill="{s["color"]}" class="bar">'
                    f'<title>{cat} · {s["nombre"]}: {_fmt_m(v)}</title></path>'
                )
            if k == etiqueta_serie and vmax_t and v / vmax_t > 0.045:
                out.append(f'<text x="{x + bw / 2:.1f}" y="{y - 5:.1f}" '
                           f'text-anchor="middle" class="vlabel">'
                           f'{_fmt_m(v, 0)}</text>')

    out.append(f'<line x1="{mL}" y1="{mT + ph}" x2="{width - mR}" '
               f'y2="{mT + ph}" stroke="{C_BASE}" stroke-width="1"/>')
    out.append('</svg>')

    leyenda = ''.join(
        f'<span class="lg"><i style="background:{s["color"]}"></i>{s["nombre"]}</span>'
        for s in series
    )
    return f'<div class="legend">{leyenda}</div>{"".join(out)}'


def dona(conteos, width=230, height=230):
    """SVG tipo dona para la distribucion de semaforos.
    conteos: lista de (etiqueta, valor, color)."""
    total = sum(v for _, v, _ in conteos)
    cx, cy, r, grosor = width / 2, height / 2, width / 2 - 12, 30

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" '
           f'aria-label="Distribucion de semaforos">']

    ang = -90.0
    for etiqueta, v, color in conteos:
        if total == 0 or v == 0:
            continue
        frac = v / total
        barrido = frac * 360
        # brecha de 2px convertida a grados sobre el radio medio
        gap_deg = min(2.5, barrido * 0.15)
        a0 = math.radians(ang + gap_deg / 2)
        a1 = math.radians(ang + barrido - gap_deg / 2)
        rm = r - grosor / 2
        x0, y0 = cx + rm * math.cos(a0), cy + rm * math.sin(a0)
        x1, y1 = cx + rm * math.cos(a1), cy + rm * math.sin(a1)
        grande = 1 if (a1 - a0) > math.pi else 0
        out.append(
            f'<path d="M {x0:.2f} {y0:.2f} A {rm:.2f} {rm:.2f} 0 {grande} 1 '
            f'{x1:.2f} {y1:.2f}" fill="none" stroke="{color}" '
            f'stroke-width="{grosor}" stroke-linecap="butt" class="bar">'
            f'<title>{etiqueta}: {v:,} ({frac:.1%})</title></path>'
        )
        ang += barrido

    out.append(f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" '
               f'class="donut-n">{total:,}</text>')
    out.append(f'<text x="{cx}" y="{cy + 16}" text-anchor="middle" '
               f'class="donut-l">contratos</text>')
    out.append('</svg>')
    return ''.join(out)


def _chip(valor):
    clase = {"ROJO": "rojo", "AMARILLO": "amarillo", "VERDE": "verde"}.get(valor, "gris")
    icono = {"rojo": "&#9650;", "amarillo": "&#9679;", "verde": "&#10003;"}.get(clase, "–")
    return f'<span class="chip {clase}">{icono} {valor}</span>'


def generar_dashboard_html(ruta, df, resumen, dashboard, excepciones, parametros):

    d = dict(zip(dashboard["Indicador"], dashboard["Valor"]))

    total_fcst = d["Prima Forecast 2026"]
    total_ppto = d["Prima PPTO 2026"]
    total_real25 = d["Prima Real 2025"]
    total_0726 = d["Prima Real corte Jul 2026"]
    inc_agodic = d["Incremento implicito Ago-Dic"]
    esperado = d["Incremento esperado Ago-Dic (ppto ajustado)"]
    desv_inc = d["Desviacion incremento Ago-Dic"]
    real_agodic25 = d["Real Ago-Dic 2025 (referencia)"]
    n_rojo = int(d["Contratos ROJO"])
    n_amarillo = int(d["Contratos AMARILLO"])
    n_verde = int(d["Contratos VERDE"])
    n_v1 = int(d["Contratos FCST < Real Jul (V1)"])

    r = resumen.sort_values("LN").reset_index(drop=True)
    categorias = r["LN"].tolist()

    chart_primas = barras_agrupadas(
        categorias,
        [
            {"nombre": "Forecast 2026", "color": S1,
             "valores": r["Primas_1226"].tolist()},
            {"nombre": "Ppto 2026", "color": S2,
             "valores": r["Primas_PPTO1226"].tolist()},
            {"nombre": "Real 2025", "color": S3,
             "valores": r["Primas_1225"].tolist()},
        ],
    )

    chart_inc = barras_agrupadas(
        categorias,
        [
            {"nombre": "Incremento FCST Ago-Dic", "color": S1,
             "valores": r["Inc_AgoDic"].tolist()},
            {"nombre": "Esperado (Ppto Ago-Dic × ejecucion)", "color": S2,
             "valores": r["Inc_Esperado"].tolist()},
            {"nombre": "Real Ago-Dic 2025", "color": S3,
             "valores": r["Primas_0812_25"].tolist()},
        ],
        height=300,
    )

    grafica_dona = dona([
        ("Verde", n_verde, C_VERDE),
        ("Amarillo", n_amarillo, C_AMARILLO),
        ("Rojo", n_rojo, C_ROJO),
    ])

    # ----- tabla resumen por LN -----
    filas_ln = []
    for _, row in resumen.sort_values("Score_Total", ascending=False).iterrows():
        filas_ln.append(
            "<tr>"
            f"<td>LN {row['LN']}</td>"
            f"<td class='num'>{_fmt_m(row['Primas_1226'])}</td>"
            f"<td class='num'>{_fmt_pct(row['Cumplimiento_PPTO'] - 1, signo=True)}</td>"
            f"<td class='num'>{_fmt_pct(row['Crec_vs_Real25'], signo=True)}</td>"
            f"<td class='num'>{_fmt_pct(row['Desv_Inc_AgoDic'], signo=True)}</td>"
            f"<td>{_chip(row['Semaforo_Inc'])}</td>"
            f"<td class='num'>{_fmt_pct(row['Ind_Sin_FCST'])}</td>"
            f"<td>{_chip(row['Semaforo_Sin'])}</td>"
            f"<td class='num'>{int(row['Contratos_Alerta'])} / {int(row['Contratos'])}</td>"
            f"<td class='num'>{row['Score_Total']:.0f}</td>"
            f"<td><span class='nivel {row['Nivel_Riesgo'].lower()}'>{row['Nivel_Riesgo']}</span></td>"
            "</tr>"
        )

    # ----- tabla top excepciones -----
    filas_exc = []
    for _, row in excepciones.head(12).iterrows():
        motivos = []
        if row.get("F_V1_Primas"):
            motivos.append("FCST &lt; Real Jul")
        if row.get("F_V6_PrimaNegativa"):
            motivos.append("Prima negativa")
        if row.get("F_V6_FcstCero"):
            motivos.append("FCST en cero")
        if row.get("Semaforo_Sin") == "ROJO":
            motivos.append("Siniestralidad &gt; 100%")
        if row.get("Semaforo_Inc") == "ROJO":
            motivos.append("Desv. incremento")
        comp = str(row.get("Compañía", ""))[:38]
        filas_exc.append(
            "<tr>"
            f"<td>LN {row['LN']}</td>"
            f"<td>{comp}</td>"
            f"<td>{row.get('País', '')}</td>"
            f"<td>{row.get('Tipo Reaseguro', '')}</td>"
            f"<td class='num'>{_fmt_m(row['Primas 0726'], 2)}</td>"
            f"<td class='num'>{_fmt_m(row['Primas 1226'], 2)}</td>"
            f"<td class='num'>{_fmt_m(row['Inc_Primas_AgoDic'], 2)}</td>"
            f"<td class='motivo'>{' · '.join(motivos) if motivos else 'Revision'}</td>"
            "</tr>"
        )

    # ----- insight automatico -----
    peor = resumen.sort_values("Score_Total", ascending=False).iloc[0]
    cumpl = total_fcst / total_ppto - 1
    crec25 = total_fcst / total_real25 - 1
    insight = (
        f"El RFCST 2026 proyecta <b>{_fmt_m(total_fcst)}</b> de prima, "
        f"<b>{_fmt_pct(cumpl, signo=True)}</b> sobre el presupuesto anual y "
        f"<b>{_fmt_pct(crec25, signo=True)}</b> contra el cierre real 2025. "
        f"El incremento implicito Ago-Dic ({_fmt_m(inc_agodic)}) esta "
        f"<b>{_fmt_pct(desv_inc, signo=True)}</b> respecto al esperado ajustando "
        f"el ppto Ago-Dic por el nivel de ejecucion a julio ({_fmt_m(esperado)}), "
        f"y equivale a {inc_agodic / real_agodic25:,.1f}x el real del mismo "
        f"periodo 2025 ({_fmt_m(real_agodic25)}). "
        f"<b>{n_v1:,}</b> contratos reportan forecast menor al real de julio (V1) "
        f"y la LN con mayor score de riesgo es <b>LN {peor['LN']}</b> "
        f"({peor['Nivel_Riesgo']}, score {peor['Score_Total']:.0f})."
    )

    html = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Validación RFCST 2026</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; margin: 0; }}
  body {{
    background: {C_PAGE}; color: {C_INK};
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    padding: 26px 30px 40px;
  }}
  header {{ display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap;
            margin-bottom: 20px; }}
  h1 {{ font-size: 21px; font-weight: 650; }}
  header .sub {{ color: {C_MUTED}; font-size: 12.5px; }}
  .grid {{ display: grid; gap: 14px; }}
  .kpis {{ grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); }}
  .card {{
    background: {C_SURFACE}; border: 1px solid {C_BORDER};
    border-radius: 12px; padding: 16px 18px;
  }}
  .kpi .t {{ color: {C_INK2}; font-size: 12px; margin-bottom: 8px;
             display: flex; align-items: center; gap: 7px; }}
  .kpi .t i {{ width: 22px; height: 22px; border-radius: 6px; display: inline-flex;
               align-items: center; justify-content: center; font-style: normal;
               font-size: 12px; background: rgba(57,135,229,.16); }}
  .kpi .v {{ font-size: 26px; font-weight: 650; letter-spacing: -0.02em; }}
  .kpi .d {{ font-size: 12px; margin-top: 7px; color: {C_INK2}; }}
  .kpi .d b {{ font-weight: 600; padding: 2px 7px; border-radius: 999px;
               font-size: 11.5px; }}
  .up   {{ color: #7dd87d; background: rgba(12,163,12,.14); }}
  .down {{ color: #f09a9a; background: rgba(208,59,59,.16); }}
  .warn {{ color: {C_AMARILLO}; background: rgba(250,178,25,.13); }}
  section {{ margin-top: 14px; }}
  .card h2 {{ font-size: 13.5px; font-weight: 600; color: {C_INK2};
              margin-bottom: 4px; }}
  .card .nota {{ font-size: 11.5px; color: {C_MUTED}; margin-bottom: 10px; }}
  .dos {{ grid-template-columns: 2.1fr 1fr; align-items: stretch; }}
  @media (max-width: 900px) {{ .dos {{ grid-template-columns: 1fr; }} }}
  svg {{ width: 100%; height: auto; display: block; }}
  .tick, .donut-l {{ fill: {C_MUTED}; font-size: 10.5px;
    font-family: system-ui, sans-serif; font-variant-numeric: tabular-nums; }}
  .cat {{ fill: {C_INK2}; font-size: 11px; font-family: system-ui, sans-serif; }}
  .vlabel {{ fill: {C_INK2}; font-size: 10px; font-family: system-ui, sans-serif;
             font-variant-numeric: tabular-nums; }}
  .donut-n {{ fill: {C_INK}; font-size: 26px; font-weight: 650;
              font-family: system-ui, sans-serif; }}
  .bar {{ transition: opacity .12s; }}
  svg:hover .bar {{ opacity: .45; }}
  svg .bar:hover {{ opacity: 1; }}
  .legend {{ display: flex; gap: 16px; flex-wrap: wrap; margin: 4px 0 10px; }}
  .lg {{ color: {C_INK2}; font-size: 11.5px; display: inline-flex;
         align-items: center; gap: 6px; }}
  .lg i {{ width: 10px; height: 10px; border-radius: 3px; display: inline-block; }}
  .donut-wrap {{ display: flex; flex-direction: column; align-items: center;
                 gap: 6px; }}
  .donut-wrap svg {{ max-width: 210px; }}
  .dl {{ width: 100%; font-size: 12px; color: {C_INK2}; }}
  .dl div {{ display: flex; justify-content: space-between; padding: 5px 2px;
             border-bottom: 1px solid {C_GRID}; }}
  .dl div:last-child {{ border-bottom: none; }}
  .dl i {{ width: 10px; height: 10px; border-radius: 3px; display: inline-block;
           margin-right: 7px; }}
  .dl .n {{ font-variant-numeric: tabular-nums; color: {C_INK}; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ text-align: left; color: {C_MUTED}; font-weight: 500; font-size: 11px;
        padding: 7px 10px; border-bottom: 1px solid {C_BASE};
        white-space: nowrap; }}
  td {{ padding: 7.5px 10px; border-bottom: 1px solid {C_GRID};
        white-space: nowrap; }}
  tr:last-child td {{ border-bottom: none; }}
  tbody tr:hover {{ background: rgba(255,255,255,.03); }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  th.num {{ text-align: right; }}
  .motivo {{ color: {C_INK2}; white-space: normal; max-width: 260px; }}
  .chip {{ font-size: 10.5px; font-weight: 600; padding: 2px 8px;
           border-radius: 999px; }}
  .chip.rojo {{ color: #f09a9a; background: rgba(208,59,59,.16); }}
  .chip.amarillo {{ color: {C_AMARILLO}; background: rgba(250,178,25,.13); }}
  .chip.verde {{ color: #7dd87d; background: rgba(12,163,12,.14); }}
  .chip.gris {{ color: {C_MUTED}; background: rgba(137,135,129,.15); }}
  .nivel {{ font-size: 10.5px; font-weight: 700; padding: 2px 8px;
            border-radius: 5px; }}
  .nivel.critico {{ color: #f09a9a; background: rgba(208,59,59,.18); }}
  .nivel.alto {{ color: {C_AMARILLO}; background: rgba(250,178,25,.14); }}
  .nivel.medio {{ color: #9ec5f4; background: rgba(57,135,229,.14); }}
  .nivel.bajo {{ color: #7dd87d; background: rgba(12,163,12,.14); }}
  .insight {{ background: linear-gradient(90deg, rgba(57,135,229,.10),
              rgba(57,135,229,.03)); border: 1px solid rgba(57,135,229,.25);
              border-radius: 12px; padding: 14px 18px; font-size: 13px;
              line-height: 1.55; color: {C_INK2}; }}
  .insight b {{ color: {C_INK}; }}
  .scroll {{ overflow-x: auto; }}
  footer {{ margin-top: 18px; color: {C_MUTED}; font-size: 11px; }}
</style>
</head>
<body>

<header>
  <h1>Validación RFCST 2026 · 7+5</h1>
  <span class="sub">Corte Julio 2026 · {parametros['archivo']} ·
    generado {parametros['generado']}</span>
</header>

<div class="grid kpis">
  <div class="card kpi">
    <div class="t"><i>&#128181;</i>Prima Forecast 2026</div>
    <div class="v">{_fmt_m(total_fcst)}</div>
    <div class="d"><b class="{'up' if cumpl >= 0 else 'down'}">{_fmt_pct(cumpl, signo=True)}</b>
      vs Ppto 2026 ({_fmt_m(total_ppto)})</div>
  </div>
  <div class="card kpi">
    <div class="t"><i>&#128200;</i>Crecimiento vs Real 2025</div>
    <div class="v">{_fmt_pct(crec25, signo=True)}</div>
    <div class="d">Real 2025: {_fmt_m(total_real25)} · Real Jul 26: {_fmt_m(total_0726)}</div>
  </div>
  <div class="card kpi">
    <div class="t"><i>&#9202;</i>Incremento Ago-Dic implícito</div>
    <div class="v">{_fmt_m(inc_agodic)}</div>
    <div class="d"><b class="{'warn' if abs(desv_inc) > 0.2 else 'up'}">{_fmt_pct(desv_inc, signo=True)}</b>
      vs esperado ({_fmt_m(esperado)})</div>
  </div>
  <div class="card kpi">
    <div class="t"><i>&#9888;</i>Contratos con alerta</div>
    <div class="v">{n_rojo + n_amarillo:,}</div>
    <div class="d"><b class="down">{n_rojo:,} rojos</b> · {n_amarillo:,} amarillos ·
      {n_v1:,} con FCST &lt; Real Jul</div>
  </div>
</div>

<section class="grid dos">
  <div class="card">
    <h2>Primas por línea de negocio</h2>
    <div class="nota">Forecast acumulado a Dic 2026 vs presupuesto anual y cierre real 2025 (USD)</div>
    {chart_primas}
  </div>
  <div class="card donut-wrap">
    <h2>Semáforo de contratos</h2>
    {grafica_dona}
    <div class="dl">
      <div><span><i style="background:{C_VERDE}"></i>&#10003; Verde — sin alertas</span><span class="n">{n_verde:,}</span></div>
      <div><span><i style="background:{C_AMARILLO}"></i>&#9679; Amarillo — revisar</span><span class="n">{n_amarillo:,}</span></div>
      <div><span><i style="background:{C_ROJO}"></i>&#9650; Rojo — inconsistencia</span><span class="n">{n_rojo:,}</span></div>
    </div>
  </div>
</section>

<section class="card">
  <h2>Incremento Ago-Dic 2026: forecast vs esperado</h2>
  <div class="nota">Esperado = Ppto Ago-Dic 2026 × nivel de ejecución Ene-Jul
    (Real Jul / Ppto Ene-Jul). Referencia: real del mismo periodo 2025. LN 4004
    no tiene ppto Ene-Jul, por lo que no se calcula esperado.</div>
  {chart_inc}
</section>

<section class="card scroll">
  <h2>Resumen por línea de negocio</h2>
  <div class="nota">Ordenado por score de riesgo (0-100). Índices calculados sobre agregados.</div>
  <table>
    <thead><tr>
      <th>LN</th><th class="num">Prima FCST</th><th class="num">vs Ppto</th>
      <th class="num">vs Real 25</th><th class="num">Desv. inc. Ago-Dic</th><th>Semáforo</th>
      <th class="num">% Sin FCST</th><th>Semáforo</th>
      <th class="num">Alertas</th><th class="num">Score</th><th>Riesgo</th>
    </tr></thead>
    <tbody>{''.join(filas_ln)}</tbody>
  </table>
</section>

<section class="card scroll">
  <h2>Top excepciones (semáforo rojo)</h2>
  <div class="nota">Contratos con mayor impacto en prima. Detalle completo en VAL_RFCST26.xlsx → Excepciones.</div>
  <table>
    <thead><tr>
      <th>LN</th><th>Compañía</th><th>País</th><th>Tipo</th>
      <th class="num">Real Jul 26</th><th class="num">FCST Dic 26</th>
      <th class="num">Inc. Ago-Dic</th><th>Motivo</th>
    </tr></thead>
    <tbody>{''.join(filas_exc)}</tbody>
  </table>
</section>

<section class="insight">&#128161; {insight}</section>

<footer>Validación automática VAL_RFCST26.py · Planeación Financiera ·
  cifras en dólares · V1: consistencia acumulada · V2: incremento vs ppto ajustado ·
  V3: coherencia vs 2025 · V4: índices vs factores · V5: vs ppto anual · V6: calidad de datos</footer>

</body>
</html>"""

    with open(ruta, "w", encoding="utf-8") as f:
        f.write(html)
