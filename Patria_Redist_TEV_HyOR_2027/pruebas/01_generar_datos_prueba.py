# -*- coding: utf-8 -*-
"""
Genera un juego de datos de prueba para 0_Redistribucion_TEV_HyOR.py a partir del extracto PptoTecnico2027.xlsx:
  <carpeta>/Inputs/PptoTecnico2027.csv                      (mismas 45 columnas; + 2 filas sintéticas GL 54 en 1-40-16 ramo 71)
  <carpeta>/Inputs/Redistribucion/Hist_Real_LLAVE_Ramo.csv  (histórico SINTÉTICO que cubre los casos de prueba)
  <carpeta>/Inputs/Redistribucion/Layout_Redistribucion.xlsx
Uso: python 01_generar_datos_prueba.py <PptoTecnico2027.xlsx> <carpeta_salida>
"""
import sys, os
import pandas as pd

src, dst = sys.argv[1], sys.argv[2]
os.makedirs(os.path.join(dst, "Inputs", "Redistribucion"), exist_ok=True)
df = pd.read_excel(src, sheet_name=0, engine="openpyxl") if src.lower().endswith((".xlsx", ".xlsm")) else pd.read_csv(src, thousands=",")
base = df.copy()
m = ((base["/ERP/FUNCAREA"] == "LN04001") & (base["ZTIPOREAS"] == 1) & (base["ZCEDENTE"] == 40) & (base["ZCONTRATO"] == 16)
     & (base["/ERP/PROFTCTR"] == "A071000000") & (base["/ERP/GL_ACCT"] == 6108010000) & (base["0FISCYEAR"] == 2027))
sin = base[m].head(2).copy()
if len(sin) == 2:
    sin["/ERP/GL_ACCT"] = 5402010000; sin["/ERP/AMOUNT"] = [12345.67, 2000.00]
    base = pd.concat([base, sin], ignore_index=True)
base.to_csv(os.path.join(dst, "Inputs", "PptoTecnico2027.csv"), index=False, encoding="utf-8")

rows = []
b27 = base[(base["0FISCYEAR"] == 2027) & (base["/ERP/GL_ACCT"] == 6108010000) & base["/ERP/PROFTCTR"].isin(["A071000000", "A073000000"])].copy()
b27["LLAVE"] = (b27["ZTIPOREAS"].fillna(0).astype(int).astype(str) + "-" + b27["ZCEDENTE"].fillna(0).astype(int).astype(str) + "-"
                + b27["ZCONTRATO"].fillna(0).astype(int).astype(str) + "-" + b27["/ERP/FUNCAREA"])
ESC = b27.groupby("LLAVE")["/ERP/AMOUNT"].sum().abs()  # prima 71+73 de 2027 por LLAVE
def add(llave, ramo, anio, gl, monto):
    """monto en 'unidades': se escala a la prima 2027 de la LLAVE (x 0.9 / 1000) para que el histórico sea creíble frente al presupuesto"""
    t, c, k, ln = llave.split("-")
    esc = float(ESC.get(llave, 1000.0)) * 0.9 / 1000.0
    rows.append(dict(ZTIPOREAS=int(t), ZCEDENTE=int(c), ZCONTRATO=int(k), FUNCAREA=ln, RAMO=ramo, ANIO=anio, GL=gl, MONTO=round(monto * esc, 2)))
add("1-264-19-LN04001", 71, 2025, 61, -730); add("1-264-19-LN04001", 73, 2025, 61, -270)       # ambos ramos; dentro de tolerancia; INCLUIR en layout
add("1-264-19-LN04001", 71, 2025, 53, 182);  add("1-264-19-LN04001", 73, 2025, 53, 68)
add("1-5-20-LN04001", 71, 2025, 61, -400);   add("1-5-20-LN04001", 73, 2025, 61, -600)         # ambos ramos; fuera de tolerancia -> REVISAR por defecto
add("1-40-16-LN04001", 71, 2025, 61, -400);  add("1-40-16-LN04001", 73, 2025, 61, -600)       # sólo 71 en ppto -> clones 73; comisiones propias 30/70
add("1-40-16-LN04001", 71, 2026, 61, -400);  add("1-40-16-LN04001", 73, 2026, 61, -600)
add("1-40-16-LN04001", 71, 2025, 53, 300);   add("1-40-16-LN04001", 73, 2025, 53, 700)
add("1-181-1-LN04001", 71, 2026, 61, -250);  add("1-181-1-LN04001", 73, 2026, 61, -750)        # sólo primas en hist -> comisiones con pesos de primas
add("1-486-1-LN04001", 73, 2025, 61, -1000)                                                    # 100% 73 en ambos -> sin cambio
add("1-296-6-LN04001", 71, 2025, 61, -350);  add("1-296-6-LN04001", 73, 2025, 61, -650)        # sólo 73 en ppto -> clones 71
add("1-32-71-LN04001", 71, 2024, 61, -100);  add("1-32-71-LN04001", 73, 2024, 61, -300)        # 3 años: ponderado 2025-26 = 50/50, último = 25/75
add("1-32-71-LN04001", 71, 2025, 61, -300);  add("1-32-71-LN04001", 73, 2025, 61, -100)
add("1-32-71-LN04001", 71, 2026, 61, -100);  add("1-32-71-LN04001", 73, 2026, 61, -300)
add("1-124-3-LN04001", 71, 2025, 61, -100);  add("1-124-3-LN04001", 73, 2025, 61, 50)          # signos opuestos -> inválido
add("1-9999-1-LN04001", 71, 2025, 61, -100); add("1-9999-1-LN04001", 73, 2025, 61, -100)       # LLAVE inexistente en ppto
add("1-181-4-LN04001", 71, 2025, 61, -500);  add("1-181-4-LN04001", 73, 2025, 61, -500)        # EXCLUIR en layout
pd.DataFrame(rows).to_csv(os.path.join(dst, "Inputs", "Redistribucion", "Hist_Real_LLAVE_Ramo.csv"), index=False)

lay = pd.DataFrame([
    dict(LLAVE="1-181-4-LN04001", ACCION="EXCLUIR", RAMO=None, PESO_PRIMA=None, FUENTE="Suscripción", JUSTIFICACION="Contrato renovado 2027 sólo HyOR (correo del suscriptor, fecha)"),
    dict(LLAVE="2-85-4-LN04001", ACCION="FORZAR", RAMO=71, PESO_PRIMA=0.5, FUENTE="Slip 2027 sección cobertura", JUSTIFICACION="El slip establece participación 50% TEV / 50% HyOR"),
    dict(LLAVE="2-85-4-LN04001", ACCION="FORZAR", RAMO=73, PESO_PRIMA=0.5, FUENTE="Slip 2027 sección cobertura", JUSTIFICACION="El slip establece participación 50% TEV / 50% HyOR"),
    dict(LLAVE="1-264-19-LN04001", ACCION="INCLUIR", RAMO=None, PESO_PRIMA=None, FUENTE="", JUSTIFICACION="Se pide ajustar aunque esté dentro de tolerancia"),
])
lay.to_excel(os.path.join(dst, "Inputs", "Redistribucion", "Layout_Redistribucion.xlsx"), index=False)
print("Datos de prueba generados en", dst, "| filas ppto:", len(base), "| filas hist:", len(rows))
