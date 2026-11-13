# Nuestro Nido en producción (Netlify + Supabase + IA)

La página es la misma que el artefacto de Claude (`index.html`). Para vivir en su propia
dirección necesita tres cosas que hoy le presta Claude: dónde guardar los datos compartidos
(Supabase), quién puede entrar (dos usuarios con contraseña) y la IA (una llave de Anthropic).
Todo lo que sigue se hace una sola vez y toma unos 20 minutos.

## 1. Supabase: la base de datos (gratis)

1. Entra a https://supabase.com, crea cuenta y un proyecto nuevo (nombre `nuestro-nido`,
   región la más cercana, por ejemplo *East US*). Guarda la contraseña de la base; no se usa aquí.
2. Menú **SQL Editor** → *New query* → pega completo `produccion/supabase.sql` → **Run**.
3. Menú **Authentication → Users → Add user → Create new user**. Crea dos usuarios, uno por
   persona, con correo y contraseña, y deja marcado **Auto Confirm User**.
4. Menú **Authentication → Sign In / Providers**: apaga **Allow new users to sign up**.
   Este paso es el candado: sin él, cualquiera podría registrarse y ver sus finanzas.
5. Menú **Project Settings → API** (o *Data API* / *API Keys*): copia el **Project URL** y la llave
   **anon / publishable**. Esa llave es pública por diseño; la que nunca debe salir es la `service_role`.

## 2. Anthropic: la llave de la IA

1. Entra a https://console.anthropic.com, agrega saldo (con 5 USD alcanza para mucho tiempo)
   y crea una llave en **API Keys**.
2. Por defecto la función usa `claude-opus-5-5`. Si quieres gastar menos, en el paso 3 agrega la
   variable `ANTHROPIC_MODEL` con `claude-sonnet-5-5` o `claude-haiku-5-5`.

## 3. Netlify: la dirección

1. En https://app.netlify.com → **Add new site → Import an existing project** → GitHub →
   repositorio `SA`. Es un sitio nuevo, aparte del de F1 y Liga MX.
2. Configuración del build:
   - **Branch to deploy:** la rama donde esté este código (`main` cuando se haya integrado).
   - **Base directory:** `finanzas`
   - Lo demás lo toma solo de `finanzas/netlify.toml` (comando `python3 construir.py`, carpeta `web`).
3. **Environment variables** (antes de desplegar):
   - `SUPABASE_URL` = el Project URL
   - `SUPABASE_ANON_KEY` = la llave anon / publishable
   - `ANTHROPIC_API_KEY` = la llave de Anthropic (márcala como secreta)
4. **Deploy site**. Luego **Site configuration → Change site name** y ponle, por ejemplo,
   `nuestronido` para que quede en `https://nuestronido.netlify.app` (si está libre).
5. Dominio propio (opcional): se compra aparte (unos 12 USD al año) y se conecta en
   **Domain management → Add a domain**; Netlify pone el HTTPS.

## Modo abierto: sin contraseña, cualquiera con el enlace edita

Si prefieren no usar correo y contraseña:

1. En Supabase ejecuta `produccion/supabase-abierto.sql` en lugar de `supabase.sql` (o después de él).
   No hace falta crear usuarios.
2. En Netlify agrega la variable `NIDO_ABIERTO` con valor `1` y vuelve a desplegar.

Qué implica: quien tenga la dirección puede ver, cambiar y borrar todos los movimientos, y también
usar la IA con cargo a tu llave de Anthropic. No compartas la dirección en público y, si se filtra,
quita `NIDO_ABIERTO`, vuelve a ejecutar `supabase.sql` y crea los usuarios (pasos 1.3 y 1.4).

## 4. Probar

1. Abre la dirección: debe pedir correo y contraseña. Entra con uno de los dos usuarios.
2. Captura "tacos 180". Abre la página en otro teléfono con el otro usuario: debe aparecer solo.
3. En **Asesor IA** haz una pregunta. Si no responde, revisa en Netlify → **Logs → Functions → ai**.
4. En el iPhone: Safari → Compartir → **Agregar a pantalla de inicio** para tenerla como app.

## Qué cambia frente a la versión dentro de Claude

- Los datos de esta versión viven en Supabase; no se mezclan con los del artefacto de Claude.
- La IA se cobra a tu llave de Anthropic.
- Para cerrar sesión: toca tu nombre arriba → *Cerrar sesión en este dispositivo*.
- Cada cambio que llegue a la rama desplegada se publica solo.

## Archivos

| Archivo | Para qué |
|---|---|
| `index.html` | La app (fuente única para Claude y para producción) |
| `logos/` | Logos de marcas |
| `construir.py` | Arma `web/` para Netlify |
| `produccion/shim.js` | Conecta la app con Supabase y con la función de IA |
| `produccion/supabase.sql` | Tabla, permisos y tiempo real |
| `netlify/functions/ai.mjs` | La IA; solo responde a quien tiene sesión |
| `netlify.toml`, `package.json` | Configuración de Netlify |
