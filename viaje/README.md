# Viaje SoCal 2026

App de viaje para la ruta **CDMX → Tijuana → San Diego → Anaheim → Los Ángeles**,
del 8 al 14 de septiembre de 2026.

Es una PWA sin dependencias, sin servidor y sin costo: HTML, CSS y JavaScript plano.
Se instala en el celular y funciona sin conexión.

## Qué trae

| Sección | Contenido |
|---|---|
| **Hoy** | Cuenta regresiva, lo que sigue en el día en curso, los candados de horario y los conflictos detectados del itinerario. |
| **Ruta** | Los 7 días bloque por bloque, con la hora, qué hacer y **por qué** está puesto a esa hora. |
| **Parques** | Plan de ataque de cada parque: principios del día, recorrido hora por hora, qué NO hacer y trucos. |
| **Listas** | Cuatro listas de verificación con progreso guardado. |
| **Gastos** | Registro por categoría con conversión USD ↔ MXN editable. |
| **Info** | Tiempos de traslado, reglas del viaje, fuentes consultadas y respaldo de datos. |

## Correr en local

```bash
cd viaje
python3 -m http.server 8000
# abrir http://localhost:8000
```

Se necesita servirla por HTTP (no `file://`) porque el service worker lo requiere.

## Publicar gratis

**GitHub Pages** — en Settings → Pages, elige la rama y la carpeta `/viaje`.
Queda en `https://<usuario>.github.io/<repo>/`.

**Netlify o Cloudflare Pages** — arrastra la carpeta `viaje/` a la interfaz web.
Sin build, sin configuración: es un sitio estático.

## Instalar en el celular

- **iPhone**: abre la liga en Safari → Compartir → *Agregar a pantalla de inicio*.
- **Android**: abre en Chrome → menú → *Instalar aplicación*.

Después de abrirla una vez, funciona sin señal. Útil en los parques, donde el wifi
de Disney es lento, y cruzando la frontera.

## Editar el contenido

Todo el contenido del viaje vive en **`js/data.js`**, separado de la lógica:

- `DIAS` — el itinerario día por día.
- `PARQUES` — los planes de ataque de cada parque.
- `ALERTAS` — los conflictos del itinerario.
- `TRASLADOS`, `CHECKLISTS`, `FUENTES`.

Cambiar una hora o agregar un bloque es editar ese archivo. No hay que tocar `app.js`.

## Datos del usuario

Las listas marcadas y los gastos se guardan en `localStorage`, sólo en el dispositivo.
No hay servidor ni cuenta. En Info hay botones para exportar respaldo y para borrar todo.

## Advertencia sobre horarios

Los horarios de parques, precios, calendarios de shows y fechas de eventos **cambian**.
Los datos de la app se verificaron contra fuentes públicas (listadas en la sección Info),
pero hay que confirmar en las apps oficiales de Disneyland y Universal antes de cada día.

## Version de un solo archivo

`build-artifact.py` une index.html, el CSS y los dos JS en un solo HTML, listo
para pegar en cualquier lado o publicar como pagina suelta. Quita el service
worker y el boton de respaldo, que solo funcionan en hosting propio.

```bash
python3 viaje/build-artifact.py salida.html
```
