# Publicar el sitio: opciones

## Resumen

| Opción | Dirección | Costo | Tiempo |
|---|---|---|---|
| **Netlify** (recomendada) | `alepicks.netlify.app` | **gratis** | ~3 min |
| GitHub Pages | `aleosuna75-commits.github.io/SA/` | gratis | ~2 min |
| Dominio propio | `alepicks.com` | ~$12 USD/año | ~1 h + espera de DNS |

Verificado el 15-ago-2026: **`alepicks.netlify.app` está libre** (Netlify responde 404, o sea
nadie tomó ese nombre) y **`alepicks.com` no está registrado** (RDAP 404, DNS NXDOMAIN).

---

## Opción recomendada: Netlify, gratis y con tu nombre

Te deja en **https://alepicks.netlify.app**, se actualiza solo con cada `git push` igual que
Pages, y no depende del permiso de GitHub que bloqueó la activación automática.

1. Entra a **https://app.netlify.com** y crea cuenta con **Sign up with GitHub**.
2. *Add new site* → *Import an existing project* → **GitHub** → autoriza → elige el
   repositorio **SA**.
3. Configura así:

   | Campo | Valor |
   |---|---|
   | Branch to deploy | `claude/new-session-i9lrt6` |
   | Build command | *(déjalo vacío)* |
   | Publish directory | `docs` |

4. *Deploy site*. Te da una dirección fea tipo `random-name-123.netlify.app`.
5. *Site configuration* → *Change site name* → escribe **`alepicks`** → guardar.

Listo: **https://alepicks.netlify.app**

A partir de ahí, cada `git push` que toque `docs/` republica solo. Si algún día compras
`alepicks.com`, Netlify también lo conecta y te da el HTTPS gratis.

### Alternativa aún más rápida, sin repositorio

**https://app.netlify.com/drop** — arrastras `docs/vista_previa.html` y te da URL al
instante. Sirve para pasar la página hoy mismo, pero hay que volver a arrastrarla cada
jornada. Para uso continuo, mejor la opción de arriba.

---

## Opción B: GitHub Pages

Queda en `https://aleosuna75-commits.github.io/SA/`. Gratis, pero la dirección es más fea.

**https://github.com/aleosuna75-commits/SA/settings/pages** → *Source*: **Deploy from a
branch** → rama `claude/new-session-i9lrt6`, carpeta `/docs` → *Save*.

> Se intentó activar esto desde un workflow de Actions y GitHub lo rechazó
> (`Resource not accessible by integration`): el token de Actions no puede crear el sitio de
> Pages la primera vez. Ese clic tiene que ser manual.

---

## Opción C: alepicks.com, el dominio propio

Es el único que cuesta: **~$10-15 USD al año**. Todo lo demás (hosting, HTTPS, ancho de
banda) sigue gratis. Hazlo en este orden o no vas a saber qué está fallando.

### 1. Primero, que el sitio funcione en algún lado

Netlify u Opción B, arriba. Hasta que eso jale, no sigas.

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
