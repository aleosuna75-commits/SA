# -*- coding: utf-8 -*-
"""
Prueba de los criterios fijos v2.0 y de la traducción de ramos (Terremoto = 71, HyORH = 73).
Uso: python 05_prueba_criterios_fijos.py <carpeta_vacia>
Arma una 5_Generacion mínima: presupuesto 2027 con todo en HyORH (A073000000), Base_1 con FUENTE (REAL 2024-2025, PPTO 2026 y 2027),
Subramo con RamoN. Casos:
  A: real 60 % Terremoto / 40 % HyORH                -> AJUSTAR con peso real, Terremoto 2027 = 60 %
  B: sin real, presupuesto 2026 aprobado 70 / 30      -> AJUSTAR con PPTO_APROBADO_2026, Terremoto = 70 %
  C: sin datos                                        -> SIN_PESO, sin cambio
  D: real 2 % Terremoto (dentro de 5 pp)              -> NO_AJUSTAR
  E: sólo PPTO 2027 en la Base_1 (no debe usarse)     -> SIN_PESO
  F: contrato nuevo mono-HyORH de la cedente de A      -> cartera de la cedente (60 % Terremoto)
  G: contrato nuevo que la LN ya repartió 50/50        -> SIN_PESO, se respeta su partición
  H: contrato nuevo de la cedente de D (mono-ramo)     -> se deja como viene
  Con --sin-cartera, F queda SIN_PESO.
"""
import os, subprocess, sys
import numpy as np, pandas as pd
AQUI = os.path.dirname(os.path.abspath(__file__)); SCRIPT = os.path.join(AQUI, "..", "0_Redistribucion_TEV_HyOR.py")
G = os.path.abspath(sys.argv[1]); os.makedirs(os.path.join(G, "Inputs", "Redistribución"), exist_ok=True); os.makedirs(os.path.join(G, "Outputs"), exist_ok=True)
ll = {"A": (1, 10, 1), "B": (1, 20, 2), "C": (1, 30, 3), "D": (1, 40, 4), "E": (1, 50, 5), "F": (1, 10, 9), "G": (1, 60, 7), "H": (1, 40, 8)}
rows = []
for k, (tr, ced, cto) in ll.items():
    for mes in range(1, 13):
        rows.append({"/ERP/GL_ACCT": 6108010000, "/ERP/FUNCAREA": "LN04001", "/ERP/PROFTCTR": "A073000000", "ZCONTRATO": cto, "ZTIPOREAS": tr,
                     "ZCEDENTE": ced, "ZREGIONRP": "R01", "ZSUSCYEAR": 2027, "0FISCYEAR": 2027, "0CALMONTH": 202700 + mes, "/ERP/AMOUNT": -1000.0})
        if k == "G":  # la LN ya lo repartió 50/50
            rows[-1]["/ERP/AMOUNT"] = -500.0
            rows.append({**rows[-1], "/ERP/PROFTCTR": "A071000000"})
        rows.append({**rows[-1], "/ERP/GL_ACCT": 5301010000, "/ERP/AMOUNT": 120.0})
pd.DataFrame(rows).to_csv(os.path.join(G, "Inputs", "PptoTecnico2027.csv"), index=False)
pd.DataFrame({"CeBe": ["A071000000", "A073000000"], "Ramo": [71, 73], "Ramo2": [71, 73], "RamoN": ["Terremoto", "HyORH"]}).to_csv(os.path.join(G, "Inputs", "Subramo.csv"), index=False)
b = []
def add(k, desc, anio, frac, fuente):
    tr, ced, cto = ll[k]
    for mes in range(1, 13):
        b.append({"LLAVE": f"{tr}-{ced}-{cto}-LN04001", "DescRamo": desc, "AñoCont": anio, "MesCont": mes, "PmaTom": 500.0 * frac, "CosTom": 60.0 * frac,
                  "SinTom": 0.0, "FUENTE": fuente})
for anio in (2024, 2025):
    add("A", "TERREMOTO", anio, 0.6, "REAL"); add("A", "HYORH", anio, 0.4, "REAL")
    add("D", "TERREMOTO", anio, 0.02, "REAL"); add("D", "HYORH", anio, 0.98, "REAL")
add("B", "Terremoto", 2026, 0.7, "PPTO 2026 (BD_CtaMens_0526_1.xlsx)"); add("B", "HyORH", 2026, 0.3, "PPTO 2026 (BD_CtaMens_0526_1.xlsx)")
add("E", "Terremoto", 2027, 0.5, "PPTO 2027 (CtaMens_2027_5.xlsx)"); add("E", "HyORH", 2027, 0.5, "PPTO 2027 (CtaMens_2027_5.xlsx)")
pd.DataFrame(b).to_csv(os.path.join(G, "Inputs", "Redistribución", "Base_1_20261016_120000.csv"), index=False)
BASE_ARGS = ["--layout", "", "--pesos", "", "--td", "", "--pais", "", "--cesion", "", "--cesionpi", "", "--cesion-hist", "", "--matxl", "",
             "--dncostoxl", "", "--dnrecup", "", "--evcat", "", "--attritional", "", "--sin-sirec"]
r = subprocess.run([sys.executable, SCRIPT, "--ppto", os.path.join(G, "Inputs", "PptoTecnico2027.csv"), "--subramo", os.path.join(G, "Inputs", "Subramo.csv"),
                    "--salida", os.path.join(G, "Inputs", "PptoTecnico2027_Red.csv"), "--out-dir", os.path.join(G, "Outputs", "Redistribucion_TEV_HyOR"),
                    ] + BASE_ARGS, capture_output=True, text=True, encoding="utf-8", errors="replace")
ok_run = r.returncode == 0
print(f"[{'OK' if ok_run else 'FALLA'}] corrida automática (rc={r.returncode})")
if not ok_run:
    print((r.stdout + r.stderr)[-3000:]); sys.exit(1)
traza = sorted(f for f in os.listdir(os.path.join(G, "Outputs", "Redistribucion_TEV_HyOR")) if f.startswith("Trazabilidad"))[-1]
al = pd.read_excel(os.path.join(G, "Outputs", "Redistribucion_TEV_HyOR", traza), sheet_name="Alcance_LLAVEs").set_index("LLAVE")
red = pd.read_csv(os.path.join(G, "Inputs", "PptoTecnico2027_Red.csv"))
red["LLAVE"] = red["ZTIPOREAS"].astype(str) + "-" + red["ZCEDENTE"].astype(str) + "-" + red["ZCONTRATO"].astype(str) + "-" + red["/ERP/FUNCAREA"]
def share71(k, gl="61"):
    x = red[(red["LLAVE"] == "%s-%s-%s-LN04001" % ll[k]) & red["/ERP/GL_ACCT"].astype(str).str.startswith(gl)]
    t = x.groupby(x["/ERP/PROFTCTR"])["/ERP/AMOUNT"].sum()
    return float(t.get("A071000000", 0.0) / t.sum())
L = {k: "%s-%s-%s-LN04001" % v for k, v in ll.items()}
checks = {
    "busca la Base_1 más reciente sola": "Base_1_20261016_120000.csv" in r.stdout,
    "texto -> ramo con Subramo (Terremoto=71, HyORH=73)": "'TERREMOTO': 71" in r.stdout and "'HYORH': 73" in r.stdout,
    "años base AUTO = [2024, 2025]": "[2024, 2025]" in r.stdout,
    "A: AJUSTAR con peso real": al.loc[L["A"], "DECISION"] == "AJUSTAR" and str(al.loc[L["A"], "FUENTE_PESO"]).startswith("HIST"),
    "A: Terremoto 60 % en primas": abs(share71("A") - 0.6) < 1e-6,
    "A: Terremoto 60 % en comisiones": abs(share71("A", "53") - 0.6) < 1e-6,
    "B: AJUSTAR con presupuesto aprobado 2026": al.loc[L["B"], "DECISION"] == "AJUSTAR" and al.loc[L["B"], "FUENTE_PESO"] == "PPTO_APROBADO_2026",
    "B: Terremoto 70 %": abs(share71("B") - 0.7) < 1e-6,
    "B: alerta de presupuesto aprobado": "presupuesto aprobado" in str(al.loc[L["B"], "ALERTAS"]),
    "C: SIN_PESO y sin cambio": al.loc[L["C"], "DECISION"] == "SIN_PESO" and share71("C") == 0.0,
    "D: NO_AJUSTAR (dentro de tolerancia)": al.loc[L["D"], "DECISION"] == "NO_AJUSTAR",
    "E: el presupuesto 2027 nunca es peso": al.loc[L["E"], "DECISION"] == "SIN_PESO",
    "ningún REVISAR en modo fijo": (al["DECISION"] != "REVISAR").all(),
    "F: AJUSTAR con cartera de la cedente": al.loc[L["F"], "DECISION"] == "AJUSTAR" and al.loc[L["F"], "FUENTE_PESO"] == "CARTERA_CEDENTE",
    "F: Terremoto 60 % (mezcla real de la cedente)": abs(share71("F") - 0.6) < 1e-6,
    "F: alerta de contrato nuevo": "contrato nuevo" in str(al.loc[L["F"], "ALERTAS"]),
    "G: partición de la LN respetada": al.loc[L["G"], "DECISION"] == "SIN_PESO" and abs(share71("G") - 0.5) < 1e-9,
    "H: cedente mono-ramo, se deja como viene": al.loc[L["H"], "DECISION"] != "AJUSTAR" and share71("H") == 0.0,
    "total conservado": abs(red["/ERP/AMOUNT"].sum() - pd.read_csv(os.path.join(G, "Inputs", "PptoTecnico2027.csv"))["/ERP/AMOUNT"].sum()) < 1e-6,
}
for k, v in checks.items():
    print(f"[{'OK' if v else 'FALLA'}] {k}")
# sin cartera: F vuelve a quedar sin peso
r2 = subprocess.run([sys.executable, SCRIPT, "--ppto", os.path.join(G, "Inputs", "PptoTecnico2027.csv"), "--subramo", os.path.join(G, "Inputs", "Subramo.csv"),
                     "--salida", os.path.join(G, "Inputs", "PptoTecnico2027_Red2.csv"), "--out-dir", os.path.join(G, "Outputs", "sin_cartera"), "--sin-cartera"] + BASE_ARGS,
                    capture_output=True, text=True, encoding="utf-8", errors="replace")
t2 = sorted(f for f in os.listdir(os.path.join(G, "Outputs", "sin_cartera")) if f.startswith("Trazabilidad"))[-1]
al2 = pd.read_excel(os.path.join(G, "Outputs", "sin_cartera", t2), sheet_name="Alcance_LLAVEs").set_index("LLAVE")
checks["--sin-cartera: F queda SIN_PESO"] = r2.returncode == 0 and al2.loc[L["F"], "DECISION"] == "SIN_PESO"
print(f"[{'OK' if checks['--sin-cartera: F queda SIN_PESO'] else 'FALLA'}] --sin-cartera: F queda SIN_PESO")
print(f"\n{sum(checks.values()) + ok_run}/{len(checks) + 1} verificaciones OK")
sys.exit(0 if all(checks.values()) else 1)
