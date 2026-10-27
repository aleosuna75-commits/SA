# -*- coding: utf-8 -*-
"""
Tipo de cambio MXN/USD mensual (supuesto de Inversiones) que se escribe en la columna TC de las BD.

Fuente: TC_Real_Esti.xlsx, hoja "TC":
  * 2026 -> columna "FCST" (202601-202608 = TC real con el que SAP convirtio a USD;
            202609-202612 = pronostico, interpolacion lineal de 16.9971 a 17.9000)
  * 2027 -> columna "FCST 2027"

Actualiza este diccionario cuando Inversiones publique un nuevo pronostico.
"""

TC_FCST = {
    # 2026 (FCST)
    202601: 17.4201,
    202602: 17.2318,
    202603: 17.9252,
    202604: 17.4688,
    202605: 17.3401,
    202606: 17.4986,
    202607: 17.3207,
    202608: 16.9971,
    202609: 17.222825,   # en pantalla 17.2228
    202610: 17.44855,    # en pantalla 17.4486
    202611: 17.674275,   # en pantalla 17.6743
    202612: 17.9000,
    # 2027 (FCST 2027)
    202701: 17.9500,
    202702: 18.0000,
    202703: 18.0500,
    202704: 18.1000,
    202705: 18.1500,
    202706: 18.2000,
    202707: 18.2500,
    202708: 18.3000,
    202709: 18.3500,
    202710: 18.4000,
    202711: 18.4500,
    202712: 18.5000,
}
