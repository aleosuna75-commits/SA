# -*- coding: utf-8 -*-
"""
================================================================================
 recalibrar_delta_reforecast.py · δ ajustado sobre la BASE DE PRIMA DEL REFORECAST
--------------------------------------------------------------------------------
 Planeación Financiera (BP&A) · Reaseguradora Patria (GPV)

 POR QUÉ EXISTE. El δ de delta_calibrado.json se ajustó para que
 «Σ prima_BD-MEC × FND ≈ prima no devengada real». El reforecast aplica ese δ sobre
 otra base de prima —la consulta a BD Gonzalo, con sus filtros— que produce del
 orden de 10% más prima no devengada con el MISMO FND. Por eso el δ no transfiere
 y el reforecast sobreestima ~9.5% (sin CAT). Este script vuelve a ajustar δ usando
 la prima del propio reforecast, que es la base sobre la que se va a aplicar.

 QUÉ NECESITA, todo en la misma carpeta que este script:
   · ConsultaPPTO_RRC_<mes>_tradicional.xlsx  — uno o varios; los escribe el propio
     reforecast en Documents\\Outputs. Debe traer, por registro:
         Ramo · TipoRea · CALMONTH · FRECUENCIA · MONTO_PI · BELMEDIA · PORC_ND
         (y TC_Valuación si el monto viene en moneda original)
     El <mes> del nombre es el mes de valuación (1..12) del año ANIO_VALUACION.
   · insumos\\real_rrc_long.csv  — la RRC real (la arma preparar_insumos.py)
   · insumos\\tc_mensual_bd.csv  — TC de cierre por mes
   · mec_devengamiento.py        — para NT y la tabla de ramos

 QUÉ HACE.
 1. Detecta con qué FND se corrió el archivo. Si PORC_ND == clip(NT(k) − δ_ramo, 0, 1)
    en las filas ajustables, la corrida es del MODELO; si coincide con la columna de
    xPND que toca por FRECUENCIA, es del LEGADO. Importa: sobre una corrida del modelo
    el VALORFREC legado no viene en el archivo y no se puede ajustar «sobre el legado».
 2. Vuelve a ajustar δ por ramo contra el BEL real, en dos formas:
      PLANA        FND = clip(NT(k) − δ_ramo, 0, 1)                 ← la del reforecast
      ESCALONADA   FND = clip(NT(k) − δ_M4(frecuencia) − δ_ramo, 0, 1)
    (y DESPLAZADA, clip(PORC_ND − δ, 0, 1), sólo si el archivo es del legado).
 3. Reconstruye el LEGADO sobre el mismo archivo con la regla M4, δ_M4(t)=(t−1)/2·30/365,
    para comparar legado / modelo / δ reajustado en la misma base y la misma ventana.
    M4 reproduce EXACTO las columnas 'NA', '1' y '3' de xPND —aquí el 93.7% de la
    prima— y difiere hasta 0.0055 en '2', '6' y '0', donde la tabla trunca antes.
 4. Valida FUERA DE MUESTRA: ajusta δ dejando un mes fuera y lo prueba en ese mes.
    Sin esto el ajuste se juzga a sí mismo.

 Respeta la jerarquía de PORC_ND del script: los ramos 71/73 y el no proporcional
 (TipoRea 2) se dejan como están y no entran al ajuste. En un ramo donde nada es
 ajustable δ no se publica: se conserva el de producción y se avisa.

 SALIDA:  delta_recalibrado.json · recalibracion_reforecast.csv ·
          comparacion_tres_opciones.csv · validacion_fuera_de_muestra.csv

 Uso:  python recalibrar_delta_reforecast.py
================================================================================
"""
import glob
import json
import os
import re
import sys

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
INS = os.path.join(BASE, "insumos") if os.path.isdir(os.path.join(BASE, "insumos")) else BASE
sys.path.insert(0, BASE)

ANIO_VALUACION = 2026          # año de los archivos ConsultaPPTO_RRC_<mes>_tradicional
GRID = np.round(np.arange(-0.30, 0.801, 0.005), 3)

# grupos de la calibración (mismos que validar_prima_devengada.py)
RAMO2GRUPO = {10: "Vida", 20: "Vida", 30: "AyE", 31: "AyE", 34: "AyE", 35: "AyE", 37: "AyE", 39: "AyE",
              40: "RC", 50: "MyT", 60: "Incendio", 70: "CAT", 71: "CAT", 73: "CAT",
              80: "Agro", 90: "Autos", 100: "Credito", 110: "Diversos"}
# columna RAM del real -> ramo del reforecast
RAM2RAMO = {"RAM_10": 10, "RAM_30": 31, "RAM_34": 35, "RAM_37": 39, "RAM_40": 40, "RAM_50": 50,
            "RAM_60": 60, "RAM_71": 71, "RAM_73": 73, "RAM_80": 80, "RAM_90": 90,
            "RAM_100": 100, "RAM_110": 110}

try:
    import mec_devengamiento as mec
    NT = mec.NT_MENSUAL
except Exception:
    NT = np.array([0.95890411, 0.876712329, 0.791780822, 0.706849315, 0.624657534, 0.539726027,
                   0.457534247, 0.37260274, 0.295890411, 0.210958904, 0.126027397, 0.043835616])


def d_m4(t):
    """Regla M4 del MEC. Reproduce EXACTO las columnas de frecuencia de xPND."""
    return (t - 1) / 2 * 30 / 365


# código de FRECUENCIA del reforecast -> meses de la cuenta
FREC2MESES = {"1": 1, "2": 2, "3": 3, "6": 6, "0": 12, "NA": 1, "DEF": 3}


def meses_cuenta(f):
    if f is None or (isinstance(f, float) and np.isnan(f)):
        return 1                      # 'NA' -> columna mensual, δ_M4 = 0
    s = str(f).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return FREC2MESES.get(s, 1)


def antiguedad(mes_val, calmonth):
    a, b = int(mes_val), int(calmonth)
    return (a // 100 - b // 100) * 12 + (a % 100 - b % 100)


def leer_consultas():
    """Cada ConsultaPPTO_RRC_<mes>_tradicional.xlsx, con su mes de valuación."""
    pat = os.path.join(BASE, "ConsultaPPTO_RRC_*_tradicional.xls*")
    arch = sorted(x for x in glob.glob(pat) if not os.path.basename(x).startswith("~$"))
    if not arch:
        raise SystemExit(
            "[recal] No encontré ningún «ConsultaPPTO_RRC_<mes>_tradicional.xlsx» en:\n"
            f"        {BASE}\n"
            "        Los escribe el propio reforecast en Documents\\Outputs; copia aquí dos o tres meses.")
    piezas = []
    for a in arch:
        m = re.search(r"ConsultaPPTO_RRC_(\d+)_tradicional", os.path.basename(a))
        if not m:
            continue
        mes = int(m.group(1))
        d = pd.read_excel(a)
        falta = [c for c in ("Ramo", "TipoRea", "CALMONTH", "FRECUENCIA", "MONTO_PI", "BELMEDIA", "PORC_ND")
                 if c not in d.columns]
        if falta:
            raise SystemExit(f"[recal] A «{os.path.basename(a)}» le faltan columnas: {falta}\n"
                             f"        Tiene: {list(d.columns)}")
        d["MES_VAL"] = ANIO_VALUACION * 100 + mes
        piezas.append(d)
        print(f"[recal] {os.path.basename(a)}: {len(d):,} registros · valuación {d.MES_VAL.iloc[0]}")
    return pd.concat(piezas, ignore_index=True)


def regimen(d, delta_prod):
    """¿Con qué FND se corrió este archivo? Lo decide el propio PORC_ND.

    Si el reforecast corrió con USAR_FND_CALIBRADO = True, entonces para toda fila
    ajustable PORC_ND == clip(NT(k) − δ_ramo, 0, 1). Si corrió con el legado, PORC_ND
    es la columna de xPND que corresponde a la FRECUENCIA de la cuenta. Distinguirlos
    importa: sobre un archivo del MODELO no se puede ajustar un desplazamiento «sobre
    el VALORFREC legado», porque el VALORFREC legado no viene en el archivo.
    """
    a = d[d.ajustable]
    if a.empty:
        return "desconocido", 0.0
    dd = a.Grupo.map(lambda g: float(delta_prod.get(g, 0.0))).to_numpy()
    mod = np.clip(a.NT_k.to_numpy() - dd, 0.0, 1.0)
    leg = np.clip(a.NT_k.to_numpy() - a.dM4.to_numpy(), 0.0, 1.0)
    fm = float((np.abs(a.PORC_ND.to_numpy() - mod) < 1e-9).mean())
    fl = float((np.abs(a.PORC_ND.to_numpy() - leg) < 1e-9).mean())
    if fm > 0.99:
        return "modelo", fm
    if fl > 0.99:
        return "legado", fl
    return "mixto", max(fm, fl)


def main():
    d = leer_consultas()
    for c in ("Ramo", "TipoRea", "CALMONTH", "MONTO_PI", "BELMEDIA", "PORC_ND"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    if "TC_Valuación" in d.columns:
        d["TC_Val"] = pd.to_numeric(d["TC_Valuación"], errors="coerce").fillna(1.0)
    else:
        d["TC_Val"] = 1.0
    d = d.dropna(subset=["Ramo", "CALMONTH", "MONTO_PI", "BELMEDIA"])
    # PORC_ND nulo = el legado no le asignó factor (frecuencia fuera del catálogo de xPND):
    # cuenta como 0, que es lo que el legado acaba metiendo en el BEL.
    n_nulos = int(d.PORC_ND.isna().sum())
    if n_nulos:
        print(f"[recal] Aviso: {n_nulos:,} registros traen PORC_ND vacío; se toman como 0 (así entran al BEL).")
    d["PORC_ND"] = d.PORC_ND.fillna(0.0)
    d["Grupo"] = d.Ramo.map(RAMO2GRUPO)
    d = d[d.Grupo.notna()].copy()
    d["k"] = [antiguedad(v, c) for v, c in zip(d.MES_VAL, d.CALMONTH)]
    d["t"] = [meses_cuenta(f) for f in d.FRECUENCIA]
    d["dM4"] = d_m4(d.t)
    kk = d.k.to_numpy(int)
    d["NT_k"] = np.where((kk < 0) | (kk >= len(NT)), 0.0, NT[np.clip(kk, 0, len(NT) - 1)])

    # la jerarquía de PORC_ND: 71/73 y el no proporcional NO entran al ajuste
    d["ajustable"] = (~d.Ramo.isin([71, 73])) & (d.TipoRea != 2)
    d["peso"] = d.MONTO_PI * d.BELMEDIA * d.TC_Val         # BEL cuando FND = 1
    # SIGNO. En el archivo del reforecast MONTO_PI viene NEGATIVO y por tanto el BEL
    # también: MONTO_PI x BELMEDIA x PORC_ND x TC_Valuación reproduce EXACTO la columna
    # BELRIESGO2026_TCVal, que es negativa. La RRC real viene positiva. Es un convenio de
    # signo del archivo, no un neteo: se voltea el agregado completo, nunca fila por fila
    # (un abs() por fila destruiría las contrapartidas negativas legítimas).
    SIGNO = -1.0 if (d.peso * d.PORC_ND).sum() < 0 else 1.0
    if SIGNO < 0:
        print("[recal] El BEL del archivo viene con signo negativo (convenio del reforecast);"
              " se voltea el agregado para compararlo con la RRC real.")
    d["peso"] = SIGNO * d.peso
    d["BEL_arch"] = d.peso * d.PORC_ND

    delta_prod = {}
    jp = os.path.join(BASE, "delta_calibrado.json")
    if not os.path.exists(jp):
        jp = os.path.join(BASE, "salidas", "delta_calibrado.json")
    if os.path.exists(jp):
        delta_prod = json.load(open(jp, encoding="utf-8"))

    # ---- ¿el archivo trae el FND del modelo o el legado?
    reg, frac = regimen(d, delta_prod)
    ETIQ = {"modelo": "FND DEL MODELO (USAR_FND_CALIBRADO = True)",
            "legado": "FND LEGADO (xPND por frecuencia)",
            "mixto": "NO IDENTIFICADO"}[reg] if reg != "desconocido" else "SIN FILAS AJUSTABLES"
    print(f"\n[recal] Régimen del archivo: {ETIQ}  ({frac:.1%} de las filas ajustables cuadran)")
    if reg == "modelo":
        print("        Es decir: PORC_ND = clip(NT(k) − δ_producción, 0, 1). El VALORFREC legado NO")
        print("        viene en el archivo, así que la variante «desplazada sobre el legado» no se")
        print("        puede ajustar aquí; lo que sí se puede —y es lo que hace falta— es volver a")
        print("        ajustar δ sobre esta base de prima, que es la que el reforecast usa de verdad.")
    elif reg == "mixto":
        print("        AVISO: no reproduzco el PORC_ND del archivo con ninguna de las dos reglas.")
        print("        Revisa que delta_calibrado.json sea el mismo con el que se corrió el reforecast.")

    # BEL real (USD) y TC para pasar el archivo a USD
    real = pd.read_csv(os.path.join(INS, "real_rrc_long.csv"))
    real["Ramo"] = real.RAM.map(RAM2RAMO)
    real = real[real.Ramo.notna()].copy()
    real["Grupo"] = real.Ramo.map(RAMO2GRUPO)
    tc = pd.read_csv(os.path.join(INS, "tc_mensual_bd.csv")).set_index("Periodo")["TC"]
    meses_val = sorted(d.MES_VAL.unique())
    faltan = [m for m in meses_val if m not in real.PERIODO.values]
    if faltan:
        print(f"[recal] Aviso: la RRC real no cubre {faltan}; esos meses quedan fuera del ajuste.")
    rr = (real[real.PERIODO.isin(meses_val)].groupby(["Grupo", "PERIODO"])["RRC BEL"].sum())

    d["TC_mes"] = d.MES_VAL.map(tc)
    if d.TC_mes.isna().any():
        raise SystemExit(f"[recal] Sin TC para {sorted(d.loc[d.TC_mes.isna(),'MES_VAL'].unique())} en tc_mensual_bd.csv")
    d["peso_USD"] = d.peso / d.TC_mes
    d["BEL_arch_USD"] = d.BEL_arch / d.TC_mes

    # CONTROL: el BEL que reconstruyo debe ser el que el propio reforecast ya escribió.
    col_bel = next((c for c in d.columns if c.upper().startswith("BELRIESGO") and "TCVAL" in c.upper()), None)
    if col_bel:
        ref = SIGNO * pd.to_numeric(d[col_bel], errors="coerce").fillna(0.0)
        err = float(np.abs(d.BEL_arch - ref).sum()) / max(float(np.abs(ref).sum()), 1.0)
        print(f"[recal] Control contra «{col_bel}» del propio archivo: error relativo {err:.2e}"
              f"  ({'OK' if err < 1e-6 else 'REVISAR: la fórmula del BEL no coincide'})")

    # ---- diagnóstico: ¿cuánta prima anula el legado por FRECUENCIA fuera de catálogo?
    CAT_XPND = {"1", "2", "3", "6", "0", "NA", "DEF"}
    aj = d[d.ajustable].copy()
    # OJO: en el archivo, las filas cuya FRECUENCIA era la cadena 'NA' llegan como vacío
    # (el viaje a Excel las convierte en NaN). En memoria SÍ son 'NA', que está en el catálogo.
    aj["frec_txt"] = np.where(aj.FRECUENCIA.isna(), "NA",
                              aj.FRECUENCIA.astype(str).str.strip().str.replace(r"\.0$", "", regex=True))
    aj["fuera_catalogo"] = ~aj.frec_txt.isin(CAT_XPND)
    pw = aj.peso_USD.abs()
    print("\n" + "=" * 108)
    print("DIAGNÓSTICO · reparto de la prima proporcional ajustable por código de FRECUENCIA")
    print("=" * 108)
    rep = aj.groupby("frec_txt").apply(
        lambda x: pd.Series({"prima_USD": x.peso_USD.abs().sum(),
                             "meses_cuenta": x.t.iloc[0],
                             "delta_M4": d_m4(x.t.iloc[0]),
                             "en_catalogo_xPND": (~x.fuera_catalogo).all()}), include_groups=False)
    rep["%_prima"] = 100 * rep.prima_USD / rep.prima_USD.sum()
    print(rep.sort_values("prima_USD", ascending=False).to_string(
        formatters={"prima_USD": lambda v: f"{v/1e6:10.1f}", "meses_cuenta": lambda v: f"{v:.0f}",
                    "delta_M4": lambda v: f"{v:.4f}", "%_prima": lambda v: f"{v:5.1f}"}))
    f_fuera = 100 * pw[aj.fuera_catalogo].sum() / max(pw.sum(), 1e-9)
    print(f"\n  Prima con FRECUENCIA fuera del catálogo de xPND: {f_fuera:.1f}%"
          f"   ·   δ_M4 medio ponderado por prima: {np.average(aj.dM4, weights=pw):.4f}")

    # ---------------------------------------------------------------- el ajuste
    def bel(sub, dl, modo):
        """BEL en USD que produce δ = dl sobre este subconjunto.
        'plana'      FND = clip(NT(k) − δ, 0, 1)                 ← misma forma que el reforecast
        'escalonada' FND = clip(NT(k) − δ_M4(frecuencia) − δ, 0, 1)
        'desplazada' FND = clip(PORC_ND_del_archivo − δ, 0, 1)   ← sólo tiene sentido si el
                     archivo trae el FND legado; sobre un archivo del modelo es redundante
                     con 'plana' (equivale a δ_producción + δ)."""
        fijo = sub.loc[~sub.ajustable, "BEL_arch_USD"].sum()
        a = sub[sub.ajustable]
        if a.empty:
            return fijo
        if modo == "desplazada":
            base, desp = a.PORC_ND.to_numpy(float), dl
        else:
            base = a.NT_k.to_numpy()
            desp = (a.dM4.to_numpy() if modo == "escalonada" else 0.0) + dl
        return fijo + float((a.peso_USD.to_numpy() * np.clip(base - desp, 0.0, 1.0)).sum())

    modos = ["plana", "escalonada"] + (["desplazada"] if reg == "legado" else [])
    NOM = {"plana": "δ plana", "escalonada": "δ escal", "desplazada": "δ desp"}

    filas, mejor = [], {}
    print("\n" + "=" * 108)
    print("AJUSTE DE δ SOBRE LA BASE DEL REFORECAST   (BEL riesgo, USD, suma de los meses cargados)")
    print("=" * 108)
    enc = f"{'Ramo':10s} {'real':>10s} {'archivo':>10s} {'razón':>6s} |"
    for m in modos:
        enc += f" {NOM[m]:>7s} {'razón':>6s} |"
    print(enc)
    print("-" * 108)
    for g, sub in d.groupby("Grupo"):
        y = sum(rr.get((g, m), np.nan) for m in meses_val)
        if not np.isfinite(y) or y == 0:
            print(f"{g:10s}  (sin RRC real en estos meses; se omite)")
            continue
        arch = sub.BEL_arch_USD.sum()
        best = {}
        for modo in modos:
            cand = min(GRID, key=lambda x: abs(bel(sub, x, modo) - y))
            best[modo] = (cand, bel(sub, cand, modo))
        mejor[g] = {m: float(best[m][0]) for m in best}
        lin = f"{g:10s} {y/1e6:10.1f} {arch/1e6:10.1f} {arch/y:6.3f} |"
        for m in modos:
            lin += f" {best[m][0]:+7.3f} {best[m][1]/y:6.3f} |"
        print(lin)
        fila = dict(Grupo=g, BEL_real=y, BEL_archivo=arch, razon_archivo=arch / y,
                    delta_produccion=float(delta_prod.get(g, 0.0)),
                    ajustable_pct=100 * sub.loc[sub.ajustable, "peso_USD"].abs().sum()
                    / max(sub.peso_USD.abs().sum(), 1e-9),
                    dM4_medio=np.average(sub.loc[sub.ajustable, "dM4"],
                                         weights=sub.loc[sub.ajustable, "peso_USD"].abs())
                    if sub.ajustable.any() else 0.0)
        for m in modos:
            fila[f"delta_{m}"] = best[m][0]
            fila[f"razon_{m}"] = best[m][1] / y
        filas.append(fila)
    r = pd.DataFrame(filas)
    if r.empty:
        raise SystemExit("[recal] No hubo ningún ramo con RRC real en esos meses.")
    print("-" * 108)
    pares = [("archivo (tal como se corrió)", "razon_archivo")] + \
            [(f"{NOM[m]} reajustada", f"razon_{m}") for m in modos]
    for et, col in pares:
        tot = (r[col] * r.BEL_real).sum() / r.BEL_real.sum()
        mae = np.mean(np.abs(r[col] - 1))
        sc = r[r.Grupo != "CAT"]
        mae_sc = np.mean(np.abs(sc[col] - 1))
        tot_sc = (sc[col] * sc.BEL_real).sum() / sc.BEL_real.sum()
        print(f"  {et:30s} razón {tot:.4f}  EAM/ramo {mae:6.2%}   |  sin CAT: razón {tot_sc:.4f}"
              f"  EAM/ramo {mae_sc:6.2%}")

    # ---- ¿cuánto de cada ramo es siquiera ajustable? (δ no puede mover lo demás)
    print("\n  Parte de la prima de cada ramo que δ puede mover (el resto es TipoRea 2 o ramo 71/73):")
    print("   " + "  ".join(f"{x.Grupo}:{x.ajustable_pct:.0f}%" for x in r.itertuples()))

    # ---- estabilidad mes a mes con el δ ajustado (la razón de arriba es del agregado)
    elegido = "plana"
    print("\n" + "=" * 108)
    print(f"ESTABILIDAD MES A MES con el δ reajustado (variante {elegido})   ·   razón modelo/real")
    print("=" * 108)
    # δ sólo significa algo donde hay prima que pueda mover. En CAT (ramos 71/73) el 100%
    # de la prima queda fuera de la jerarquía, así que el ajuste no cambia nada y se va al
    # borde de la malla: ahí se conserva el δ de producción y se avisa, en vez de publicar
    # un número que aparenta significar algo.
    AJ_MIN = 1.0
    inmov = set(r.loc[r.ajustable_pct < AJ_MIN, "Grupo"])
    dl_new = {g: (float(delta_prod.get(g, 0.0)) if g in inmov else v[elegido])
              for g, v in mejor.items()}
    if inmov:
        print(f"\n  AVISO · δ no mueve nada en {', '.join(sorted(inmov))}: toda su prima queda fuera de la")
        print("         jerarquía de PORC_ND (ramo 71/73 o TipoRea 2). Se conserva su δ de producción.")
        print("         Su desviación NO es un problema de FND y no se arregla recalibrando.")
    cab = f"{'Ramo':10s}" + "".join(f"{m:>10d}" for m in meses_val) + f"{'agregado':>10s}"
    print(cab)
    est = []
    for g, sub in d.groupby("Grupo"):
        if g not in dl_new:
            continue
        li, num, den = f"{g:10s}", 0.0, 0.0
        for m in meses_val:
            y = rr.get((g, m), np.nan)
            if not np.isfinite(y) or y == 0:
                li += f"{'—':>10s}"
                continue
            b = bel(sub[sub.MES_VAL == m], dl_new[g], elegido)
            li += f"{b/y:10.3f}"
            num += b
            den += y
        li += f"{num/den:10.3f}" if den else f"{'—':>10s}"
        print(li)
        est.append(dict(Grupo=g, razon_agregada=num / den if den else np.nan))

    # ---- LEGADO RECONSTRUIDO: el mismo archivo, con el FND que xPND habría dado.
    # La regla M4 reproduce EXACTO las columnas 'NA', '1' y '3' de xPND (aquí, el 93.7%
    # de la prima); '2', '6' y '0' difieren hasta 0.0055 porque la tabla trunca antes en
    # la cola. Sirve para comparar legado / modelo / δ reajustado sobre LA MISMA base y
    # la MISMA ventana, que es la única comparación limpia posible con estos archivos.
    if reg == "modelo":
        print("\n" + "=" * 108)
        print("LAS TRES OPCIONES SOBRE LA MISMA BASE Y LA MISMA VENTANA   ·   razón BEL/real")
        print("=" * 108)
        print(f"{'Ramo':10s} {'real M USD':>10s} | {'legado*':>8s} | {'modelo hoy':>10s} |"
              f" {'δ reajust.':>10s} |   δ hoy   δ nuevo")
        print("-" * 108)
        cmp_ = []
        for g, sub in d.groupby("Grupo"):
            y = sum(rr.get((g, m), np.nan) for m in meses_val)
            if not np.isfinite(y) or y == 0 or g not in dl_new:
                continue
            leg = bel(sub, 0.0, "escalonada")          # NT(k) − δ_M4(frecuencia), δ = 0
            mod = sub.BEL_arch_USD.sum()
            new = bel(sub, dl_new[g], elegido)
            print(f"{g:10s} {y/1e6:10.1f} | {leg/y:8.3f} | {mod/y:10.3f} | {new/y:10.3f} |"
                  f" {float(delta_prod.get(g, 0.0)):+8.3f} {dl_new[g]:+8.3f}")
            cmp_.append(dict(Grupo=g, BEL_real=y, razon_legado_rec=leg / y, razon_modelo=mod / y,
                             razon_reajustado=new / y))
        c = pd.DataFrame(cmp_)
        print("-" * 108)
        for et, col in [("legado reconstruido*", "razon_legado_rec"), ("modelo tal como corrió", "razon_modelo"),
                        ("δ reajustado", "razon_reajustado")]:
            sc = c[c.Grupo != "CAT"]
            print(f"  {et:24s} sin CAT: razón {(sc[col]*sc.BEL_real).sum()/sc.BEL_real.sum():.4f}"
                  f"   EAM/ramo {np.mean(np.abs(sc[col]-1)):6.2%}")
        print("  * legado reconstruido con la regla M4; exacto en el 93.7% de la prima,")
        print("    aproximado (±0.0055 de FND) en las cuentas semestrales y anuales.")
        c.to_csv(os.path.join(BASE, "comparacion_tres_opciones.csv"), index=False)

    # ---- VALIDACIÓN FUERA DE MUESTRA: ajusto δ dejando un mes fuera y lo pruebo en ese mes.
    if len(meses_val) >= 3:
        print("\n" + "=" * 108)
        print("VALIDACIÓN FUERA DE MUESTRA (deja-un-mes-fuera): δ ajustado SIN el mes, probado EN el mes")
        print("=" * 108)
        print(f"{'Ramo':10s}" + "".join(f"{m:>12d}" for m in meses_val))
        oos = []
        for g, sub in d.groupby("Grupo"):
            if g not in dl_new or g == "CAT":
                continue
            li = f"{g:10s}"
            for m in meses_val:
                otros = [x for x in meses_val if x != m]
                y_in = sum(rr.get((g, x), np.nan) for x in otros)
                y_out = rr.get((g, m), np.nan)
                if not np.isfinite(y_in) or not np.isfinite(y_out) or y_out == 0:
                    li += f"{'—':>12s}"
                    continue
                s_in = sub[sub.MES_VAL.isin(otros)]
                dcv = min(GRID, key=lambda x: abs(bel(s_in, x, elegido) - y_in))
                rz = bel(sub[sub.MES_VAL == m], dcv, elegido) / y_out
                li += f"  {dcv:+6.3f}{rz:5.3f}"
                oos.append(dict(Grupo=g, mes=m, delta_cv=dcv, razon=rz))
            print(li)
        o = pd.DataFrame(oos)
        if not o.empty:
            print("-" * 108)
            print(f"  {len(o)} pares ramo·mes fuera de muestra:  razón media {o.razon.mean():.4f}"
                  f"   EAM {np.mean(np.abs(o.razon-1)):.2%}   peor {np.max(np.abs(o.razon-1)):.2%}"
                  f"   dispersión de δ (máx−mín por ramo) {o.groupby('Grupo').delta_cv.agg(lambda x: x.max()-x.min()).mean():.3f}")
            print("  Compárese con el error del archivo tal como se corrió (sin CAT):"
                  f" EAM {np.mean(np.abs(r[r.Grupo!='CAT'].razon_archivo-1)):.2%}")
            o.to_csv(os.path.join(BASE, "validacion_fuera_de_muestra.csv"), index=False)

    r.to_csv(os.path.join(BASE, "recalibracion_reforecast.csv"), index=False)
    json.dump(dl_new, open(os.path.join(BASE, "delta_recalibrado.json"), "w", encoding="utf-8"), indent=2)
    print(f"\n[recal] Escritos en {BASE}:")
    print("          delta_recalibrado.json      δ por ramo ajustado sobre la base del reforecast")
    print("          recalibracion_reforecast.csv  el detalle de la tabla de arriba")
    if reg == "modelo":
        print("\n[recal] CÓMO USARLO. El reforecast NO cambia: sigue aplicando")
        print("            PORC_ND = clip(NT(k) − δ_ramo, 0, 1)")
        print("        Lo único que se sustituye es delta_calibrado.json por delta_recalibrado.json,")
        print("        que es el mismo δ ajustado contra la base de prima que el reforecast usa.")


if __name__ == "__main__":
    main()
