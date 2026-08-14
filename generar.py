# -*- coding: utf-8 -*-
"""
================================================================================
  GENERADOR DE JORNADAS — Cerebro Liga MX 2026
================================================================================
Lee config/jornadas.json y produce un JSON por jornada en docs/datos/, más el
índice que consume el sitio.

Dos garantías que hacen esto seguro de correr cada semana:

  1. CORTE AUTOMÁTICO. Cada jornada se calibra SÓLO con partidos anteriores a
     su primera fecha. No importa cuánto histórico haya en el CSV: es
     imposible que un pronóstico vea resultados posteriores a sí mismo.

  2. SELLADO. Una jornada con origen "publicado" nunca se recalcula: sus
     probabilidades se leen del snapshot y sólo se le agregan los resultados.
     Es lo que hace medible el Brier a lo largo del torneo.

Uso:
    python generar.py                # regenera todo
    python generar.py --jornada 4    # sólo una

Flujo semanal:
    1. Agrega el bloque de la jornada en config/jornadas.json (fixture + ajustes)
    2. python generar.py
    3. Ya que se juegue, llena "resultado" de cada partido y vuelve a correr
    4. git add . && git commit && git push
================================================================================
"""
import argparse
import csv
import hashlib
import json
import math
from datetime import date, datetime
from pathlib import Path

import numpy as np

import cerebro_ligamx_2026 as C

RAIZ = Path(__file__).resolve().parent
CONFIG = RAIZ / "config" / "jornadas.json"
HISTORICO = RAIZ / "historico_ligamx.csv"
SALIDA = RAIZ / "docs" / "datos"
PUBLICADO = RAIZ / "golden" / "pronostico_j2_apertura2026.csv"

SOLO_FT = {"RES", "TOT", "BTS", "EQL", "EQV"}   # legs evaluables sin marcador HT


def slug(s):
    return s.translate(str.maketrans("áéíóúüñÁÉÍÓÚÜÑ ", "aeiouunAEIOUUN-")).lower().replace(".", "")


def pesos(partidos, corte):
    """Peso efectivo por equipo a la fecha de corte (mismo decaimiento del MLE)."""
    w = {}
    for p in partidos:
        f = math.exp(-C.XI_DECAIMIENTO * (corte - p["fecha"]).days)
        f *= C.PESO_LIGUILLA if p["fase"] == "liguilla" else 1.0
        w[p["local"]] = w.get(p["local"], 0.0) + f
        w[p["visitante"]] = w.get(p["visitante"], 0.0) + f
    return w


def aplicar_credibilidad(ratings, w, cfg):
    """
    Encoge hacia el prior los equipos con poco histórico reciente.
        Z = w^p / (w^p + k^p);  log(rating) = Z·log(MLE) + (1-Z)·log(prior)
    Con p=3 la transición es nítida: un ascendido se encoge fuerte y un equipo
    con 600 partidos no se mueve. Ver analisis/credibilidad.md.
    """
    if not cfg.get("activa"):
        return ratings, {}
    k, p = cfg["k"], cfg["p"]
    out, detalle = dict(ratings), {}
    for e in C.EQUIPOS:
        if e not in ratings or e not in C.PRIORS_ILUSTRATIVOS:
            continue
        wi = w.get(e, 0.0)
        Z = wi ** p / (wi ** p + k ** p) if wi > 0 else 0.0
        a, d = ratings[e]
        pa, pd = C.PRIORS_ILUSTRATIVOS[e]
        out[e] = (math.exp(Z * math.log(a) + (1 - Z) * math.log(pa)),
                  math.exp(Z * math.log(d) + (1 - Z) * math.log(pd)))
        detalle[e] = {"w": round(wi, 2), "Z": round(Z, 3),
                      "mle": [round(a, 4), round(d, 4)],
                      "usado": [round(out[e][0], 4), round(out[e][1], 4)]}
    return out, detalle


def bitacora(local, visitante, estadio, ratings, ajustes):
    """Cascada de λ capa por capa, con el valor antes y después de cada una."""
    atk_l, def_l = ratings[local]
    atk_v, def_v = ratings[visitante]
    l = C.BASE_HOME_GOALS * atk_l * def_v
    v = C.BASE_AWAY_GOALS * atk_v * def_l
    bit = [{"capa": "Fuerza base (MLE)",
            "detalle": f"ataque {local} {atk_l:.2f} × defensa {visitante} {def_v:.2f}"
                       f" · ataque {visitante} {atk_v:.2f} × defensa {local} {def_l:.2f}",
            "lam": [round(l, 3), round(v, 3)]}]

    loc = C.LOCALIA_ESTADIO.get(local, 1.0)
    l *= loc
    bit.append({"capa": "Localía por estadio", "detalle": f"{estadio} · ×{loc:.2f}",
                "lam": [round(l, 3), round(v, 3)]})

    if local in C.FACTOR_ESCUDO:
        v /= C.FACTOR_ESCUDO[local]
        bit.append({"capa": "Factor escudo",
                    "detalle": f"peso institucional de {local}: ataque rival ÷{C.FACTOR_ESCUDO[local]:.2f}",
                    "lam": [round(l, 3), round(v, 3)]})
    if visitante in C.FACTOR_ESCUDO:
        l /= C.FACTOR_ESCUDO[visitante]
        bit.append({"capa": "Factor escudo",
                    "detalle": f"peso institucional de {visitante}: ataque rival ÷{C.FACTOR_ESCUDO[visitante]:.2f}",
                    "lam": [round(l, 3), round(v, 3)]})
    if (local, visitante) in C.REGLAS_H2H:
        ml, mv, nota = C.REGLAS_H2H[(local, visitante)]
        l *= ml; v *= mv
        bit.append({"capa": "Regla H2H", "detalle": nota, "lam": [round(l, 3), round(v, 3)]})

    for eq, es_local in ((local, True), (visitante, False)):
        if eq in ajustes:
            f = ajustes[eq]["fuerza"]
            if es_local:
                l *= f; v /= math.sqrt(f)
            else:
                v *= f; l /= math.sqrt(f)
            bit.append({"capa": "Actualidad de la jornada",
                        "detalle": f"{eq} ×{f:.2f} — {ajustes[eq]['nota']}",
                        "lam": [round(l, 3), round(v, 3)]})
    return bit, l, v


def prob_exacta(M):
    """1X2 exacto desde la matriz. Sin ruido de simulación (§3.1)."""
    return (float(np.tril(M, -1).sum()), float(np.trace(M)), float(np.triu(M, 1).sum()))


def genera_jornada(bloque, historico_todo, cfg_modelo, torneo):
    n = bloque["jornada"]
    origen = bloque["origen"]
    ajustes = bloque.get("ajustes", {})
    fixture = bloque["partidos"]

    # --- corte: sólo lo anterior a la primera fecha de la jornada ---
    corte = min(datetime.strptime(p["fecha"], "%Y-%m-%d").date() for p in fixture)
    entrena = [p for p in historico_todo if p["fecha"] < corte]

    reg = [p for p in entrena if p["fase"] == "regular"]
    C.BASE_HOME_GOALS = sum(p["gl"] for p in reg) / len(reg)
    C.BASE_AWAY_GOALS = sum(p["gv"] for p in reg) / len(reg)

    crudos = C.fit_dixon_coles(entrena, hoy=corte)
    for e in C.EQUIPOS:
        crudos.setdefault(e, C.PRIORS_ILUSTRATIVOS[e])
    w = pesos(entrena, corte)
    ratings, cred = aplicar_credibilidad(crudos, w, cfg_modelo.get("credibilidad", {}))

    # el snapshot publicado no se recalcula jamás
    pub = {}
    if origen == "publicado" and PUBLICADO.is_file():
        pub = {(r["local"], r["visitante"]): r
               for r in csv.DictReader(open(PUBLICADO, encoding="utf-8-sig"))}

    partidos, matrices = [], []
    for p in fixture:
        local, visitante, estadio = p["local"], p["visitante"], p["estadio"]
        bit, lam_l, lam_v = bitacora(local, visitante, estadio, ratings, ajustes)
        M = C.matriz_marcadores(lam_l, lam_v)
        matrices.append({"nombre": f"{local} vs {visitante}", "H": local, "A": visitante,
                         "M": M, "lam_l": lam_l, "lam_v": lam_v})

        top = sorted(((M[x, y], x, y) for x in range(6) for y in range(6)), reverse=True)[:5]
        if (local, visitante) in pub:
            r = pub[(local, visitante)]
            pr = (float(r["p_local"]), float(r["p_empate"]), float(r["p_visita"]))
            pick, marcador = r["pick"], r["marcador"]
        else:
            pr = prob_exacta(M)
            i = int(np.argmax(pr))
            pick = (local, "Empate", visitante)[i]
            marcador = f"{top[0][1]}-{top[0][2]}"

        d = {"id": f"j{n:02d}-{slug(local)}-{slug(visitante)}",
             "fecha": p["fecha"], "estadio": estadio,
             "local": local, "visitante": visitante,
             "lambdas": {"local": round(lam_l, 3), "visita": round(lam_v, 3)},
             "prob": {"local": round(pr[0], 4), "empate": round(pr[1], 4),
                      "visita": round(pr[2], 4)},
             "pick": pick, "marcador_probable": marcador,
             "top_marcadores": [{"marcador": f"{x}-{y}", "prob": round(float(q), 4)}
                                for q, x, y in top],
             "bitacora": bit, "resultado": None}

        av = [e for e in (local, visitante) if cred.get(e, {}).get("Z", 1) < 0.7]
        d["incertidumbre"] = (
            f"{' y '.join(av)}: poco histórico reciente, fuerza parcialmente asumida"
            if av else None)

        if p.get("resultado"):
            gl, gv = p["resultado"]
            gana = local if gl > gv else ("Empate" if gl == gv else visitante)
            obs = (1, 0, 0) if gl > gv else ((0, 1, 0) if gl == gv else (0, 0, 1))
            d["resultado"] = {
                "gl": gl, "gv": gv, "gana": gana,
                "acerto_1x2": pick == gana,
                "acerto_marcador": marcador == f"{gl}-{gv}",
                "brier": round(sum((a - o) ** 2 for a, o in zip(pr, obs)), 4)}
        partidos.append(d)

    # --- parlays ---
    crudo_par = C.construir_parlays(matrices)
    etiquetas = {"recomendado": ("Recomendado", "Equilibrio óptimo entre número de picks y seguridad."),
                 "seguro": ("Seguro", "Los legs más sólidos, uno por partido. Menos premio, más certeza."),
                 "agresivo": ("Agresivo", "Más picks: más premio si pega, menor probabilidad combinada.")}
    parlays = {}
    for k, (nombre, desc) in etiquetas.items():
        legs, fallo, pendiente = [], False, False
        for leg in crudo_par[k]["legs"]:
            mt = matrices[leg["midx"]]
            res = next((q["resultado"] for q in fixture
                        if q["local"] == mt["H"] and q["visitante"] == mt["A"]), None)
            if res and leg["familia"] in SOLO_FT:
                ok = bool(leg["pred"](res[0], res[1], 0, 0))
                estado = "acierto" if ok else "falla"
                fallo = fallo or not ok
            elif res:
                estado = "sin_dato"
            else:
                estado = "pendiente"
                pendiente = True
            legs.append({"partido": mt["nombre"], "etiqueta": leg["label"],
                         "prob": round(leg["prob"], 4), "estado": estado})
        parlays[k] = {"nombre": nombre, "descripcion": desc, "legs": legs,
                      "prob_conjunta": round(crudo_par[k]["prob"], 4),
                      "valor_esperado": round(len(legs) * crudo_par[k]["prob"], 3),
                      "pego": None if pendiente else (False if fallo else None)}

    jugados = [p for p in partidos if p["resultado"]]
    doc = {
        "esquema": "cerebro-ligamx/v1",
        "torneo": torneo, "jornada": n, "origen": origen,
        "nota_origen": bloque.get("nota"),
        "estado": "sellada" if len(jugados) == len(partidos) else
                  ("parcial" if jugados else "vigente"),
        "corte_calibracion": corte.isoformat(),
        "modelo": {
            "motor": "Dixon-Coles + malla exacta",
            "rho_dc": C.RHO_DC, "xi_decaimiento": C.XI_DECAIMIENTO,
            "prop_goles_1t": C.PROP_GOLES_1T,
            "base_local": round(C.BASE_HOME_GOALS, 4),
            "base_visita": round(C.BASE_AWAY_GOALS, 4),
            "credibilidad": cfg_modelo.get("credibilidad", {}),
            "historico": {"partidos": len(entrena),
                          "desde": entrena[0]["fecha"].isoformat(),
                          "hasta": entrena[-1]["fecha"].isoformat()},
        },
        "credibilidad_equipos": cred,
        "partidos": partidos,
        "parlays": parlays,
        "resumen": ({"aciertos_1x2": sum(p["resultado"]["acerto_1x2"] for p in jugados),
                     "partidos": len(jugados),
                     "marcadores_exactos": sum(p["resultado"]["acerto_marcador"] for p in jugados),
                     "brier": round(sum(p["resultado"]["brier"] for p in jugados) / len(jugados), 4),
                     "parlays_pegados": sum(1 for v in parlays.values() if v["pego"])}
                    if jugados else None),
        "no_modelado": ["tarjetas", "córners", "goleador", "minuto de gol"],
    }
    return doc


def main():
    ap = argparse.ArgumentParser(description="Genera los JSON de jornada del Cerebro")
    ap.add_argument("--jornada", type=int, help="Sólo esta jornada")
    args = ap.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    historico = C.cargar_historico(str(HISTORICO))
    historico.sort(key=lambda p: p["fecha"])
    SALIDA.mkdir(parents=True, exist_ok=True)

    resumenes, vigente = [], None
    for bloque in cfg["jornadas"]:
        n = bloque["jornada"]
        if args.jornada and n != args.jornada:
            ruta = SALIDA / f"j{n:02d}.json"
            if ruta.is_file():
                d = json.loads(ruta.read_text(encoding="utf-8"))
                resumenes.append((d, bloque))
                if d["estado"] != "sellada":
                    vigente = n
            continue
        print(f"[J{n}] origen={bloque['origen']} ...")
        doc = genera_jornada(bloque, historico, cfg["modelo"], cfg["torneo"])
        (SALIDA / f"j{n:02d}.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        r = doc["resumen"]
        print(f"      corte {doc['corte_calibracion']} · {doc['modelo']['historico']['partidos']} partidos"
              f" · estado {doc['estado']}"
              + (f" · {r['aciertos_1x2']}/{r['partidos']} aciertos, Brier {r['brier']}" if r else ""))
        resumenes.append((doc, bloque))
        if doc["estado"] != "sellada":
            vigente = n

    # --- índice + desempeño acumulado ---
    hist = [{"jornada": 1, "aciertos_1x2": 6, "partidos": 9, "marcadores_exactos": 1,
             "brier": 0.568, "origen": "publicado",
             "nota": "sin snapshot: se registra el resultado, no la distribución"}]
    for doc, _ in sorted(resumenes, key=lambda t: t[0]["jornada"]):
        if doc["resumen"]:
            hist.append({"jornada": doc["jornada"], **doc["resumen"], "origen": doc["origen"]})

    con_brier = [h for h in hist if h.get("brier") is not None]
    indice = {
        "torneo": cfg["torneo"],
        "jornada_vigente": vigente or max(d["jornada"] for d, _ in resumenes),
        "jornadas": [{"jornada": d["jornada"], "archivo": f"j{d['jornada']:02d}.json",
                      "estado": d["estado"], "origen": d["origen"]}
                     for d, _ in sorted(resumenes, key=lambda t: t[0]["jornada"])],
        "desempeno": {
            "por_jornada": hist,
            "acumulado": {
                "aciertos_1x2": sum(h["aciertos_1x2"] for h in hist),
                "partidos": sum(h["partidos"] for h in hist),
                "marcadores_exactos": sum(h["marcadores_exactos"] for h in hist),
                "brier": round(sum(h["brier"] for h in con_brier) / len(con_brier), 4),
            },
            "convencion_brier": "multicategoría (0–2); azar = 0.667",
        },
    }
    (SALIDA / "indice.json").write_text(
        json.dumps(indice, ensure_ascii=False, indent=1), encoding="utf-8")
    a = indice["desempeno"]["acumulado"]
    print(f"\nindice.json · jornada vigente J{indice['jornada_vigente']} · "
          f"acumulado {a['aciertos_1x2']}/{a['partidos']}, Brier {a['brier']}")


if __name__ == "__main__":
    main()
