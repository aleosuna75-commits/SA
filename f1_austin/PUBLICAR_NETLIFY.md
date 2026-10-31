# Publicar los pronósticos en Netlify con tu propio dominio

El sitio es una carpeta estática: `sitio_f1/` (en la raíz del repo). La genera `f1_austin/publicar_sitio.py`
a partir de los reportes HTML del modelo. No hay que compilar nada.

## 1. Generar el sitio

```bash
cd f1_austin
python3 publicar_sitio.py      # crea ../sitio_f1 con index.html (México), austin/qualy.html, austin/carrera.html
```

## 2. Desplegar (elige una opción)

**Opción A: arrastrar y soltar (60 segundos, como en el curso)**
1. Entra a <https://app.netlify.com> (crea la cuenta gratis si no la tienes).
2. En **Projects** (o en <https://app.netlify.com/drop>), arrastra la carpeta `sitio_f1`.
3. Netlify te da una URL provisional tipo `nombre-aleatorio.netlify.app`.
4. Cambia el nombre en **Project configuration → Change project name** (p. ej. `pronosticos-f1`).

Para actualizar después de cada GP: vuelve a generar el sitio y arrastra otra vez la carpeta en
**Deploys → Drag and drop**.

**Opción B: conectado a GitHub (se actualiza solo con cada push)**
1. En Netlify: **Add new project → Import an existing project → GitHub** y elige el repo `aleosuna75-commits/SA`.
2. Netlify lee `netlify.toml` de la raíz: publica la carpeta `sitio_f1` sin comando de build.
3. Rama a desplegar: la rama donde vivan los pronósticos (p. ej. `main` cuando se haga merge).
4. Desde entonces, cada push que actualice `sitio_f1/` se publica solo.

## 3. Conectar tu propio dominio

1. En el proyecto de Netlify: **Domain management → Add a domain** y escribe tu dominio (p. ej. `midominio.com`).
   Netlify agrega también `www.midominio.com`.
2. En el panel DNS de donde compraste el dominio (GoDaddy, Namecheap, Hostinger, Cloudflare…), crea:

   | Tipo | Host / Nombre | Valor |
   |---|---|---|
   | `A` (o `ALIAS`/`ANAME` si existe) | `@` | `75.2.60.5` (con ALIAS/ANAME: `apex-loadbalancer.netlify.com`) |
   | `CNAME` | `www` | `TU-PROYECTO.netlify.app` |

   Si sólo quieres un subdominio (p. ej. `f1.midominio.com`), basta con un `CNAME` `f1` → `TU-PROYECTO.netlify.app`.
   Borra registros `A`/`CNAME` anteriores que choquen con esos nombres.
3. Espera la propagación (minutos, hasta 24 h). Netlify muestra "Pending DNS verification" hasta que detecta los registros.
4. **HTTPS**: en **Domain management → HTTPS**, Netlify emite el certificado gratuito de Let's Encrypt automáticamente
   cuando el DNS ya apunta bien (botón *Verify DNS configuration* si tarda).

Alternativa: usar los DNS de Netlify (cambiar los *nameservers* del dominio a los que te indique Netlify en
**Set up Netlify DNS**); así Netlify administra todos los registros.

Referencia: <https://docs.netlify.com/manage/domains/configure-domains/configure-external-dns/>
