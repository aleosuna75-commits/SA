# El sitio

Todo lo que se publica vive en esta carpeta. Es HTML, CSS y JavaScript planos:
sin build, sin npm, sin dependencias.

## Publicar en GitHub Pages (una sola vez)

1. Entra a **https://github.com/aleosuna75-commits/SA/settings/pages**
2. En *Build and deployment* → *Source*, elige **Deploy from a branch**
3. Branch: **`claude/new-session-i9lrt6`** · carpeta: **`/docs`** → *Save*

En un par de minutos queda en:

**https://aleosuna75-commits.github.io/SA/**

A partir de ahí, cada `git push` que toque `docs/` republica el sitio solo. No
hay que volver a entrar a Settings.

> Se intentó activar Pages desde un workflow de Actions, pero el token de
> Actions no puede crear el sitio la primera vez (`Resource not accessible by
> integration`). Por eso ese primer clic es manual. Con *Deploy from a branch*
> tampoco hace falta ningún workflow después.

## Archivos

| Archivo | Qué es |
|---|---|
| `index.html` | La página: índice de jornadas y vista de jornada |
| `estilos.css` | Paleta GPV, tema claro y oscuro, mobile-first |
| `app.js` | Render. **No calcula probabilidades**: sólo formatea |
| `equipos.js` | Colores e insignias de cada equipo |
| `datos/indice.json` | Catálogo de las 17 jornadas y desempeño acumulado |
| `datos/jNN.json` | Una jornada: pronóstico, bitácora, parlays y resultados |
| `datos/proyeccion.json` | Probabilidades de campeón |
| `escudos/` | Vacía. Ver `preparar_escudos.py` en la raíz |
| `vista_previa.html` | El sitio en un solo archivo, para compartir o abrir sin servidor |
| `.nojekyll` | Le dice a Pages que sirva los archivos tal cual |

## Regenerar

Desde la raíz del repositorio:

```powershell
python generar.py                      # todas las jornadas + proyección
python docs\construir_vista_previa.py  # rearma vista_previa.html
```
