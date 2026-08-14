# Escudos de los equipos

Esta carpeta está vacía a propósito.

Los escudos de los clubes de Liga MX son **marcas registradas** y no se redistribuyen en
este repositorio. La página muestra en su lugar una insignia de monograma con los colores
reales de cada club, que se lee igual de rápido, pesa cero y no usa material ajeno.

## Si quieres usar los escudos reales

1. Consigue los archivos por una vía en la que tengas derecho a usarlos.
2. Guárdalos aquí como `<slug>.png` (fondo transparente, cuadrados, ~128 px).
   Los slugs están en `docs/equipos.js`: `ame`, `ats`, `ate`, `asl`, `caz`, `chi`, `jua`,
   `leo`, `mty`, `nec`, `pac`, `pue`, `pum`, `qro`, `san`, `tig`, `tij`, `tol`.
3. Agrega esos slugs a la lista `ESCUDOS` al inicio de `docs/equipos.js`:

   ```js
   const ESCUDOS = ["ame", "tol", "caz"];
   ```

Los equipos que no estén en la lista siguen mostrando su monograma, así que puedes ir
agregándolos de a poco. La lista existe para no disparar peticiones a archivos que no están.
