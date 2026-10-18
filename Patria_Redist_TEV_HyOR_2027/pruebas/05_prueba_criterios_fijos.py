# -*- coding: utf-8 -*-
"""
Prueba de los criterios fijos (v2.0) y del nivel 3 de cartera (v2.3), con la traducción de ramos Terremoto = 71, HyORH = 73.
Uso: python 05_prueba_criterios_fijos.py <carpeta_vacia>

Arma una 5_Generacion mínima: presupuesto 2027 con todo en HyORH (A073000000) salvo G, Base_1 con FUENTE (REAL 2024-2025, PPTO 2026 y 2027)
y Territorio, Subramo con RamoN. Casos:
  A: real 60 % Terremoto / 40 % HyORH                      -> AJUSTAR con peso real, Terremoto 60 %
  B: sin real, presupuesto 2026 aprobado 70 / 30            -> AJUSTAR con PPTO_APROBADO_2026, Terremoto 70 %
  C: sin datos propios; su grupo LN04001+tipo 1+México tiene 3 miembros en el ppto 2026 -> cartera (80 %)
  D: real 2 % Terremoto (dentro de 5 pp)                    -> NO_AJUSTAR
  E: sólo PPTO 2027 propio (50/50) en la Base_1            -> su 2027 nunca es peso: toma la cartera del grupo (80 %)
  N: sin datos ni grupo (LN04002)                           -> SIN_PESO, sin cambio
  F: nuevo, misma cedente y tipo que A                      -> cartera CEDENTE_TIPOREA (60 %)
  G: nuevo que la LN ya repartió 50/50                      -> se respeta su partición
  H: nuevo de la cedente de D (grupo del mismo ramo)        -> NO_AJUSTAR, sin cambio
  I: con historia 2026 inválida por reverso                 -> NO es candidato a cartera (SIN_PESO)
  J: nuevo cuya cedente es 100 % Terremoto                  -> reclasificación (100 % Terremoto); con --cartera-sin-reclasificar no se mueve
  K: en vigor (suscripción 2025) sin historia catastrófica  -> EN_VIGOR_CARTERA (70 %) y VALIDAR_SIREC; con --cartera-sin-en-vigor no se mueve
  L: prima diminuta (< 1,000)                               -> no es candidato
  M: facultativo de la cedente 70                           -> se salta el nivel cedente: usa LN+tipo+región (40 %), no la cedente (90 %)
  Con --sin-cartera, F queda SIN_PESO.
"""
import os, subprocess, sys
import numpy as np, pandas as pd
AQUI = os.path.dirname(os.path.abspath(__file__)); SCRIPT = os.path.join(AQUI, "..", "0_Redistribucion_TEV_HyOR.py")
G_ = os.path.abspath(sys.argv[1]); os.makedirs(os.path.join(G_, "Inputs", "Redistribución"), exist_ok=True); os.makedirs(os.path.join(G_, "Outputs"), exist_ok=True)
ll = {"A": (1, 10, 1), "B": (1, 20, 2), "C": (1, 30, 3), "D": (1, 40, 4), "E": (1, 50, 5), "F": (1, 10, 9), "G": (1, 60, 7), "H": (1, 40, 8),
      "I": (1, 65, 1), "J": (1, 80, 2), "K": (1, 90, 2), "L": (1, 95, 1), "M": (3, 70, 0), "N": (1, 99, 1)}
LN_DE = {"N": "LN04002"}
L = {k: "%s-%s-%s-" % v + LN_DE.get(k, "LN04001") for k, v in ll.items()}
rows = []
for k, (tr, ced, cto) in ll.items():
    for mes in range(1, 13):
        base = {"/ERP/GL_ACCT": 6108010000, "/ERP/FUNCAREA": LN_DE.get(k, "LN04001"), "/ERP/PROFTCTR": "A073000000", "ZCONTRATO": cto, "ZTIPOREAS": tr,
                "ZCEDENTE": ced, "ZREGIONRP": "R01", "ZSUSCYEAR": 2025 if k == "K" else 2027, "ZTIPOCES": 1, "0FISCYEAR": 2027,
                "0CALMONTH": 202700 + mes, "/ERP/AMOUNT": -50.0 if k == "L" else -1000.0}
        if k == "G":  # la LN ya lo repartió 50/50
            base["/ERP/AMOUNT"] = -500.0
            rows.append({**base, "/ERP/PROFTCTR": "A071000000"})
        rows.append(base)
        rows.append({**rows[-1], "/ERP/GL_ACCT": 5301010000, "/ERP/AMOUNT": 120.0})
ppto = pd.DataFrame(rows)
ppto.to_csv(os.path.join(G_, "Inputs", "PptoTecnico2027.csv"), index=False)
pd.DataFrame({"CeBe": ["A071000000", "A073000000"], "Ramo": [71, 73], "Ramo2": [71, 73], "RamoN": ["Terremoto", "HyORH"]}).to_csv(os.path.join(G_, "Inputs", "Subramo.csv"), index=False)
b = []
def add(llave, desc, anio, monto, fuente, terr="México"):
    for mes in range(1, 13):
        b.append({"LLAVE": llave, "DescRamo": desc, "Territorio": terr, "AñoCont": anio, "MesCont": mes, "PmaTom": monto, "CosTom": monto * 0.12,
                  "SinTom": 0.0, "FUENTE": fuente})
P26, P27 = "PPTO 2026 (BD_CtaMens_0526_1.xlsx)", "PPTO 2027 (CtaMens_2027_5.xlsx)"
for anio in (2024, 2025):
    add(L["A"], "TERREMOTO", anio, 300.0, "REAL"); add(L["A"], "HYORH", anio, 200.0, "REAL")
    add(L["D"], "TERREMOTO", anio, 10.0, "REAL"); add(L["D"], "HYORH", anio, 490.0, "REAL")
add(L["B"], "Terremoto", 2026, 350.0, P26); add(L["B"], "HyORH", 2026, 150.0, P26)
add(L["E"], "Terremoto", 2027, 250.0, P27); add(L["E"], "HyORH", 2027, 250.0, P27)
add(L["I"], "Terremoto", 2026, -50.0, P26); add(L["I"], "HyORH", 2026, 500.0, P26)      # reverso: historia 2026 inválida
add("1-80-1-LN04001", "Terremoto", 2026, 500.0, P26)                                      # cedente 80: 100 % Terremoto
add("1-90-1-LN04001", "Terremoto", 2026, 350.0, P26); add("1-90-1-LN04001", "HyORH", 2026, 150.0, P26)   # cedente 90: 70/30
for c_ in (71, 72, 73):                                                                   # facultativos LN04001 en México: 40/60
    add(f"3-{c_}-0-LN04001", "Terremoto", 2026, 200.0, P26); add(f"3-{c_}-0-LN04001", "HyORH", 2026, 300.0, P26)
add("3-70-5-LN04001", "Terremoto", 2026, 450.0, P26, "El Caribe"); add("3-70-5-LN04001", "HyORH", 2026, 50.0, P26, "El Caribe")  # misma cedente que M: 90/10
pd.DataFrame(b).to_csv(os.path.join(G_, "Inputs", "Redistribución", "Base_1_20261016_120000.csv"), index=False)
BASE_ARGS = ["--layout", "", "--pesos", "", "--td", "", "--pais", "", "--cesion", "", "--cesionpi", "", "--cesion-hist", "", "--matxl", "",
             "--dncostoxl", "", "--dnrecup", "", "--evcat", "", "--attritional", "", "--sin-sirec", "--subramo", os.path.join(G_, "Inputs", "Subramo.csv"),
             "--ppto", os.path.join(G_, "Inputs", "PptoTecnico2027.csv")]


def correr(nombre, extra):
    out = os.path.join(G_, "Outputs", nombre)
    r = subprocess.run([sys.executable, SCRIPT, "--salida", os.path.join(G_, "Inputs", f"Red_{nombre}.csv"), "--out-dir", out] + BASE_ARGS + extra,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print((r.stdout + r.stderr)[-3000:])
        return r, None, None
    t = sorted(f for f in os.listdir(out) if f.startswith("Trazabilidad"))[-1]
    al = pd.read_excel(os.path.join(out, t), sheet_name="Alcance_LLAVEs").set_index("LLAVE")
    red = pd.read_csv(os.path.join(G_, "Inputs", f"Red_{nombre}.csv"))
    red["LLAVE"] = red["ZTIPOREAS"].astype(str) + "-" + red["ZCEDENTE"].astype(str) + "-" + red["ZCONTRATO"].astype(str) + "-" + red["/ERP/FUNCAREA"]
    return r, al, red


def share71(red, k, gl="61"):
    x = red[(red["LLAVE"] == L[k]) & red["/ERP/GL_ACCT"].astype(str).str.startswith(gl)]
    t = x.groupby(x["/ERP/PROFTCTR"])["/ERP/AMOUNT"].sum()
    return float(t.get("A071000000", 0.0) / t.sum())


r, al, red = correr("base", [])
ok_run = r.returncode == 0
print(f"[{'OK' if ok_run else 'FALLA'}] corrida automática (rc={r.returncode})")
if not ok_run:
    sys.exit(1)
dec = lambda k: al.loc[L[k], "DECISION"]
fte = lambda k: str(al.loc[L[k], "FUENTE_PESO"])
caso = lambda k: str(al.loc[L[k], "CASO"])
checks = {
    "busca la Base_1 más reciente sola": "Base_1_20261016_120000.csv" in r.stdout,
    "texto -> ramo con Subramo (Terremoto=71, HyORH=73)": "'TERREMOTO': 71" in r.stdout and "'HYORH': 73" in r.stdout,
    "años base AUTO = [2024, 2025]": "[2024, 2025]" in r.stdout,
    "A: AJUSTAR con peso real, Terremoto 60 %": dec("A") == "AJUSTAR" and fte("A").startswith("HIST") and abs(share71(red, "A") - 0.6) < 1e-6,
    "A: comisiones siguen al 60 %": abs(share71(red, "A", "53") - 0.6) < 1e-6,
    "B: presupuesto aprobado 2026, Terremoto 70 %": dec("B") == "AJUSTAR" and fte("B") == "PPTO_APROBADO_2026" and abs(share71(red, "B") - 0.7) < 1e-6,
    "C: cartera LN+tipo+región (80 %)": fte("C") == "CARTERA_LN_TIPOREA_REGION" and abs(share71(red, "C") - 0.8) < 1e-6,
    "N: sin datos ni grupo, SIN_PESO sin cambio": dec("N") == "SIN_PESO" and share71(red, "N") == 0.0,
    "D: NO_AJUSTAR (dentro de tolerancia)": dec("D") == "NO_AJUSTAR",
    "E: su presupuesto 2027 nunca es peso (toma 80 %, no 50 %)": fte("E").startswith("CARTERA") and abs(share71(red, "E") - 0.8) < 1e-6,
    "F: cartera de la cedente con el mismo tipo (60 %)": dec("F") == "AJUSTAR" and fte("F") == "CARTERA_CEDENTE_TIPOREA" and abs(share71(red, "F") - 0.6) < 1e-6,
    "F: CASO NUEVO_CARTERA con alerta": caso("F") == "NUEVO_CARTERA" and "sin datos propios" in str(al.loc[L["F"], "ALERTAS"]),
    "G: partición de la LN respetada": dec("G") != "AJUSTAR" and abs(share71(red, "G") - 0.5) < 1e-9,
    "H: grupo del mismo ramo, no se toca": dec("H") == "NO_AJUSTAR" and share71(red, "H") == 0.0,
    "I: historia con reverso no recibe cartera": not fte("I").startswith("CARTERA") and share71(red, "I") == 0.0,
    "J: reclasificación por grupo 100 % Terremoto": dec("J") == "AJUSTAR" and caso("J") == "NUEVO_CARTERA_RECLASIFICA" and abs(share71(red, "J") - 1.0) < 1e-9,
    "K: en vigor toma cartera (70 %) y va a SIREC": caso("K") == "EN_VIGOR_CARTERA" and abs(share71(red, "K") - 0.7) < 1e-6 and bool(al.loc[L["K"], "VALIDAR_SIREC"]),
    "L: prima diminuta no es candidata": not fte("L").startswith("CARTERA") and share71(red, "L") == 0.0,
    "M: facultativo usa LN+tipo+región (40 %), no la cedente (90 %)": fte("M") == "CARTERA_LN_TIPOREA_REGION" and abs(share71(red, "M") - 0.4) < 1e-6,
    "ningún REVISAR en modo fijo": (al["DECISION"] != "REVISAR").all(),
    "total conservado": abs(red["/ERP/AMOUNT"].sum() - ppto["/ERP/AMOUNT"].sum()) < 1e-6,
    "hojas Cartera_Nuevos, Cartera_Confirmar y Backtest_Cartera": all(s_ in pd.ExcelFile(os.path.join(G_, "Outputs", "base", sorted(f for f in os.listdir(os.path.join(G_, "Outputs", "base")) if f.startswith("Trazabilidad"))[-1])).sheet_names
                                                                      for s_ in ("Cartera_Nuevos", "Cartera_Confirmar", "Backtest_Cartera")),
}
r2, al2, red2 = correr("sin_reclasificar", ["--cartera-sin-reclasificar"])
checks["--cartera-sin-reclasificar: J no se mueve"] = r2.returncode == 0 and al2.loc[L["J"], "DECISION"] == "NO_AJUSTAR" and share71(red2, "J") == 0.0
r3, al3, red3 = correr("sin_en_vigor", ["--cartera-sin-en-vigor"])
checks["--cartera-sin-en-vigor: K no se mueve, F sí"] = (r3.returncode == 0 and al3.loc[L["K"], "DECISION"] == "NO_AJUSTAR" and share71(red3, "K") == 0.0
                                                         and abs(share71(red3, "F") - 0.6) < 1e-6)
r4, al4, red4 = correr("sin_cartera", ["--sin-cartera"])
checks["--sin-cartera: F queda SIN_PESO"] = r4.returncode == 0 and al4.loc[L["F"], "DECISION"] == "SIN_PESO"
for k, v in checks.items():
    print(f"[{'OK' if v else 'FALLA'}] {k}")
print(f"\n{sum(checks.values()) + ok_run}/{len(checks) + 1} verificaciones OK")
sys.exit(0 if all(checks.values()) else 1)
