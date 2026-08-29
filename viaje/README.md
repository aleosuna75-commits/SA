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

**GitHub Pages no sirve para esta app.** Pages sólo publica desde la raíz del
repositorio o desde `/docs`, y las dos ya están ocupadas por el proyecto de Liga MX.
No hay opción de publicar desde `/viaje`.

**Netlify** es el camino, y es el mismo que ya usa este repositorio:

1. Entra a https://app.netlify.com y crea cuenta con *Sign up with GitHub*.
2. *Add new site* → *Import an existing project* → **GitHub** → elige el repositorio **SA**.
3. Configura:

   | Campo | Valor |
   |---|---|
   | Branch to deploy | `claude/app-viaje-cdmx-disneyland-fqh5eg` |
   | Build command | *(vacío)* |
   | Publish directory | `viaje` |

4. *Deploy site*, y luego *Site configuration* → *Change site name* para dejarlo
   en algo como `viaje-socal.netlify.app`.

Cada `git push` que toque `viaje/` republica solo. Es un sitio estático: no hay build.

## Instalar en el celular

- **iPhone**: abre la liga en **Safari** (no en Chrome) → botón Compartir → *Agregar a inicio*.
- **Android**: abre en Chrome → menú de tres puntos → *Instalar aplicación*.

Instalada desde su propia dirección, funciona **sin señal** después de abrirla una vez:
el service worker guarda todo en el teléfono. Eso es lo que la hace útil dentro de los
parques y cruzando la frontera.

Si en vez de eso guardas el enlace del artifact de Claude, funciona igual de bien pero
**necesita internet y sesión iniciada**: es una página, no una app instalada.

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
