"""Precio de traspaso pagado frente al valor de Transfermarkt.

El valor de TM es una estimación; lo que un club paga es otra cosa. Aquí se modela el cociente
cuota pagada / valor de TM en la fecha, con los ~35 mil traspasos que tienen ambos datos, usando los
mismos rasgos del jugador (foto del 1-jul previa al traspaso) más quién vende.

Sesgo que no se puede quitar: sólo se observan traspasos CON cuota divulgada. Los libres, los préstamos
y los jugadores que nadie compró no están. El resultado se lee como "si se vende con cuota, cuánto se
paga típicamente por un jugador así", no como el precio al que cualquiera podría comprarlo hoy.
"""
import numpy as np
import pandas as pd
import lightgbm as lgb

import modelo as M

# Fuera los rasgos de "fichaje reciente": para un traspaso fechado el 1-jul contendrían la propia cuota a predecir.
FUGA = ["fichado12", "log_fee", "fee_x"]
RASGOS_P = [r for r in M.RASGOS if r not in FUGA] + ["lv_t", "meses_foto", "nivel_de", "pais_de"]
CAT_P = M.CATEGORICAS + ["pais_de"]
CUANTILES = [0.1, 0.5, 0.9]


def tabla_traspasos(crudos):
    """Une los traspasos de las dos fuentes: jugador, fecha, clubes, tipo, valor de TM en la fecha y cuota."""
    b = pd.read_csv(crudos / "extra" / "salimt_transfer_history" / "transfer_history.csv.gz", low_memory=False)
    b = pd.DataFrame({"player_id": b.player_id, "fecha": pd.to_datetime(b.transfer_date, errors="coerce"), "de_id": b.from_team_id,
                      "a_id": b.to_team_id, "de": b.from_team_name, "a": b.to_team_name, "tipo": b.transfer_type,
                      "valor_t": b.value_at_transfer.astype(float), "pagado": b.transfer_fee.astype(float)})
    a = pd.read_csv(crudos / "transfers.csv.gz", parse_dates=["transfer_date"])
    a = pd.DataFrame({"player_id": a.player_id, "fecha": a.transfer_date, "de_id": a.from_club_id, "a_id": a.to_club_id,
                      "de": a.from_club_name, "a": a.to_club_name, "tipo": "Transfer", "valor_t": a.market_value_in_eur, "pagado": a.transfer_fee})
    # Tercera fuente (Zenodo, CC BY 4.0; 50 ligas, 2005-2024): sólo traspasos definitivos con cuota y valor.
    c = pd.read_csv(crudos / "extra" / "zenodo_cumetti_transfers" / "football_transfers_data.csv.gz", low_memory=False)
    c = c[(c.fee_cleaned > 0) & (c.market_value > 0) & ~c.fee.astype(str).str.lower().str.contains("loan")]
    c = pd.DataFrame({"player_id": c.player_id, "fecha": pd.to_datetime(c.year.astype(str) + np.where(c.transfer_period == "Summer", "-07-01", "-01-15")),
                      "de_id": c.source_club_id, "a_id": c.target_club_id, "de": c.source_club, "a": c.target_club, "tipo": "Transfer",
                      "valor_t": c.market_value * 1e6, "pagado": c.fee_cleaned * 1e6})
    t = pd.concat([b.assign(orden=0), a[a.pagado > 0].assign(orden=1), c.assign(orden=2)])   # de A y C sólo los que traen cuota
    t = t[t.fecha.notna()]
    t["ventana"] = t.fecha.dt.year + (t.fecha.dt.month >= 5)   # verano de Y y enero de Y+1 caen en ventanas distintas
    t = t.sort_values(["orden", "pagado"], ascending=[True, False])
    # el mismo traspaso en dos fuentes: se queda el de fecha exacta, pero con la cuota si la otra fuente la trae
    con_cuota = t[t.pagado > 0].drop_duplicates(["player_id", "a_id", "ventana"]).set_index(["player_id", "a_id", "ventana"])[["pagado", "valor_t"]]
    t = t.drop_duplicates(["player_id", "a_id", "ventana"]).set_index(["player_id", "a_id", "ventana"])
    falta = (t.pagado <= 0) | t.pagado.isna()
    t.loc[falta, "pagado"] = con_cuota.pagado.reindex(t.index)[falta].fillna(t.pagado[falta])
    sin_valor = ~(t.valor_t > 0)
    t.loc[sin_valor, "valor_t"] = con_cuota.valor_t.reindex(t.index)[sin_valor].fillna(t.valor_t[sin_valor])
    return t.reset_index().drop(columns=["orden", "ventana"]).sort_values(["player_id", "fecha"])


def _contexto(d, clubes, codigos):
    d["nivel_de"] = d.de_id.map(clubes.nivel).astype(float)
    d["pais_de"] = d.de_id.map(clubes.pais).map(codigos)
    return d


def muestra(f, t, clubes, corte):
    """Traspasos con cuota y valor, pegados a la foto del 1-jul inmediatamente anterior del jugador."""
    p = t[(t.tipo == "Transfer") & (t.pagado > 0) & (t.valor_t > 0) & (t.fecha <= corte)].copy()
    p["anio"] = p.fecha.dt.year - (p.fecha.dt.month < 7)     # traspaso desde el 1-jul del año Y -> foto Y
    p = p.merge(f[["player_id", "anio"] + M.RASGOS], on=["player_id", "anio"], how="inner")
    p["r"] = np.log(p.pagado / p.valor_t)
    p["lv_t"] = np.log(p.valor_t)
    p["meses_foto"] = (p.fecha - pd.to_datetime(p.anio.astype(str) + "-07-01")).dt.days / 30.4
    codigos = {c: i for i, c in enumerate(sorted(x for x in clubes.pais.dropna().unique() if x))}
    return _contexto(p, clubes, codigos), codigos


def _ajustar(d, q, rondas=300):
    par = dict(objective="quantile", alpha=q, learning_rate=0.04, num_leaves=31, min_data_in_leaf=40, feature_fraction=0.8,
               bagging_fraction=0.8, bagging_freq=1, lambda_l2=1.0, verbose=-1, num_threads=4, seed=7)
    return lgb.train(par, lgb.Dataset(d[RASGOS_P], label=d.r, categorical_feature=CAT_P), num_boost_round=rondas)


def retro(p, anios=range(2018, 2026)):
    """Para cada año T: entrena con traspasos anteriores al 1-jul de T y predice los de la temporada T (jul T a jun T+1)."""
    filas, zs = [], []
    for T in anios:
        ent, pru = p[p.anio < T], p[p.anio == T]
        if len(pru) < 300:
            continue
        m = {q: _ajustar(ent, q) for q in CUANTILES}
        P = {q: m[q].predict(pru[RASGOS_P]) for q in CUANTILES}
        sesgo = ent[ent.anio >= T - 3].r.median()
        e = lambda v: float(np.exp(np.median(np.abs(v))) - 1)
        z = np.where(pru.r >= P[0.5], (pru.r - P[0.5]) / np.maximum(P[0.9] - P[0.5], 0.05), (P[0.5] - pru.r) / np.maximum(P[0.5] - P[0.1], 0.05))
        zs.append(pd.DataFrame({"T": T, "z": z}))
        joven = (pru.edad_f < 22).to_numpy()
        filas.append({"temporada": int(T), "n": int(len(pru)), "modelo": e(P[0.5] - pru.r), "tm": e(-pru.r), "tm_ajustado": e(sesgo - pru.r),
                      "modelo_sub22": e((P[0.5] - pru.r)[joven]), "tm_sub22": e(-pru.r[joven]), "n_sub22": int(joven.sum()),
                      "orden": float(pd.Series(P[0.5]).corr(pru.r.reset_index(drop=True), method="spearman"))})
    zs = pd.concat(zs)
    sal = []
    for nivel in (0.8, 0.95):
        sal += [float(zs.z.quantile(nivel)), float(np.mean([(g.z <= zs[zs["T"] != T].z.quantile(nivel)).mean() for T, g in zs.groupby("T")]))]
    return (filas, *sal)                                      # filas, k80, cobertura80, k95, cobertura95


def proyectar(p, codigos, act, clubes, k, k95):
    """Precio estimado hoy para cada jugador vigente: (pesimista, mediana, optimista) como múltiplos del valor de TM."""
    m = {q: _ajustar(p, q) for q in CUANTILES}
    d = act.copy()
    d["lv_t"] = np.log(d.valor)
    d["meses_foto"] = float(p.meses_foto.median())
    d["de_id"] = d.club_actual
    d = _contexto(d, clubes, codigos)
    P = {q: m[q].predict(d[RASGOS_P]) for q in CUANTILES}
    bajo, alto = np.maximum(P[0.5] - P[0.1], 0.05), np.maximum(P[0.9] - P[0.5], 0.05)
    return np.exp(np.column_stack([P[0.5] - k95 * bajo, P[0.5] - k * bajo, P[0.5], P[0.5] + k * alto, P[0.5] + k95 * alto]))


def resumen_por_grupo(p):
    """Cociente mediano cuota/valor observado, por edad y por liga vendedora (últimos 8 años)."""
    r = p[p.anio >= p.anio.max() - 8]
    edad = r.groupby(pd.cut(r.edad_f, [14, 19, 21, 23, 26, 29, 45], labels=["≤19", "20-21", "22-23", "24-26", "27-29", "30+"]), observed=True).r
    return [{"grupo": str(g), "n": int(v.size), "multiplo": round(float(np.exp(v.median())), 2),
             "bajo": round(float(np.exp(v.quantile(0.25))), 2), "alto": round(float(np.exp(v.quantile(0.75))), 2)} for g, v in edad]
