#!/usr/bin/env python3
"""Arma la versión de producción de Nuestro Nido en finanzas/web/.

Toma index.html (la misma página que se publica como artefacto de Claude), la envuelve en un
documento completo y le conecta Supabase (datos) y la función de Netlify (IA) con produccion/shim.js.
Lee SUPABASE_URL y SUPABASE_ANON_KEY del entorno (variables de Netlify)."""
import json, os, shutil, sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SALIDA = AQUI / "web"
SUPABASE_JS = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.118.0/dist/umd/supabase.js"

def main():
    fuente = (AQUI / "index.html").read_text(encoding="utf-8")
    corte = fuente.index('<div class="app">')
    cabeza, cuerpo = fuente[:corte], fuente[corte:]
    conexion = f'<script src="{SUPABASE_JS}"></script>\n<script src="config.js"></script>\n<script src="shim.js"></script>\n'
    primero = cuerpo.index("<script>")
    cuerpo = cuerpo[:primero] + conexion + cuerpo[primero:]
    pagina = f"""<!doctype html>
<html lang="es-MX">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<meta name="theme-color" content="#fdeff4">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Nuestro Nido">
<style>:root{{padding:env(safe-area-inset-top,0px) 0 env(safe-area-inset-bottom,0px)}}body{{margin:0}}img{{max-width:100%}}[hidden]{{display:none!important}}</style>
{cabeza}</head>
<body>
{cuerpo}</body>
</html>
"""
    if SALIDA.exists():
        shutil.rmtree(SALIDA)
    SALIDA.mkdir()
    (SALIDA / "index.html").write_text(pagina, encoding="utf-8")
    shutil.copytree(AQUI / "logos", SALIDA / "logos")
    shutil.copy(AQUI / "produccion" / "shim.js", SALIDA / "shim.js")
    url, llave = os.environ.get("SUPABASE_URL", "").strip(), os.environ.get("SUPABASE_ANON_KEY", "").strip()
    (SALIDA / "config.js").write_text("window.NIDO_CONFIG=" + json.dumps({"supabaseUrl": url, "supabaseAnonKey": llave}) + ";\n", encoding="utf-8")
    if not (url and llave):
        print("AVISO: faltan SUPABASE_URL o SUPABASE_ANON_KEY; la página abrirá sin datos compartidos.", file=sys.stderr)
    print(f"Listo: {SALIDA} ({len(pagina) // 1024} KB la página)")

if __name__ == "__main__":
    main()
