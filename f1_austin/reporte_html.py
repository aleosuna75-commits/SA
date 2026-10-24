"""Genera el reporte HTML con estilo 'Texas F1' a partir del resultado del modelo."""
import html
from datetime import datetime

import numpy as np
import pandas as pd

ETIQUETAS = {
    "fp1_gap": "Gap mejor vuelta FP1 (%)", "fp1_rank": "Posición FP1", "fp1_laps": "Vueltas FP1",
    "fp1_ideal_gap": "Vuelta ideal FP1 (%)", "fp1_s1_gap": "Sector 1 FP1", "fp1_s2_gap": "Sector 2 FP1",
    "fp1_s3_gap": "Sector 3 FP1", "fp1_trap_delta": "Speed trap FP1", "fp1_soft_gap": "Vuelta con blando FP1",
    "fp1_long_gap": "Tanda larga FP1", "fp1_top3_spread": "Consistencia FP1",
    "fp2_gap": "Gap mejor vuelta FP2 (%)", "fp2_rank": "Posición FP2", "fp2_laps": "Vueltas FP2",
    "fp2_ideal_gap": "Vuelta ideal FP2 (%)", "fp2_ideal_rank": "Rank vuelta ideal FP2",
    "fp2_s1_gap": "Sector 1 FP2", "fp2_s2_gap": "Sector 2 FP2", "fp2_s3_gap": "Sector 3 FP2",
    "fp2_trap_delta": "Speed trap FP2", "fp2_i1_delta": "Vel. intermedia 1 FP2", "fp2_i2_delta": "Vel. intermedia 2 FP2",
    "fp2_soft_gap": "Vuelta con blando FP2", "fp2_long_gap": "Tanda larga FP2 (%)", "fp2_long_rank": "Rank tanda larga FP2",
    "fp2_top3_spread": "Consistencia FP2", "fp2_track_temp": "Temp. pista FP2",
    "comb_gap": "Gap mejor vuelta FP1+FP2 (%)", "comb_rank": "Rank mejor vuelta FP1+FP2",
    "main_gap": "Gap sesión principal (%)", "main_rank": "Rank sesión principal", "fp_improve": "Mejora FP1→FP2",
    "ideal_best_gap": "Mejor vuelta ideal (%)", "laps_total": "Vueltas totales", "long_gap_best": "Mejor tanda larga",
    "fp_rain": "Lluvia en prácticas", "team_best_gap": "Gap del equipo (%)", "team_mean_gap": "Gap medio del equipo",
    "teammate_delta": "Delta vs compañero", "team_fp_rank": "Rank del equipo en FP", "sprint": "Fin de semana sprint",
    "n_drivers": "Nº de pilotos", "h_q_last": "Qualy anterior", "h_q_mean3": "Qualy media últimas 3",
    "h_q_mean5": "Qualy media últimas 5", "h_q_mean10": "Qualy media últimas 10", "h_q_season": "Qualy media temporada",
    "h_q3_rate10": "% Q3 últimas 10", "h_q_std10": "Volatilidad en qualy", "h_r_mean5": "Carrera media últimas 5",
    "h_pts_season": "Puntos temporada", "h_pts_rank": "Posición campeonato", "h_dnf_rate10": "% abandonos",
    "h_experience": "Experiencia (qualys)", "h_circ_mean": "Qualy media en el circuito",
    "h_circ_best": "Mejor qualy en el circuito", "h_circ_n": "Visitas al circuito",
    "h_team_q_mean5": "Qualy media equipo últimas 5", "h_fp_to_q_driver": "Sesgo FP→Qualy piloto",
    "h_fp_to_q_team": "Sesgo FP→Qualy equipo", "year_idx": "Temporada", "is_2026_regs": "Reglamento 2026",
}

STAR = ('<svg viewBox="0 0 24 24" class="{c}" aria-hidden="true"><path d="M12 1.8l2.95 6.9 7.45.65-5.65 4.9 '
        '1.7 7.3L12 17.7l-6.45 3.85 1.7-7.3L1.6 9.35l7.45-.65z"/></svg>')


def e(x):
    return html.escape(str(x))


def fnum(x, d=1, suf=""):
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{d}f}{suf}"


def fint(x):
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{int(x)}"


def pct(x):
    return f"{100 * x:.0f}%" if x >= 0.005 else "<1%"


def color(row):
    c = row.get("team_colour")
    return f"#{c}" if isinstance(c, str) and len(c) == 6 else "#888"


def seccion_real(obj, base):
    """Compara contra el resultado real de la qualy si ya está en cache (qualy_real_1297.json)."""
    import json
    f = base / "cache" / "qualy_real_1297.json"
    if not f.exists():
        return ""
    real = pd.DataFrame(json.loads(f.read_text()))
    if real.empty or "position" not in real:
        return ""
    real = real[["driver_number", "position"]].rename(columns={"position": "real"})
    real["real"] = pd.to_numeric(real.real, errors="coerce")
    v1_f = base / "prediccion_pre_qualy_v1.csv"
    v1 = pd.read_csv(v1_f)[["driver_number", "pred_rank"]].rename(columns={"pred_rank": "v1"}) if v1_f.exists() else None
    t = obj[["driver_number", "name_acronym", "team_name", "team_colour", "pred_rank"]].merge(real, on="driver_number", how="left")
    if v1 is not None:
        t = t.merge(v1, on="driver_number", how="left")
    t = t.sort_values("real", na_position="last")
    top_real = set(t[t.real <= 10].driver_number)
    hits_v2 = len(top_real & set(t[t.pred_rank <= 10].driver_number))
    hits_v1 = len(top_real & set(t[t.v1 <= 10].driver_number)) if v1 is not None else None
    pole = t.iloc[0]
    filas = []
    for _, r in t.iterrows():
        ok = lambda col: "hit" if (r.real <= 10) == (r[col] <= 10) else "miss"
        v1c = (f'<td class="num {ok("v1")}">{int(r.v1)}</td>' if v1 is not None and pd.notna(r.v1) else "<td></td>")
        filas.append(f"""<tr class="{'in' if r.real <= 10 else ''}"><td class="num">{fint(r.real)}</td>
          <td><span class="chip" style="background:{color(r)}"></span><b>{e(r.name_acronym)}</b><span class="sub">{e(r.team_name)}</span></td>
          {v1c}<td class="num {ok('pred_rank')}">{int(r.pred_rank)}</td></tr>""")
    k1 = (f'<div class="kpi"><b>{hits_v1}/10</b><span>Aciertos del pronóstico pre-qualy (v1, commit 14:29 UTC)</span></div>'
          if hits_v1 is not None else "")
    return f"""
<section>
  <h2>{STAR.format(c="st")}Resultado real vs. pronóstico</h2>
  <p class="lead">La v1 se publicó (commit en git) antes de la FP3 y de la qualy. La v2 incluye los arreglos de la auditoría
  y se generó <b>durante/después</b> de la qualy, con los mismos datos de FP1/FP2 (no usa el resultado), así que no cuenta como pronóstico previo.</p>
  <div class="kpis">
    <div class="kpi"><b>{e(pole.name_acronym)}</b><span>Pole real</span></div>
    {k1}
    <div class="kpi"><b>{hits_v2}/10</b><span>Aciertos del modelo corregido (v2)</span></div>
    <div class="kpi"><b>{fila_real_media(t)}</b><span>Error medio de posición (v2)</span></div>
  </div>
  <div class="tw" style="margin-top:12px"><table class="real">
    <tr><th>Real</th><th>Piloto</th>{'<th>Pred v1</th>' if v1 is not None else ''}<th>Pred v2</th></tr>
    {''.join(filas)}
  </table></div>
</section>"""


def fila_real_media(t):
    x = t.dropna(subset=["real"])
    return f"{(x.real - x.pred_rank).abs().mean():.1f}"


def generar_html(R, ruta):
    obj, tabla, imp, cota, por_gp = R["obj"], R["tabla"], R["imp"], R["cota"], R["por_gp"]
    mejor = R["mejor"]
    fila_mejor = tabla[tabla.modelo == mejor].iloc[0]
    base = tabla[tabla.modelo.str.startswith("Baseline")].top10_hits.max()

    cota_med = cota.groupby("code").pos.agg(["mean", "min", "count"])
    obj = obj.copy()
    obj["cota_mean"] = obj.name_acronym.map(cota_med["mean"])
    obj["cota_best"] = obj.name_acronym.map(cota_med["min"])
    obj["cota_n"] = obj.name_acronym.map(cota_med["count"]).fillna(0)

    # ---------------- Parrilla Top 10 ----------------
    grid = []
    for _, r in obj.head(10).iterrows():
        lado = "izq" if r.pred_rank % 2 else "der"
        grid.append(f"""
        <div class="slot {lado}" style="--tc:{color(r)}">
          <div class="pnum">P{int(r.pred_rank)}</div>
          <div class="pinfo">
            <div class="pname">{e(r.full_name.title() if isinstance(r.full_name, str) else r.name_acronym)}</div>
            <div class="pteam">{e(r.team_name)}</div>
          </div>
          <div class="pprob"><span>{pct(r.p_q3)}</span><small>Q3</small></div>
        </div>""")

    # ---------------- Tabla completa ----------------
    filas = []
    for _, r in obj.iterrows():
        barra = f'<div class="bar"><i style="width:{100 * r.p_q3:.0f}%"></i></div>'
        filas.append(f"""<tr class="{'in' if r.pred_rank <= 10 else ''}">
          <td class="num">{int(r.pred_rank)}</td>
          <td><span class="chip" style="background:{color(r)}"></span><b>{e(r.name_acronym)}</b>
              <span class="sub">{e(r.team_name)}</span></td>
          <td class="num">{fint(r.fp1_rank)}<span class="sub">+{fnum(r.fp1_gap, 2)}%</span></td>
          <td class="num">{fint(r.fp2_rank)}<span class="sub">+{fnum(r.fp2_gap, 2)}%</span></td>
          <td class="num">{fint(r.fp2_long_rank)}</td>
          <td class="num">{fnum(r.h_q_mean5, 1)}</td>
          <td class="num">{fnum(r.cota_mean, 1)}<span class="sub">{'' if r.cota_n == 0 else f'{int(r.cota_n)} vis.'}</span></td>
          <td class="num">{int(r.pos_p10)}–{int(r.pos_p90)}</td>
          <td class="prob">{barra}<span>{pct(r.p_q3)}</span></td>
          <td class="num">{pct(r.p_pole)}</td>
        </tr>""")

    # ---------------- Comparación de modelos ----------------
    mod = []
    for _, r in tabla.iterrows():
        cls = "win" if r.modelo == mejor else ("base" if r.modelo.startswith("Baseline") else "")
        mod.append(f"""<tr class="{cls}"><td>{'★ ' if cls == 'win' else ''}{e(r.modelo)}</td>
          <td class="num">{r.top10_hits:.2f}</td><td class="num">{r.top10_hits_2026:.2f}</td>
          <td class="num">{r.spearman:.3f}</td><td class="num">{r.mae:.2f}</td>
          <td class="num">{100 * r.pole_acc:.0f}%</td><td class="num">{r.top3_hits:.2f}</td></tr>""")

    # ---------------- Importancia de variables ----------------
    imp_top = imp.head(15)
    mx = imp_top.max() if len(imp_top) else 1
    imps = "".join(
        f'<div class="irow"><span>{e(ETIQUETAS.get(k, k))}</span>'
        f'<div class="ibar"><i style="width:{100 * v / mx:.0f}%"></i></div><b>{100 * v:.1f}%</b></div>'
        for k, v in imp_top.items())

    # ---------------- Validación por GP 2026 ----------------
    g26 = por_gp[por_gp.year >= 2026]
    val = "".join(
        f'<div class="vcol" title="{e(r.circuit)}: {r.top10_hits}/10"><div class="vbar" style="height:{r.top10_hits * 10}%">'
        f'<span>{r.top10_hits}</span></div><small>{e(r.circuit[:8])}</small></div>'
        for _, r in g26.iterrows())

    # ---------------- Historia COTA ----------------
    poles = cota[cota.pos == 1].sort_values("season", ascending=False)
    pol = "".join(f"<li><b>{r.season}</b> {e(r['name'])} <span class='sub'>{e(r.team)}</span></li>"
                  for _, r in poles.iterrows())
    reyes = (cota[cota.code.isin(obj.name_acronym)].groupby("code").pos
             .agg(top10=lambda s: (s <= 10).sum(), n="count", media="mean")
             .sort_values(["media"]).head(8))
    rey = "".join(f"<tr><td><b>{e(k)}</b></td><td class='num'>{int(r.n)}</td><td class='num'>{int(r.top10)}</td>"
                  f"<td class='num'>{r.media:.1f}</td></tr>" for k, r in reyes.iterrows())

    # Zona de burbuja
    burbuja = obj[(obj.p_q3 > 0.25) & (obj.p_q3 < 0.75)]
    burb = ", ".join(f"<b>{e(r.name_acronym)}</b> ({pct(r.p_q3)})" for _, r in burbuja.iterrows())

    favorito = obj.sort_values("p_pole", ascending=False).iloc[0]
    real_html = seccion_real(obj, ruta.parent)
    n_train = len(R["train"])
    n_gp = R["train"].meeting_key.nunique()
    n_vars = R.get("n_vars", len(ETIQUETAS))
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M UTC")

    doc = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Qualy Austin 2026</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Rye&family=Titillium+Web:wght@400;600;700;900&display=swap" rel="stylesheet">
<style>
:root{{--navy:#0a1a33;--navy2:#102849;--ink:#f4efe6;--muted:#b9b1a3;--red:#c8102e;--red2:#ff3b4f;
--sand:#d6a96b;--leather:#8a5a2b;--line:rgba(214,169,107,.25);--card:#0f2240}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--navy);color:var(--ink);font-family:"Titillium Web",system-ui,sans-serif;
background-image:radial-gradient(circle at 20% 0%,rgba(200,16,46,.18),transparent 40%),
radial-gradient(circle at 100% 30%,rgba(214,169,107,.10),transparent 35%)}}
.wrap{{max-width:1100px;margin:0 auto;padding:0 16px}}
h1,h2,.west{{font-family:"Rye",serif;font-weight:400;letter-spacing:.5px}}
.hero{{border-bottom:6px solid var(--red);position:relative;overflow:hidden;
background:linear-gradient(90deg,var(--navy2) 0 34%,transparent 34%),
repeating-linear-gradient(180deg,#f4efe6 0 26px,var(--red) 26px 52px);}}
.hero .shade{{background:linear-gradient(90deg,rgba(10,26,51,.0) 0 34%,rgba(10,26,51,.88) 34%)}}
.hero .wrap{{display:grid;grid-template-columns:34% 1fr;min-height:250px;align-items:center}}
.bigstar{{width:150px;fill:#f4efe6;filter:drop-shadow(0 4px 0 rgba(0,0,0,.35));margin:auto}}
.htext{{padding:28px 0 28px 28px}}
.kicker{{color:var(--sand);text-transform:uppercase;letter-spacing:3px;font-weight:700;font-size:13px}}
h1{{font-size:clamp(30px,5vw,54px);margin:6px 0;line-height:1.05}}
.hsub{{font-size:18px;color:var(--ink)}}
.hsub b{{color:var(--sand)}}
.tag{{display:inline-block;margin-top:12px;background:var(--red);padding:4px 12px;border-radius:2px;font-weight:700;
text-transform:uppercase;letter-spacing:2px;font-size:12px}}
section{{margin:34px 0}}
h2{{font-size:26px;margin:0 0 4px;display:flex;align-items:center;gap:10px}}
h2 .st{{width:22px;fill:var(--red2)}}
.lead{{color:var(--muted);margin:0 0 16px}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}
.kpi{{background:var(--card);border:1px solid var(--line);border-top:4px solid var(--red);padding:14px;border-radius:4px}}
.kpi b{{display:block;font-size:28px;font-weight:900;line-height:1.1}}
.kpi span{{color:var(--muted);font-size:13px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px 22px;padding:20px;background:
repeating-linear-gradient(90deg,#1b1b1b 0 40px,#202020 40px 80px);border-radius:6px;border:2px solid var(--leather)}}
.slot{{display:flex;align-items:center;gap:12px;background:linear-gradient(90deg,var(--card),#0b1a30);
border-left:6px solid var(--tc);padding:10px 12px;border-radius:3px;box-shadow:0 2px 0 rgba(0,0,0,.4)}}
.slot.der{{margin-top:34px}}
.pnum{{font-family:"Rye";font-size:26px;color:var(--sand);min-width:52px}}
.pinfo{{flex:1;min-width:0}}
.pname{{font-weight:900;font-size:17px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.pteam{{color:var(--muted);font-size:13px}}
.pprob{{text-align:right}} .pprob span{{font-weight:900;font-size:20px}} .pprob small{{display:block;color:var(--muted);font-size:11px}}
.tw{{overflow-x:auto;border:1px solid var(--line);border-radius:4px}}
table{{width:100%;border-collapse:collapse;font-size:14px;background:var(--card)}}
th{{background:var(--leather);color:#fff;text-align:left;padding:8px;font-size:12px;text-transform:uppercase;letter-spacing:1px;white-space:nowrap}}
td{{padding:7px 8px;border-top:1px solid rgba(255,255,255,.06);white-space:nowrap}}
td.num{{text-align:right;font-variant-numeric:tabular-nums}}
tr.in td:first-child{{color:var(--sand);font-weight:900}}
table.full tr:nth-child(12) td{{border-top:2px dashed var(--red2)}}
.sub{{display:block;color:var(--muted);font-size:11px}}
td b + .sub{{display:inline;margin-left:6px}}
.chip{{display:inline-block;width:4px;height:16px;margin-right:8px;vertical-align:-3px;border-radius:1px}}
.prob{{display:flex;align-items:center;gap:8px;min-width:140px}}
.bar{{flex:1;height:8px;background:rgba(255,255,255,.1);border-radius:4px;overflow:hidden}}
.bar i{{display:block;height:100%;background:linear-gradient(90deg,var(--red),var(--red2))}}
tr.win td{{background:rgba(200,16,46,.22);font-weight:700}} tr.base td{{color:var(--muted)}}
.two{{display:grid;grid-template-columns:1.2fr 1fr;gap:22px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:4px;padding:16px}}
td.hit{{color:#5fd38d;font-weight:700}} td.miss{{color:var(--red2);font-weight:700}}
table.real tr:nth-child(12) td{{border-top:2px dashed var(--red2)}}
.irow{{display:grid;grid-template-columns:190px 1fr 48px;gap:8px;align-items:center;font-size:13px;margin:5px 0}}
.ibar{{height:10px;background:rgba(255,255,255,.08);border-radius:5px;overflow:hidden}}
.ibar i{{display:block;height:100%;background:var(--sand)}}
.irow b{{text-align:right;font-variant-numeric:tabular-nums}}
.vchart{{display:flex;gap:4px;align-items:flex-end;height:160px;padding-top:10px}}
.vcol{{flex:1;display:flex;flex-direction:column;align-items:center;height:100%;justify-content:flex-end;min-width:0}}
.vbar{{width:100%;background:var(--red);border-radius:2px 2px 0 0;position:relative;min-height:4px}}
.vbar span{{position:absolute;top:-17px;left:0;right:0;text-align:center;font-size:11px;font-weight:700}}
.vcol small{{font-size:9px;color:var(--muted);writing-mode:vertical-rl;transform:rotate(180deg);margin-top:4px;height:48px}}
ul.poles{{list-style:none;padding:0;margin:0;columns:2;font-size:14px}} ul.poles li{{padding:3px 0;break-inside:avoid}}
ul.poles .sub{{display:inline;margin-left:4px}}
.note{{border-left:4px solid var(--sand);padding:10px 14px;background:rgba(214,169,107,.08);color:var(--ink);font-size:14px}}
footer{{border-top:6px solid var(--red);margin-top:40px;padding:20px 0 40px;color:var(--muted);font-size:13px}}
.rope{{height:10px;background:repeating-linear-gradient(45deg,var(--leather) 0 6px,var(--sand) 6px 12px);opacity:.6;margin:28px 0}}
@media(max-width:760px){{.hero .wrap{{grid-template-columns:1fr}} .hero{{background:var(--navy2)}}
.hero .shade{{background:none}} .bigstar{{width:80px;margin:20px 0 0 0}} .htext{{padding:10px 0 24px}}
.kpis{{grid-template-columns:1fr 1fr}} .grid{{grid-template-columns:1fr;padding:12px}} .slot.der{{margin-top:0}}
.two{{grid-template-columns:1fr}} .irow{{grid-template-columns:130px 1fr 44px}} ul.poles{{columns:1}}}}
</style></head><body>
<header class="hero"><div class="shade"><div class="wrap">
  {STAR.format(c="bigstar")}
  <div class="htext">
    <div class="kicker">Circuit of the Americas · Austin, Texas</div>
    <h1>Howdy, Austin!<br>Pronóstico de Qualy</h1>
    <div class="hsub">United States Grand Prix 2026 · Sábado 24 de octubre · <b>4:00 PM CT</b></div>
    <span class="tag">Top 10 · modelo con FP1 + FP2 + historial</span>
  </div></div></div>
</header>

<main class="wrap">
<section>
  <div class="kpis">
    <div class="kpi"><b>{e(favorito.name_acronym)}</b><span>Favorito a la pole ({pct(favorito.p_pole)})</span></div>
    <div class="kpi"><b>{fila_mejor.top10_hits:.1f}/10</b><span>Aciertos promedio en Top 10 (validación)</span></div>
    <div class="kpi"><b>+{fila_mejor.top10_hits - base:.2f}</b><span>vs. mejor baseline de prácticas</span></div>
    <div class="kpi"><b>{n_gp} GPs</b><span>{n_train:,} filas piloto-GP · {n_vars} variables</span></div>
  </div>
</section>
{real_html}

<section>
  <h2>{STAR.format(c="st")}La parrilla según el modelo</h2>
  <p class="lead">Top 10 pronosticado (los que pasan a Q3). El porcentaje es la probabilidad de meterse a Q3 según 20,000 simulaciones.</p>
  <div class="grid">{''.join(grid)}</div>
  <p class="note" style="margin-top:14px">En la burbuja (25–75% de llegar a Q3): {burb or 'nadie — el corte se ve claro'}.</p>
</section>

<section>
  <h2>{STAR.format(c="st")}Tabla completa</h2>
  <p class="lead">Rango = posiciones entre los percentiles 10 y 90 de la simulación. Tanda larga = rank del ritmo de carrera en FP2. COTA = qualy media en Austin desde 2012.</p>
  <div class="tw"><table class="full">
    <tr><th>Pred</th><th>Piloto</th><th>FP1</th><th>FP2</th><th>Tanda larga</th><th>Qualy últ. 5</th><th>COTA</th><th>Rango</th><th>P(Q3)</th><th>P(Pole)</th></tr>
    {''.join(filas)}
  </table></div>
</section>

<div class="rope"></div>

<section>
  <h2>{STAR.format(c="st")}El rodeo de modelos</h2>
  <p class="lead">Validación walk-forward: cada GP de 2024–2026 se predijo entrenando <i>solo</i> con fines de semana anteriores.
  Se elige el modelo con más aciertos en el Top 10 (desempate: correlación de Spearman).</p>
  <div class="tw"><table>
    <tr><th>Modelo</th><th>Top 10 aciertos</th><th>Top 10 en 2026</th><th>Spearman</th><th>Error medio (pos.)</th><th>Pole acertada</th><th>Top 3 aciertos</th></tr>
    {''.join(mod)}
  </table></div>
</section>

<section class="two">
  <div class="card">
    <h2 style="font-size:20px">{STAR.format(c="st")}Qué pesa más</h2>
    <p class="lead">Importancia de variables (promedio de los modelos de árbol).</p>
    {imps}
  </div>
  <div class="card">
    <h2 style="font-size:20px">{STAR.format(c="st")}Así le fue en 2026</h2>
    <p class="lead">Aciertos del Top 10 por GP de esta temporada (predicción fuera de muestra).</p>
    <div class="vchart">{val}</div>
  </div>
</section>

<section class="two">
  <div class="card">
    <h2 style="font-size:20px">{STAR.format(c="st")}Poles en COTA</h2>
    <ul class="poles">{pol}</ul>
  </div>
  <div class="card">
    <h2 style="font-size:20px">{STAR.format(c="st")}Los que dominan Austin</h2>
    <p class="lead">Parrilla actual, mejor qualy media en COTA.</p>
    <div class="tw"><table><tr><th>Piloto</th><th>Visitas</th><th>Q3</th><th>Media</th></tr>{rey}</table></div>
  </div>
</section>

<section>
  <h2>{STAR.format(c="st")}Cómo se armó</h2>
  <div class="card" style="font-size:14px;line-height:1.6">
  <b>Datos:</b> OpenF1 (vueltas, sectores, speed traps, compuestos, stints y clima de FP1/FP2 de 2023–2026) y Jolpica/Ergast
  (todas las qualys y carreras 2018–2026, más Austin desde 2012).<br>
  <b>Variables ({n_vars}):</b> gap y posición de la mejor vuelta en FP1, FP2 y combinada; vuelta ideal por sectores; ranking por sector;
  speed trap e intermedias; mejor vuelta con blando; ritmo de tanda larga; consistencia; vueltas completadas; mejora FP1→FP2;
  ritmo del equipo y delta contra el compañero; forma en qualy (últimas 3/5/10, temporada, % de Q3, volatilidad); forma en carrera,
  puntos y posición en el campeonato; historial en el circuito; forma del equipo; sesgo histórico “prácticas → qualy” del piloto y del equipo
  (quién suele esconder ritmo el viernes); lluvia/temperatura y fin de semana sprint.<br>
  <b>Modelos comparados:</b> 2 baselines, Ridge, Random Forest, Extra Trees, Gradient Boosting, XGBoost, LightGBM, LightGBM LambdaRank,
  XGBoost Ranker y 2 ensambles. Ganó: <b>{e(mejor)}</b>. 2026 pesa 3× y 2025 1.5× por el nuevo reglamento.<br>
  <b>Probabilidades:</b> Monte Carlo con los errores reales de validación del modelo (ventana de ±2 posiciones predichas).<br>
  <b>Auditoría (v2):</b> se corrigieron una fuga de fechas en Las Vegas 2024 (zona horaria OpenF1 vs Jolpica), el sesgo FP→Qualy del
  equipo que veía al compañero en el mismo GP, una vuelta corrupta que borraba la FP1 de Miami 2026, nombres de equipos de Jolpica
  (Alpine, RB, Cadillac) y la calibración del Monte Carlo; además la validación ahora incluye a los pilotos que no marcaron tiempo.
  Seis experimentos de mejora (hiperparámetros, objetivo, ~90 variables nuevas, pesos, ensambles/stacking/CatBoost y modelos jerárquicos)
  no superaron al Random Forest de forma robusta.
  </div>
  <p class="note" style="margin-top:14px">Ojo: el modelo no ve la FP3 (sábado por la mañana), ni lluvia en la qualy, banderas rojas,
  límites de pista o penalizaciones de motor (éstas no cambian la posición de qualy, sólo la salida). La qualy F1 es ruidosa:
  incluso el mejor modelo acierta ~{fila_mejor.top10_hits:.0f} de 10.</p>
</section>
</main>
<footer><div class="wrap">Generado {ahora} · Datos: OpenF1 &amp; Jolpica-F1 · Proyecto no oficial, sin relación con Formula 1.
<span class="west" style="float:right;color:var(--sand)">Keep Austin Fast</span></div></footer>
</body></html>"""
    ruta.write_text(doc, encoding="utf-8")
    print("HTML ->", ruta)
