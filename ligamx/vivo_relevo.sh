#!/bin/bash
# Un paso del bucle del día de partido (produccion/VIVO.md, sección 6.3): espera el siguiente evento del vivo, deja la
# copia estable del documento (salidas/vivo_relevo.json) y anota hasta qué evento quedó atendido, para que cada
# despertar de la sesión sea una sola respuesta: escribir la copia en vivo/actual y volver a lanzar este guion.
# Sale con el código de `vivo.py esperar`: 0 evento, 3 observar ya no corre, 4 nada en 110 min, 5 observar colgado.
cd "$(dirname "$0")" || exit 9
N=$(cat salidas/vivo_ultimo_n.txt 2>/dev/null || echo 0)
python3 vivo.py esperar --desde "$N" > salidas/.vivo_esperar.tmp 2>&1; COD=$?
N2=$(python3 vivo.py estado | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('ultimo_n') or 0)")
cp salidas/vivo.json salidas/.vivo_relevo.tmp && mv salidas/.vivo_relevo.tmp salidas/vivo_relevo.json
echo "$N2" > salidas/vivo_ultimo_n.txt
head -1 salidas/.vivo_esperar.tmp | cut -c1-420
python3 -c "import json; d=json.load(open('salidas/vivo_relevo.json')); print('copia:', d.get('estado'), d.get('generado_utc'), '| ' + '; '.join(f\"{p['local']} {p.get('gl')}-{p.get('gv')} {p['visitante']} [{p.get('estado')}]\" for p in d.get('partidos', [])))"
echo "atendido hasta $N2 · codigo_esperar $COD"
exit $COD
