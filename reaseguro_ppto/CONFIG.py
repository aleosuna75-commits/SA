import getpass
import os

usuario = getpass.getuser()

ROOT = fr"C:\Users\asunad\OneDrive - GPV\Archivos de Maria Osmara Camacho Lopez - 2027\4_Validacion"

#ROOT = os.path.dirname(
#    os.path.dirname(__file__)
#)

INPUT = os.path.join(ROOT, "Inputs")

OUTPUT = os.path.join(ROOT, "Outputs")

ARCHIVO_PPTO = os.path.join(
    INPUT,
    "PptoTecnico2026.csv"
)

ARCHIVO_REAL = os.path.join(
    INPUT,
    "BD_Real.xlsx"
)

ARCHIVO_SUBRAMO = os.path.join(
    INPUT,
    "Subramo.csv"
)