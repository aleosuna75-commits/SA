# Publicar en alepicks.com

Sí se puede, y GitHub Pages lo soporta **gratis, con HTTPS incluido** (certificado
Let's Encrypt que se renueva solo).

**Verificado el 15-ago-2026: `alepicks.com` está libre.** No está registrado — NXDOMAIN en
DNS y 404 en el registro de Verisign. Si lo quieres, agárralo, porque eso cambia.

## Lo único que cuesta dinero

El dominio: **~$10-15 USD al año** en cualquier registrador (Cloudflare lo vende casi a
precio de costo; Namecheap, GoDaddy y Google/Squarespace también sirven). Todo lo demás
—hosting, HTTPS, ancho de banda— sigue siendo gratis. Es el único gasto del proyecto.

---

## Orden de los pasos

Hazlos en este orden. Si montas el dominio antes de que el sitio funcione, después no sabes
qué está fallando.

### 1. Primero, que funcione en github.io

**https://github.com/aleosuna75-commits/SA/settings/pages** → *Source*: **Deploy from a
branch** → rama `claude/new-session-i9lrt6`, carpeta `/docs` → *Save*.

Comprueba que abre **https://aleosuna75-commits.github.io/SA/**. Hasta que eso jale, no sigas.

### 2. Registra el dominio

Compra `alepicks.com` donde prefieras.

### 3. Configura el DNS en el registrador

Para que **alepicks.com** (sin www) apunte a GitHub, cuatro registros **A**:

| Tipo | Nombre | Valor |
|---|---|---|
| A | `@` | `185.199.108.153` |
| A | `@` | `185.199.109.153` |
| A | `@` | `185.199.110.153` |
| A | `@` | `185.199.111.153` |

Y si quieres que **www.alepicks.com** también funcione, un registro **CNAME**:

| Tipo | Nombre | Valor |
|---|---|---|
| CNAME | `www` | `aleosuna75-commits.github.io.` |

Opcional, para IPv6, cuatro registros **AAAA** en `@`:
`2606:50c0:8000::153`, `2606:50c0:8001::153`, `2606:50c0:8002::153`, `2606:50c0:8003::153`

> El DNS tarda de unos minutos a unas horas en propagarse. Es normal.

### 4. Dile a GitHub cuál es tu dominio

De vuelta en **Settings → Pages**, en *Custom domain* escribe `alepicks.com` y guarda.

GitHub crea solo el archivo `docs/CNAME` en el repositorio y empieza a verificar el DNS.
Cuando termine, marca la casilla **Enforce HTTPS** (puede tardar hasta 24 h en habilitarse
mientras se emite el certificado).

Listo: **https://alepicks.com** sirviendo tu sitio.

---

## Por qué el archivo `CNAME` no está ya puesto

Sería contraproducente. Si el repositorio declara `alepicks.com` antes de que el dominio
exista y apunte a GitHub, Pages deja de servir en `github.io` y redirige a un dominio que no
responde: te quedas sin sitio. Por eso el orden importa, y por eso el paso 4 va al final.

En cuanto tengas el dominio, dímelo y lo dejo puesto en el repositorio — aunque si lo
configuras desde Settings, GitHub lo agrega solo y no hace falta que yo toque nada.

---

## Si prefieres no comprar dominio

Dos alternativas sin costo:

- **https://aleosuna75-commits.github.io/SA/** — el paso 1 y ya. Funciona igual, sólo que la
  dirección es más fea.
- **Netlify Drop** (https://app.netlify.com/drop): arrastras `docs/vista_previa.html` y te da
  una URL al instante, sin repositorio ni cuenta. Útil para pasar la página de volada, pero
  hay que volver a arrastrarla cada jornada.
