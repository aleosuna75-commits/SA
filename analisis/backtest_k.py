# -*- coding: utf-8 -*-
"""
Backtest walk-forward para elegir k (credibilidad).

Para cada mes del periodo de prueba: calibra SOLO con lo anterior a ese mes,
predice todos los partidos del mes y califica. Nunca ve el futuro.

Encogimiento hacia la media de la liga (ataque=1, defensa=1), que es el unico
blanco bien definido para todo el historico: PRIORS_ILUSTRATIVOS solo existe
para los 18 equipos actuales, no para Veracruz, Morelia o Chiapas.

    Z = w / (w + k)      w = peso efectivo del equipo a la fecha de corte
    log(rating) = Z * log(MLE) + (1 - Z) * log(1) = Z * log(MLE)
"""
import math, sys, time
from collections import defaultdict
from datetime import date

sys.path.insert(0, "/tmp/claude-0/-home-user-SA/e5565e27-c69c-55a1-a036-90aa77074faa/scratchpad")
import numpy as np
import cerebro as C

KS = [None, 1, 2, 3, 5, 10, 20]        # None = sin credibilidad (hoy)
INICIO = date(2023, 8, 1)              # 3 temporadas de prueba


def pesos(partidos, corte):
    w = defaultdict(float)
    for p in partidos:
        f = math.exp(-C.XI_DECAIMIENTO * (corte - p["fecha"]).days)
        f *= C.PESO_LIGUILLA if p["fase"] == "liguilla" else 1.0
        w[p["local"]] += f
        w[p["visitante"]] += f
    return w


def encoger(ratings, w, k):
    if k is None:
        return ratings
    out = {}
    for e, (a, d) in ratings.items():
        Z = w.get(e, 0.0) / (w.get(e, 0.0) + k)
        out[e] = (math.exp(Z * math.log(a)), math.exp(Z * math.log(d)))
    return out


def main():
    partidos = C.cargar_historico("/home/user/SA/historico_ligamx.csv")
    partidos.sort(key=lambda p: p["fecha"])
    fin = partidos[-1]["fecha"]

    # meses de evaluación
    meses = []
    y, m = INICIO.year, INICIO.month
    while date(y, m, 1) <= fin:
        meses.append(date(y, m, 1))
        m += 1
        if m == 13:
            y, m = y + 1, 1

    acum = {k: {"brier": 0.0, "logloss": 0.0, "rps": 0.0, "n": 0, "aciertos": 0} for k in KS}
    t0 = time.time()

    for i, ini in enumerate(meses):
        fin_mes = meses[i + 1] if i + 1 < len(meses) else date(fin.year, fin.month, 28) if False else None
        prueba = [p for p in partidos if p["fecha"] >= ini and (fin_mes is None or p["fecha"] < fin_mes)]
        entrena = [p for p in partidos if p["fecha"] < ini]
        if not prueba or len(entrena) < 500:
            continue

        reg = [p for p in entrena if p["fase"] == "regular"]
        C.BASE_HOME_GOALS = sum(p["gl"] for p in reg) / len(reg)
        C.BASE_AWAY_GOALS = sum(p["gv"] for p in reg) / len(reg)
        base = C.fit_dixon_coles(entrena, hoy=ini)
        w = pesos(entrena, ini)

        for k in KS:
            r = encoger(base, w, k)
            for p in prueba:
                if p["local"] not in r or p["visitante"] not in r:
                    continue
                lam_l, lam_v, _ = C.lambdas_partido(p["local"], p["visitante"], r,
                                                    jornada_actual=False)
                M = C.matriz_marcadores(lam_l, lam_v)
                pr = (float(np.tril(M, -1).sum()), float(np.trace(M)), float(np.triu(M, 1).sum()))
                gl, gv = p["gl"], p["gv"]
                o = (1, 0, 0) if gl > gv else ((0, 1, 0) if gl == gv else (0, 0, 1))
                a = acum[k]
                a["brier"] += sum((x - y_) ** 2 for x, y_ in zip(pr, o))
                idx = o.index(1)
                a["logloss"] -= math.log(max(pr[idx], 1e-12))
                # RPS: respeta el orden Local > Empate > Visita
                cp = np.cumsum(pr); co = np.cumsum(o)
                a["rps"] += float(np.sum((cp[:-1] - co[:-1]) ** 2)) / 2
                a["aciertos"] += int(int(np.argmax(pr)) == idx)
                a["n"] += 1

    print(f"\nPeriodo de prueba: {INICIO} -> {fin}   ({acum[KS[0]]['n']} partidos, "
          f"{time.time()-t0:.0f}s)\n")
    print(f"{'k':>6s} {'Brier':>8s} {'log-loss':>9s} {'RPS':>8s} {'aciertos':>9s}")
    print("-" * 46)
    mejor = None
    for k in KS:
        a = acum[k]
        n = a["n"]
        b, l, r_, ac = a["brier"]/n, a["logloss"]/n, a["rps"]/n, a["aciertos"]/n
        et = "  <- hoy" if k is None else ""
        if mejor is None or b < mejor[1]:
            mejor = (k, b)
        print(f"{str(k):>6s} {b:8.4f} {l:9.4f} {r_:8.4f} {ac:8.1%}{et}")
    print("-" * 46)
    print(f"azar   {2/3:8.4f} {math.log(3):9.4f} {0.2222:8.4f} {'':8s}")
    print(f"\nMejor Brier: k = {mejor[0]}")


if __name__ == "__main__":
    main()
