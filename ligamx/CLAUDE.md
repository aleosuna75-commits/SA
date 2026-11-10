# Cerebro Liga MX

Pronósticos de la Liga MX (partido, combinada de 4 picks, liguilla y campeón) con datos de ESPN, validación
walk-forward y página publicada como Artifact. **El estado, el runbook diario y los pendientes viven en `ESTADO.md`:
léelo primero.**

## Comandos
- Todo de una vez: `python3 pipeline.py auto` (datos → variables → mejora → pronósticos → página). Después, si
  `salidas/ultimo_auto.json` dice `publicar: true`, republicar `web/index.html` y correr `python3 pipeline.py publicado`.
- Por partes: `python3 datos/espn_descarga.py actualizar` · `python3 -m modelo.mejora estado|ciclo|adoptar` ·
  `python3 -m produccion.exportar` · `python3 web/construir.py [--documento --salida DIR]`.
- Pruebas: `python3 -m pytest modelo/pruebas produccion/pruebas -q`; página: `web/LEEME.md` (Chromium y WebKit).

## Reglas (no romper)
- Sin fugas: todo se ajusta sólo con partidos anteriores al corte; el arnés (`modelo/arnes.py`) lo verifica.
- El modelo de producción es el de `modelo/campeon.json`; sólo se cambia con `modelo.mejora` (regla de 2 errores
  estándar pareados y no peor en los últimos 8 bloques, o decisión manual con motivo escrito).
- JavaScript no calcula probabilidades: la página sólo da formato a `salidas/actual.json` (contrato en
  `salidas/CONTRATO.md`).
- Nada inventado: córners y tarjetas no se pronostican (no superaron a la frecuencia de liga); ningún modelo le
  gana al mercado de cierre y la página lo dice.
- Página: fragmento sin doctype para el Artifact, un solo tema oscuro con tokens, cada bloque aislado con
  `seguro()`, sin `location.hash`; probar siempre en WebKit además de Chromium.
- Fotos y videos: sólo con licencia libre y crédito visible (`web/medios.json`). Escudos: uso nominativo con nota legal.
