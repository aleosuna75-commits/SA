"""Diagnostico: por que las primas del PPTO salen tan bajas.

Uso:
    python DIAGNOSTICO_PRIMAS.py "ruta\\PptoTecnico2026.csv"

Compara el total del presupuesto con la conversion actual
(pd.to_numeric) contra la conversion corregida, sin tocar el resto
del framework.
"""

import sys
import pandas as pd

from utils.PARSEO import a_numerico, validar_importes

COLUMNA = "/ERP/AMOUNT"

# Ajustar si el mapeo de cuentas del loader es distinto.
CUENTAS = {
    "6108010000": "Primas",
    "5402010000": "Siniestros",
    "5402030000": "Siniestros",
    "5310010000": "Comisiones",
}


def main(ruta):

    ppto = pd.read_csv(
        ruta,
        usecols=["/ERP/GL_ACCT", COLUMNA, "/ERP/FUNCAREA", "0CALYEAR"],
        dtype=str,
        encoding="utf-8-sig"
    )

    print(f"Filas leidas: {len(ppto):,}")

    actual = pd.to_numeric(ppto[COLUMNA], errors="coerce")
    perdidas = actual.isna().sum()

    print(
        f"\nConversion ACTUAL  -> {perdidas:,} filas a NaN "
        f"({perdidas / len(ppto):.1%})"
    )

    corregido = a_numerico(ppto[COLUMNA], COLUMNA)

    print(f"Conversion NUEVA   -> {corregido.isna().sum():,} filas a NaN")

    validar_importes(ppto, corregido, COLUMNA, "(DIAGNOSTICO)")

    ppto["CONCEPTO"] = ppto["/ERP/GL_ACCT"].map(CUENTAS)
    ppto["ACTUAL"] = actual.fillna(0.0)
    ppto["CORREGIDO"] = corregido

    resumen = (
        ppto
        .dropna(subset=["CONCEPTO"])
        .groupby("CONCEPTO")[["ACTUAL", "CORREGIDO"]]
        .sum()
    )

    print("\nTOTALES PPTO (MXN)")
    print(
        resumen
        .apply(lambda c: c.map("{:,.2f}".format))
        .to_string()
    )

    # Filas atipicas que dominan el total una vez corregido el parseo.
    atipicas = ppto[ppto["CORREGIDO"].abs() >= 1e9]

    if not atipicas.empty:
        print(
            f"\nAVISO: {len(atipicas):,} filas con importe >= 1,000 millones. "
            "Revisar en el origen antes de publicar cifras."
        )
        print(
            atipicas
            .nlargest(10, "CORREGIDO", keep="all")
            .assign(CORREGIDO=lambda d: d["CORREGIDO"].map("{:,.2f}".format))
            [["/ERP/GL_ACCT", "/ERP/FUNCAREA", "0CALYEAR", "CORREGIDO"]]
            .to_string(index=False)
        )


if __name__ == "__main__":

    if len(sys.argv) < 2:
        raise SystemExit("Uso: python DIAGNOSTICO_PRIMAS.py <ruta_csv>")

    main(sys.argv[1])
