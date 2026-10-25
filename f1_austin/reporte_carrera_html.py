"""Reporte HTML 'Texas F1' del pronóstico de carrera (reutiliza estilos y helpers del reporte de qualy)."""
from datetime import datetime

import numpy as np
import pandas as pd

from reporte_html import CSS, ETIQUETAS, STAR, color, e, fint, fnum, pct

ETIQUETAS_CARRERA = {
    **ETIQUETAS,
    "grid": "Posición de salida", "q_pos": "Posición en qualy", "grid_penalty": "Penalización de parrilla",
    "grid_team_best": "Mejor salida del equipo", "q_gap": "Gap de qualy a la pole (%)", "q_team_best": "Mejor qualy del equipo",
    "q_teammate_delta": "Qualy vs compañero", "fp3_gap": "Gap mejor vuelta FP3", "fp3_rank": "Posición FP3",
    "fp3_long_gap": "Tanda larga FP3", "fp3_long_rank": "Rank tanda larga FP3", "fp3_ideal_gap": "Vuelta ideal FP3",
    "fp3_soft_gap": "Vuelta con blando FP3", "fp3_laps": "Vueltas FP3", "fp3_trap_delta": "Speed trap FP3",
    "long_gap_all": "Ritmo de carrera FP1-3 (%)", "long_rank_all": "Rank ritmo de carrera FP1-3",
    "long_team_best": "Ritmo de carrera del equipo", "fp_rank_all": "Mejor vuelta FP1-3 (rank)",
    "race_vs_q_pace": "Ritmo carrera vs qualy", "sprint_pos": "Resultado sprint", "r_mean3": "Carrera media últimas 3",
    "r_mean10": "Carrera media últimas 10", "r_season": "Carrera media temporada", "r_top10_rate10": "% Top 10 últimas 10",
    "r_podium_rate10": "% podios últimas 10", "r_gain_mean10": "Posiciones ganadas (media)", "r_finish_rate10": "% carreras terminadas",
    "r_last": "Carrera anterior", "r_circ_mean": "Carrera media en el circuito", "r_circ_gain": "Posiciones ganadas en el circuito",
    "circ_gain_abs": "Movilidad del circuito", "circ_grid_corr": "Peso de la parrilla en el circuito",
    "circ_dnf_rate": "% abandonos del circuito", "team_r_mean5": "Carrera media equipo últimas 5",
    "team_finish_rate5": "Fiabilidad del equipo",
}

EXTRA_CSS = """
.podium{display:grid;grid-template-columns:1fr 1.1fr 1fr;gap:14px;align-items:end;margin-top:8px}
.step{background:var(--card);border:1px solid var(--line);border-top:6px solid var(--tc);border-radius:4px;padding:14px;text-align:center}
.step .pos{font-family:"Rye",serif;font-size:42px;color:var(--sand);line-height:1}
.step .nm{font-weight:900;font-size:20px;margin-top:6px}
.step .tm{color:var(--muted);font-size:13px}
.step .pr{margin-top:8px;font-size:13px;color:var(--muted)} .step .pr b{color:var(--ink);font-size:16px}
.step.p1{padding-top:34px;background:linear-gradient(180deg,rgba(200,16,46,.25),var(--card))}
.step.p2{padding-top:22px} .step.p3{padding-top:12px}
.block{height:16px;background:repeating-linear-gradient(90deg,var(--leather) 0 14px,var(--sand) 14px 28px);opacity:.7;border-radius:0 0 4px 4px}
.order{display:grid;grid-template-columns:repeat(7,1fr);gap:8px;margin-top:14px}
.ord{background:var(--card);border-left:5px solid var(--tc);padding:8px 10px;border-radius:3px}
.ord .pos{font-family:"Rye",serif;color:var(--sand);font-size:20px}
.ord .nm{font-weight:900} .ord small{display:block;color:var(--muted);font-size:11px}
.pen{color:var(--red2);font-size:11px;font-weight:700;margin-left:4px}
.up{color:#5fd38d;font-weight:700} .down{color:var(--red2);font-weight:700}
@media(max-width:760px){.podium{grid-template-columns:1fr} .step.p1{order:-1} .order{grid-template-columns:1fr 1fr}}
"""


def generar_html(R, ruta):
    obj, tabla, imp, por_gp, base_gp, jr = R["obj"], R["tabla"], R["imp"], R["por_gp"], R["base_gp"], R["jr"]
    mejor = R["mejor"]
    fm = tabla[tabla.modelo == mejor].iloc[0]
    fg = tabla[tabla.modelo == R["base"]].iloc[0]                     # baseline más fuerte
    fml = tabla[tabla.modelo == R["mejor_ml"]].iloc[0]                # mejor modelo de ML
    supera = fml.ndcg10 > fg.ndcg10
    historia = R["historia"]
    obj = obj.copy()

    def mov(r):
        d = int(r.grid - r.pred_rank)
        return f'<span class="up">▲{d}</span>' if d > 0 else (f'<span class="down">▼{-d}</span>' if d < 0 else "=")

    # Podio y P4-P10
    top = obj.head(10).reset_index(drop=True)
    pod = []
    for i, cls in ((1, "p2"), (0, "p1"), (2, "p3")):
        r = top.iloc[i]
        pod.append(f"""<div><div class="step {cls}" style="--tc:{color(r)}">
          <div class="pos">P{int(r.pred_rank)}</div><div class="nm">{e(r.full_name.title() if isinstance(r.full_name, str) else r.name_acronym)}</div>
          <div class="tm">{e(r.team_name)} · sale P{int(r.grid)}</div>
          <div class="pr">Victoria <b>{pct(r.p_win)}</b> · Podio <b>{pct(r.p_podio)}</b></div></div><div class="block"></div></div>""")
    resto = "".join(
        f"""<div class="ord" style="--tc:{color(r)}"><span class="pos">P{int(r.pred_rank)}</span>
        <div class="nm">{e(r.name_acronym)}</div><small>Sale P{int(r.grid)} {mov(r)}</small><small>Top 10: {pct(r.p_top10)}</small></div>"""
        for _, r in top.iloc[3:].iterrows())

    filas = []
    for _, r in obj.iterrows():
        pen = f'<span class="pen">+{int(r.grid_penalty)} pen.</span>' if r.grid_penalty > 0 else ""
        filas.append(f"""<tr class="{'in' if r.pred_rank <= 10 else ''}">
          <td class="num">{int(r.pred_rank)}</td>
          <td><span class="chip" style="background:{color(r)}"></span><b>{e(r.name_acronym)}</b><span class="sub">{e(r.team_name)}</span></td>
          <td class="num">{int(r.grid)}{pen}</td><td class="num">{mov(r)}</td><td class="num">{int(r.pred_ml)}</td>
          <td class="num">{fint(r.long_rank_all)}<span class="sub">{('+' + fnum(r.long_gap_all, 2) + '%') if pd.notna(r.long_gap_all) else '—'}</span></td>
          <td class="num">{fint(r.fp3_rank)}</td>
          <td class="num">{fnum(r.r_mean10, 1)}</td>
          <td class="num">{fnum(r.r_circ_mean, 1)}</td>
          <td class="num">{int(r.pos_p10)}–{int(r.pos_p90)}</td>
          <td class="prob"><div class="bar"><i style="width:{100 * r.p_top10:.0f}%"></i></div><span>{pct(r.p_top10)}</span></td>
          <td class="num">{pct(r.p_podio)}</td><td class="num">{pct(r.p_win)}</td></tr>""")

    mod = []
    for _, r in tabla.iterrows():
        cls = "win" if r.modelo == mejor else ("base" if r.modelo.startswith("Baseline") else "")
        mod.append(f"""<tr class="{cls}"><td>{'★ ' if cls == 'win' else ''}{e(r.modelo)}</td>
          <td class="num">{r.ndcg10:.3f}</td><td class="num">{r.ndcg10_2026:.3f}</td><td class="num">{r.top10_hits:.2f}</td>
          <td class="num">{r.pos_exact10:.2f}</td><td class="num">{r.mae_top10:.2f}</td><td class="num">{r.spearman:.3f}</td>
          <td class="num">{100 * r.win_acc:.0f}%</td><td class="num">{r.podium_hits:.2f}</td></tr>""")

    imp_top = imp.head(15)
    mx = imp_top.max() if len(imp_top) else 1
    imps = "".join(f'<div class="irow"><span>{e(ETIQUETAS_CARRERA.get(k, k))}</span><div class="ibar"><i style="width:{100 * v / mx:.0f}%"></i></div>'
                   f'<b>{100 * v:.1f}%</b></div>' for k, v in imp_top.items())

    g26 = por_gp[por_gp.year >= 2026].merge(base_gp[["meeting_key", "ndcg10"]].rename(columns={"ndcg10": "ndcg_grid"}), on="meeting_key")
    val = "".join(
        f'<div class="vcol" title="{e(r.circuit)}: NDCG modelo {r.ndcg10:.2f} vs baseline {r.ndcg_grid:.2f}">'
        f'<div class="vbar" style="height:{max(r.ndcg10 - 0.5, 0) * 200:.0f}%;background:{"var(--red)" if r.ndcg10 >= r.ndcg_grid else "var(--leather)"}">'
        f'<span>{r.top10_hits}</span></div><small>{e(r.circuit[:8])}</small></div>' for _, r in g26.iterrows())
    gana = int((g26.ndcg10 > g26.ndcg_grid).sum()); empata = int((g26.ndcg10 == g26.ndcg_grid).sum())

    cota = jr[jr.circuit == "americas"]
    ganadores = cota[cota.pos == 1].sort_values("season", ascending=False)
    gan = "".join(f"<li><b>{r.season}</b> {e(r.code)} <span class='sub'>{e(r.team)} · salió P{int(r.grid)}</span></li>"
                  for _, r in ganadores.iterrows())
    movil = cota[cota.grid <= 10].gain.abs().mean()
    desde_pole = (ganadores.grid == 1).mean()

    fav = obj.sort_values("p_win", ascending=False).iloc[0]
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M UTC")
    css = CSS + EXTRA_CSS

    doc = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Carrera Austin 2026</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Rye&family=Titillium+Web:wght@400;600;700;900&display=swap" rel="stylesheet">
<style>
{css}</style></head><body>
<header class="hero"><div class="shade"><div class="wrap">
  {STAR.format(c="bigstar")}
  <div class="htext">
    <div class="kicker">Circuit of the Americas · Austin, Texas · 56 vueltas</div>
    <h1>Race Day, y'all!<br>Pronóstico de Carrera</h1>
    <div class="hsub">United States Grand Prix 2026 · Domingo 25 de octubre · <b>3:00 PM CT</b></div>
    <span class="tag">Top 10 y orden · parrilla + ritmo FP1-3 + historial</span>
  </div></div></div>
</header>
<main class="wrap">
<section><div class="kpis">
  <div class="kpi"><b>{e(fav.name_acronym)}</b><span>Favorito a ganar ({pct(fav.p_win)})</span></div>
  <div class="kpi"><b>{fm.top10_hits:.1f}/10</b><span>Aciertos promedio del Top 10 (validación)</span></div>
  <div class="kpi"><b>{fm.ndcg10:.3f}</b><span>NDCG@10 (quiénes + orden) · mejor ML {fml.ndcg10:.3f}</span></div>
  <div class="kpi"><b>{historia.meeting_key.nunique()} GPs</b><span>{len(historia):,} filas piloto-carrera · {R['n_vars']} variables</span></div>
</div></section>

<section>
  <h2>{STAR.format(c="st")}El podio pronosticado</h2>
  <p class="lead">Orden más probable de llegada. Probabilidades según 20,000 simulaciones con los errores reales del modelo en validación.</p>
  <div class="podium">{''.join(pod)}</div>
  <div class="order">{resto}</div>
</section>

<section>
  <h2>{STAR.format(c="st")}Tabla completa</h2>
  <p class="lead">▲▼ = posiciones que el pronóstico espera ganar o perder respecto a la salida. ML = orden según el mejor modelo de machine learning. Ritmo de carrera = gap de tanda larga en las prácticas donde la mayoría del campo hizo tandas largas (en Austin, FP2).
  Rango = percentiles 10-90 de la simulación.</p>
  <div class="tw"><table class="full">
    <tr><th>Pred</th><th>Piloto</th><th>Sale</th><th>Mov.</th><th>ML</th><th>Ritmo carrera</th><th>FP3</th><th>Carrera últ. 10</th><th>COTA</th><th>Rango</th><th>P(Top 10)</th><th>P(Podio)</th><th>P(Victoria)</th></tr>
    {''.join(filas)}
  </table></div>
</section>
<div class="rope"></div>
<section>
  <h2>{STAR.format(c="st")}El rodeo de modelos</h2>
  <p class="lead">Walk-forward 2024-2026: cada carrera se predijo entrenando sólo con carreras anteriores. Se elige por <b>NDCG@10</b>,
  que premia acertar quiénes entran al Top 10 <i>y en qué orden</i> (más peso arriba). También: posiciones exactas dentro del Top 10,
  error medio de posición de los que realmente terminaron en el Top 10, y Spearman de toda la parrilla.</p>
  <div class="tw"><table>
    <tr><th>Modelo</th><th>NDCG@10</th><th>NDCG@10 2026</th><th>Top 10 aciertos</th><th>Pos. exactas</th><th>Error Top 10</th><th>Spearman</th><th>Ganador</th><th>Podio aciertos</th></tr>
    {''.join(mod)}
  </table></div>
  {f'<p class="note" style="margin-top:12px"><b>Ganó el orden de qualy.</b> Ningún modelo de ML lo superó en NDCG@10: el mejor, {e(R["mejor_ml"])}, quedó a {fg.ndcg10 - fml.ndcg10:.3f}, dentro del ruido, aunque algunos ordenan un poco mejor a toda la parrilla (Spearman). Por eso el pronóstico oficial es el orden de qualy, y la columna «ML» de la tabla muestra dónde difiere el mejor modelo de ML.</p>' if not supera else ''}
  <p class="note" style="margin-top:12px">La parrilla de salida y la qualy son rivales duros: en F1 el orden de salida explica la mayor parte del resultado.
  El modelo la mejora usando el ritmo de carrera de las prácticas, la fiabilidad y la tendencia de cada piloto y equipo a ganar o perder posiciones.</p>
</section>
<section class="two">
  <div class="card"><h2 style="font-size:20px">{STAR.format(c="st")}Qué pesa más</h2>
  <p class="lead">Importancia de variables (modelos de árbol).</p>{imps}</div>
  <div class="card"><h2 style="font-size:20px">{STAR.format(c="st")}2026: mejor ML vs {e(fg.modelo.replace("Baseline: ", ""))}</h2>
  <p class="lead">Aciertos del Top 10 del mejor modelo de ML ({e(R["mejor_ml"])}) por carrera. Rojo = ordenó igual o mejor que el {e(fg.modelo.replace("Baseline: ", ""))} (NDCG); café = peor.
  Le ganó o empató en {gana + empata} de {len(g26)}.</p><div class="vchart">{val}</div></div>
</section>
<section class="two">
  <div class="card"><h2 style="font-size:20px">{STAR.format(c="st")}Ganadores en COTA</h2><ul class="poles">{gan}</ul></div>
  <div class="card"><h2 style="font-size:20px">{STAR.format(c="st")}Cómo se corre Austin</h2>
  <p class="lead">Desde 2018: el ganador salió desde la pole en {100 * desde_pole:.0f}% de las ediciones; los que salen en el Top 10 ganan
  o pierden en promedio {movil:.1f} posiciones. La subida a la curva 1 y la recta trasera permiten rebasar más que en muchos circuitos.</p></div>
</section>
<section><h2>{STAR.format(c="st")}Cómo se armó</h2>
  <div class="card" style="font-size:14px;line-height:1.6">
  <b>Base:</b> el modelo de qualy (auditado: sin fugas de fechas, sin ver al compañero del mismo GP, vueltas corruptas filtradas) más
  variables de carrera: parrilla real con penalizaciones (Lindblad −5, Colapinto −10, Bortoleto al fondo), qualy y gap a la pole,
  FP3, ritmo de tanda larga de las tres prácticas, sprint, resultados recientes, posiciones ganadas, % de carreras terminadas,
  fiabilidad del equipo, historial del piloto en el circuito y movilidad del circuito.<br>
  <b>Modelos comparados:</b> parrilla y qualy como baselines, Ridge, Random Forest, Extra Trees, Gradient Boosting, XGBoost, LightGBM,
  LightGBM LambdaRank, XGBoost Ranker y 2 ensambles. Ganó por NDCG@10: <b>{e(mejor)}</b>.
  </div>
  <p class="note" style="margin-top:14px">Ojo: una carrera es mucho más aleatoria que una qualy. El modelo no ve lluvia, safety cars,
  choques de la primera curva, estrategia de paradas ni fallas mecánicas puntuales (sólo la tasa histórica). Usa las probabilidades,
  no sólo el orden.</p>
</section>
</main>
<footer><div class="wrap">Generado {ahora} · Datos: OpenF1 &amp; Jolpica-F1 · Proyecto no oficial, sin relación con Formula 1.
<span class="west" style="float:right;color:var(--sand)">Don't mess with Texas</span></div></footer>
</body></html>"""
    ruta.write_text(doc, encoding="utf-8")
    print("HTML ->", ruta)
