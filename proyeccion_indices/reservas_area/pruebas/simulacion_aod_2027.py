# -*- coding: utf-8 -*-
"""Corre ReforecastRRC_aod_2027.py y ReforecastSONR_aod_2027.py (salida de parchar_aod_2027.py) y comprueba que valuan
2027 sin la base de valuacion: cualquier consulta SQL hace fallar la prueba. Revisa, mes por mes y ramo por ramo, que los
contratos son la prima de la BD (hoja PE_RAMO), que la PND del RRC es nuestro FND por esa prima, los indices, el MR, el
tipo de cambio de la BD, que el escenario 2 de RRC y SONR da los montos de la BD y que las salidas lleven _2027.

Uso: python simulacion_aod_2027.py <carpeta con los *_aod_2027.py> ["<BD proyectada>"] [carpeta de trabajo]
Las tablas del area son inventadas (las de simulacion_aod.py). Los montos que salen NO son reservas.
"""
from __future__ import annotations

import math
import re
import shutil
import sys
import tempfile
import types
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).resolve().parent
SCRIPTS = AQUI.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(AQUI))
from insumos_bd import InsumosBD, MONEDA_MXN, MONEDA_USD, NOMBRE_BD, buscar_bd, mes_mas, rango_meses  # noqa: E402
from simulacion_aod import (_igual, correr, redirigir, restaurar, tablas_area, verificar_rrc,  # noqa: E402
                            verificar_sonr)

SALIDAS = ("RRC_esc_2027.xlsx", "SONR_esc_2027.xlsx", "Parametros_usados_RRC_2027.xlsx", "Parametros_usados_SONR_2027.xlsx",
           "TablaTCRRC_2027.xlsx", "TablaTCSONR_2027.xlsx", "auxSONR_sum_2027.xlsx")


def sin_base():
    """pyodbc y read_sql que fallan: los scripts de 2027 no deben consultar la base."""
    def no(*a, **k):
        raise RuntimeError("los scripts de 2027 no deben consultar la base Access")
    falso = types.ModuleType("pyodbc")
    falso.connect = no
    sys.modules["pyodbc"] = falso
    pd.read_sql = no
    mec = types.ModuleType("mec_devengamiento")
    mec.cargar_delta = lambda carpeta: {}
    mec.antiguedad_registro = lambda mes_val, cm: (int(mes_val) // 100 - int(cm) // 100) * 12 + int(mes_val) % 100 - int(cm) % 100
    mec.fnd_desplazado = lambda ramo, valor, k, delta: valor
    sys.modules["mec_devengamiento"] = mec


def verificar_2027(ins: InsumosBD, capturas: dict, marcos_sonr: list, salida: Path, anio: int, area: Path) -> list[str]:
    res = []
    # contratos = prima de la BD y PND = nuestro FND x esa prima, por ramo y mes
    malos_pe, malos_pnd, n = 0, 0, 0
    for m in range(1, 13):
        p = anio * 100 + m
        df = capturas.get(f"ConsultaPPTO_RRC_{m}_tradicional_2027.xlsx")
        if df is None:
            continue
        for ramo in sorted(pd.to_numeric(df["Ramo"]).astype(int).unique()):
            d = df[pd.to_numeric(df["Ramo"]) == ramo]
            pe = sum(ins.pe.get((ramo, q), 0.0) for q in rango_meses(mes_mas(p, -11), p))
            n += 1
            malos_pe += not _igual(-float(pd.to_numeric(d["MONTO_PI"]).sum()), pe)
            pnd = -float((pd.to_numeric(d["MONTO_PI"]) * pd.to_numeric(d["PORC_ND"])).sum())
            malos_pnd += not _igual(pnd, ins.fnd_bd(ramo, p) * pe)
    res.append(f"{'OK ' if n and not malos_pe else 'MAL'} RRC: en {n} ramos x mes la prima de los contratos es la PE de la BD de "
               f"los ultimos 12 meses ({malos_pe} distintos)")
    res.append(f"{'OK ' if n and not malos_pnd else 'MAL'} RRC: la PND del ramo es nuestro FND x esa prima en {n - malos_pnd} de {n}")
    # tipo de cambio: todo de la BD
    malos, tot = 0, 0
    for nombre in ("TablaTCRRC_2027.xlsx", "TablaTCSONR_2027.xlsx"):
        t = capturas.get(nombre)
        if t is None:
            malos += 1
            continue
        for p, v in zip(t["cTCAD_FecAMD"], t["cTCAD_Mnt"]):
            tot += 1
            malos += not _igual(v, ins.tc_de(int(p)))
    for m in range(1, 13):
        df = capturas.get(f"ConsultaPPTO_RRC_{m}_tradicional_2027.xlsx")
        if df is None:
            continue
        for mon, v, c in zip(df["MonedaOri"], df["TC_Valuación"], df["TC_CierreAnterior"]):
            tot += 2
            esp_v = ins.tc_de(anio * 100 + m) if int(mon) == MONEDA_USD else 1.0
            esp_c = ins.tc_de((anio - 1) * 100 + 12) if int(mon) == MONEDA_USD else 1.0
            malos += (not _igual(v, esp_v)) + (not _igual(c, esp_c))
    for f in marcos_sonr:
        if "cTCAD_Mnt_x" in f.columns and "Ramo_filt" in f.columns:
            col = next((c for c in f.columns if str(c).startswith("FND_")), None)
            if col is None:
                continue
            p = int(str(col)[4:])
            for v, c in zip(f["cTCAD_Mnt_x"], f["cTCAD_Mnt_y"]):
                tot += 2
                malos += (not _igual(v, ins.tc_de(p))) + (not _igual(c, ins.tc_de((anio - 1) * 100 + 12)))
    res.append(f"{'OK ' if tot and not malos else 'MAL'} TC de la BD (M en 2027, J en diciembre 2026): {tot} valores, {malos} distintos")
    # salidas con _2027 y periodos
    for nombre in SALIDAS:
        res.append(f"{'OK ' if (salida / nombre).exists() else 'MAL'} {nombre}")
    for nombre in ("RRC_esc_2027.xlsx", "SONR_esc_2027.xlsx"):
        if not (salida / nombre).exists():
            continue
        out = pd.read_excel(salida / nombre)
        per = pd.to_numeric(out["Periodo"])
        e0 = out[out["Escenario"] == 0]
        otros = out[out["Escenario"] != 0]
        ok = len(e0) and set(pd.to_numeric(e0["Periodo"])) == {(anio - 1) * 100 + 12} and set(per[out["Escenario"] != 0] // 100) == {anio}
        res.append(f"{'OK ' if ok else 'MAL'} {nombre}: escenarios {sorted(out['Escenario'].unique().tolist())}; escenario 0 en "
                   f"{sorted(pd.to_numeric(e0['Periodo']).unique().tolist())}; los demas de {per[out['Escenario'] != 0].min()} a "
                   f"{per[out['Escenario'] != 0].max()} ({len(otros)} renglones)")
        # el area no trae presupuesto del ano: va el del ano anterior con los meses del ano (previo)
        base = pd.read_csv(area / f"Escenario_base_{nombre.split('_')[0]}.csv")
        b1 = base[(base["Escenario"] == 1) & (pd.to_numeric(base["Periodo"]) // 100 == anio - 1)].copy()
        b1["Periodo"] = pd.to_numeric(b1["Periodo"]) + 100
        e1 = out[out["Escenario"] == 1].copy()
        e1["Periodo"] = pd.to_numeric(e1["Periodo"])
        llave = ["Tipo de Monto", "Ramo", "Periodo"]
        cruce = b1.merge(e1, on=llave, how="outer", suffixes=("_area", "_sal"), indicator=True)
        malos = int((cruce["_merge"] != "both").sum()) + int(sum(not _igual(a, b) for a, b in zip(
            cruce["Monto_USD_area"], cruce["Monto_USD_sal"]) if pd.notna(a) and pd.notna(b)))
        res.append(f"{'OK ' if len(b1) and not malos else 'MAL'} {nombre}: escenario 1 = presupuesto {anio - 1} con los meses de "
                   f"{anio} (previo): {len(e1)} renglones de {len(b1)}, {malos} distintos")
    # escenario 2 contra los montos de la BD, por tipo de monto, ramo y mes (RRC: cesion = IRR / BEL de la BD; SONR: con
    # SONR_NIVEL_BD, el BEL de la BD); los ramos que la BD no modela en el mes quedan con el metodo del area. En el RRC del
    # area BEL, BELG, IRR y MR van con signo negativo y BRUTO y NETO positivos
    conceptos = {"RRC": {"BEL": ("BEL", -1), "BELG": ("GTO", -1), "IRR": ("IRR", -1), "MR": ("MR", -1),
                         "BRUTO": ("BRUTO", 1), "NETO": ("NETO", 1)},
                 "SONR": {"BEL": ("BEL", 1), "IRR": ("IRR", 1), "MR": ("MR", 1), "BRUTO": ("BRUTO", 1), "NETO": ("NETO", 1)}}
    for reserva, mapa in conceptos.items():
        nombre = f"{reserva}_esc_{anio}.xlsx"
        if not (salida / nombre).exists():
            continue
        out = pd.read_excel(salida / nombre)
        e2 = out[out["Escenario"] == 2].groupby(["Tipo de Monto", "Ramo", "Periodo"])["Monto_USD"].sum()
        malos, n, fuera = {}, 0, set()
        for (tipo, ramo, per), monto in e2.items():
            if tipo not in mapa:
                continue
            if not ins._bd_modela(reserva, int(ramo), int(per)):
                fuera.add(int(ramo))
                continue
            n += 1
            esp = mapa[tipo][1] * ins.monto(f"{reserva} {mapa[tipo][0]}", int(per), int(ramo))
            if not abs(float(monto) - esp) <= 1e-6 * (1 + abs(esp)):
                malos.setdefault(tipo, set()).add(int(ramo))
        n_malos = sum(1 for (tipo, ramo, per), monto in e2.items() if tipo in malos and int(ramo) in malos[tipo])
        res.append(f"{'OK ' if n and not malos else 'MAL'} {nombre}: escenario 2 igual a los montos de la BD en "
                   f"{n - n_malos if malos else n} de {n} (tipo x ramo x mes)"
                   + (f"; distintos: {', '.join(f'{k} {sorted(v)}' for k, v in sorted(malos.items()))}" if malos else "")
                   + (f"; ramos sin BEL en la BD, con el metodo del area: {sorted(fuera)}" if fuera else ""))
    # ParamSONR: lo que falta del ano sale del mismo mes del ano anterior de la tabla del area
    prueba = InsumosBD.__new__(InsumosBD)
    prueba.__dict__.update(ins.__dict__)
    prueba.avisos = []
    tabla = pd.DataFrame([{"Llave": f"{(anio - 1) * 100 + m}-80", "Factor_Ret": 0.5 + m / 100, "Factor_MR": math.nan,
                           "Ind Sin SONR Media": 0.6, "Ind Sin SONR 99.5%": 0.7} for m in range(1, 13)])
    df = prueba.param_sonr_area(tabla, ramos_factor_ret_area=(80,), anio=anio)
    malos = sum(not _igual(float(df.loc[df["Llave"] == f"{anio * 100 + m}-80", "Factor_Ret"].iloc[0]), 0.5 + m / 100)
                if (df["Llave"] == f"{anio * 100 + m}-80").any() else True for m in range(1, 13))
    res.append(f"{'OK ' if not malos else 'MAL'} ParamSONR: el Factor_Ret del area de {anio} sale del mismo mes de {anio - 1} "
               f"en {12 - malos} de 12 meses")
    return res


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    carpeta = Path(sys.argv[1]).resolve()
    rrc, sonr = next(carpeta.glob("*RRC*_2027.py")), next(carpeta.glob("*SONR*_2027.py"))
    bd = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else buscar_bd(None, [SCRIPTS])
    trabajo = (Path(sys.argv[3]) if len(sys.argv) > 3 else Path(tempfile.mkdtemp(prefix="sim_aod_2027_"))).resolve()
    trabajo.mkdir(parents=True, exist_ok=True)
    for f in (rrc, sonr, SCRIPTS / "insumos_bd.py"):
        shutil.copy(f, trabajo / f.name)
    shutil.copy(bd, trabajo / NOMBRE_BD)
    if bd.with_name("Diagnostico_Proyeccion.xlsx").exists():
        shutil.copy(bd.with_name("Diagnostico_Proyeccion.xlsx"), trabajo / "Diagnostico_Proyeccion.xlsx")
    ins = InsumosBD(trabajo / NOMBRE_BD, verbose=False)
    anio = int(re.search(r"^zAño\s*=\s*(\d{4})", rrc.read_text(encoding="utf-8"), re.M).group(1))
    tablas_area(trabajo / "area", 2026)                     # (las tablas del area son las de 2026)
    capturas, textos, marcos = {}, [], []
    sin_base()
    salida = trabajo / "salida"
    redirigir(trabajo / "area", salida, capturas)
    try:
        g_rrc = correr(trabajo / rrc.name, trabajo / "cwd_ajena", textos, marcos)
        n_rrc = len(marcos)
        g_sonr = correr(trabajo / sonr.name, trabajo / "cwd_ajena", textos, marcos)
    finally:
        restaurar()
    lineas = [f"{'OK ' if g_rrc and g_sonr else 'MAL'} los dos scripts terminaron sin consultar la base Access"]
    lineas += verificar_rrc(ins, g_rrc, capturas, anio, sufijo="_2027")
    lineas += verificar_sonr(ins, g_sonr, marcos[n_rrc:], (trabajo / sonr.name).read_text(encoding="utf-8"), anio)
    lineas += verificar_2027(ins, capturas, marcos[n_rrc:], salida, anio, trabajo / "area")
    print("\n===== VERIFICACION")
    for x in lineas:
        print("  ", x)
    ok = not any(x.startswith("MAL") for x in lineas)
    print(f"\nCarpeta de trabajo: {trabajo}")
    print("RESULTADO: todo OK" if ok else "RESULTADO: con fallas")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
