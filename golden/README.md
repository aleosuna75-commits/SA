# Golden file — línea base de la Jornada 2 (Fase 0)

Salida de referencia del modelo **antes de cualquier cambio**. Todo refactor posterior debe
reproducir estos números; si no, el refactor está mal.

## Cómo se generó

```powershell
& C:\Users\asunad\.venv\Scripts\python.exe cerebro_ligamx_2026.py `
    --historico historico_ligamx.csv `
    --csv pronostico_j2_apertura2026.csv `
    --excel Cerebro_LigaMX_J2.xlsx
```

| | |
|---|---|
| Modelo | `cerebro_ligamx_2026.py`, md5 `a69b14a000b3a3f8d246515f21949e8c` |
| Histórico | `historico_ligamx.csv`, 4,996 partidos, 2010-07-23 → 2026-07-18 |
| Fecha de referencia | **2026-08-14** (ver aviso abajo) |
| Duración | ~13 s |
| MLE | convergió, ventaja local estimada ×1.222 |

## Archivos

- `salida_consola.txt` — corrida completa: MLE, patrones H2H minados, pronóstico por partido
  con bitácora de ajustes, y los tres parlays. Es el artefacto principal para comparar.
- `pronostico_j2_apertura2026.csv` — 9 partidos con probabilidades y λ.
- `Cerebro_LigaMX_J2.xlsx` — workbook regenerado.

## Validación contra la salida publicada

Comparado contra el `Cerebro_LigaMX_J2.xlsx` de la raíz (el que ya circuló):

| Concepto | Resultado |
|---|---|
| Discrepancia máxima 1X2 | **0.0002** (error estándar de MC ≈ 0.0015) |
| Picks de quiniela | **9/9 idénticos** |
| Marcadores exactos | **9/9 idénticos** |
| Parlays | idénticos: 5 picks / 47.2%, 4 picks / 49.2%, 10 picks / 18.5% |

La discrepancia residual es ruido de Monte Carlo, no una diferencia de modelo. Desaparece al
calcular el 1X2 de forma exacta desde la matriz (§3.1 de `ARQUITECTURA.md`).

## Aviso: aún no es reproducible al 100%

`fit_dixon_coles` usa `date.today()` como origen del decaimiento temporal, así que la corrida
depende del día en que se ejecuta. Está **medido y es chico**: 25 días de calendario mueven
los ratings 0.27% y la dispersión relativa no cambia a 4 decimales. Pero para sellar
snapshots hace falta una `--fecha-referencia` explícita, que entra en la Fase 1. Al agregarla,
esta línea base debe reproducirse exactamente fijándola en `2026-08-14`.
