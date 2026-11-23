"""
Regenera las predicciones walk-forward de modelo/pred/*.parquet (no van a git) cuando el contenedor se reinicia.

Sin ellas `modelo.mejora ciclo` compararía a los retadores sólo con el tramo de PRUEBA (los de DESARROLLO no se
rehacen solos) y `produccion/en_juego.py` conserva sus efectos viejos. No registra variantes nuevas
(registrar_variante=False): es la misma evaluación de siempre, sólo se vuelve a escribir.

    python3 -m modelo.restaurar_pred lista                 # qué falta
    python3 -m modelo.restaurar_pred correr ensamble ajuste # uno o varios, en DESARROLLO (por bloque)
    python3 -m modelo.restaurar_pred correr --prueba ensamble   # PRUEBA por día (queda en ACCESOS_PRUEBA.log)

Los nombres válidos son los finalistas de modelo/familias/candidatos.py y las líneas base que usa
modelo.mejora.pareadas (poisson_simple, cerebro_original_limpio, mercado_cierre_shin, mercado_abre_shin).
"""
from __future__ import annotations

import argparse
import sys
import time

from modelo import arnes, base
from modelo.familias import candidatos

REFERENCIAS = {
    "poisson_simple": lambda: base.PoissonSimple(),
    "mercado_cierre_shin": lambda: base.Mercado("cierre", "shin"),
    "mercado_abre_shin": lambda: base.Mercado("apertura", "shin"),
    "cerebro_original_limpio": lambda: base.CerebroOriginal(),
}


def modelo(nombre: str, prueba: bool):
    if nombre in REFERENCIAS:
        return REFERENCIAS[nombre]()
    fin = candidatos.finalistas()
    if nombre not in fin:
        sys.exit(f"modelo desconocido: {nombre}")
    m = fin[nombre]
    if prueba:                                       # mismo arreglo que modelo.mejora._modelo_dia
        for x in [m] + list(getattr(m, "modelos", [])):
            if hasattr(x, "tabla"):
                x.tabla = "partido"
    return m


def nombres() -> list[str]:
    return list(candidatos.finalistas()) + list(REFERENCIAS)


def lista() -> None:
    for n in nombres():
        d = (arnes.DIR_PRED / f"{n}.parquet").exists()
        p = (arnes.DIR_PRED / f"{n}__prueba__dia.parquet").exists()
        print(f"{n:26s} desarrollo={'sí' if d else 'FALTA'}  prueba_dia={'sí' if p else 'FALTA'}")


def correr(lista_nombres: list[str], prueba: bool) -> None:
    for n in lista_nombres:
        t = time.time()
        m = modelo(n, prueba)
        if prueba:
            arnes.evaluar(m, "prueba", "dia", permitir_prueba=True, quien="restaurar_pred",
                          registrar_variante=False, verbose=False)
        else:
            arnes.evaluar(m, registrar_variante=False, verbose=False)
        print(f"{n}: listo en {time.time() - t:.0f} s", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("lista")
    c = sub.add_parser("correr")
    c.add_argument("nombres", nargs="+")
    c.add_argument("--prueba", action="store_true")
    a = ap.parse_args()
    if a.cmd == "lista":
        lista()
    else:
        correr(a.nombres, a.prueba)
