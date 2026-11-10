#!/usr/bin/env python3
"""Construye la página de Cerebro Liga MX.

    python3 web/construir.py                      # escribe web/index.html (fragmento) y web/archivos_publicados.json
    python3 web/construir.py --documento          # además un sitio estático completo en web/sitio/
    python3 web/construir.py --documento --salida DIR

Lee salidas/actual.json (contrato en salidas/CONTRATO.md) y web/medios.json, los incrusta en
plantilla.html dentro de <script type="application/json"> y escribe el resultado. Las imágenes y los
videos NO se incrustan: se referencian con rutas relativas (img/..., video/...). No calcula nada:
sólo valida, recorta medios.json a lo que la página usa y arma el archivo. Sólo biblioteca estándar.
"""
import argparse
import html
import json
import re
import shutil
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DATOS = AQUI.parent / "salidas" / "actual.json"
MEDIOS = AQUI / "medios.json"
PLANTILLA = AQUI / "plantilla.html"

# Qué foto o video va de fondo en cada banda (deben existir en medios.json con "usar": true).
ESCENAS = {
    "portada": "video/bbva-aerea-foto.mp4",
    "menu": "img/ambiente/cancha-noche.jpg",
    "proximos": "img/ambiente/reflectores-noche.jpg",
    "combinada": "img/ambiente/balon-pasto.jpg",
    "liguilla": "img/ambiente/reflectores-noche.jpg",
    "camino": "video/angel-festejo.mp4",
    "tabla": "img/ambiente/aficion-banderas.jpg",
    "ultima": "img/ambiente/red-porteria.jpg",
    "estadios": "video/estadio-cu-dron.mp4",
    "dominios": "video/final-noche.mp4",
    "modelo": "img/ambiente/cancha-aerea.jpg",
    "creditos": "img/ambiente/celebracion-pirotecnia.jpg",
}

# Campos sin los que la página no tiene sentido (ruta con puntos; [] = lista no vacía en cada elemento).
OBLIGATORIOS = [
    "meta.corte_local", "meta.torneo", "meta.modelo.descripcion", "meta.modelo.origen",
    "tabla", "pendientes", "ultimos_resultados",
    "proyeccion.campeon", "proyeccion.tabla_final", "proyeccion.cruces_cuartos",
    "liguilla.en_curso", "liguilla.series", "liguilla.formato",
    "fuerzas", "estadios", "dominios", "desempeno", "avisos",
]
OBLIGATORIOS_PARTIDO = [
    "id", "fecha_utc", "fecha_local", "hora_local", "etiqueta", "local", "visitante",
    "p_local", "p_empate", "p_visitante", "pick.resultado", "pick.equipo", "pick.prob",
    "marcador.gl", "marcador.gv", "estadio.nombre",
]
CAMPOS_MEDIO = ("archivo", "poster", "alt", "pos", "credito", "licencia", "licencia_url", "url_pagina", "ancho", "alto")


class ErrorDatos(Exception):
    pass


def _buscar(obj, ruta):
    for parte in ruta.split("."):
        if not isinstance(obj, dict) or parte not in obj:
            raise KeyError(ruta)
        obj = obj[parte]
    return obj


def validar(d):
    """Falla con un mensaje claro si falta algo obligatorio."""
    faltan = []
    for ruta in OBLIGATORIOS:
        try:
            valor = _buscar(d, ruta)
        except KeyError:
            faltan.append(ruta)
            continue
        if valor is None:
            faltan.append(ruta + " (viene null)")
    if "combinada_jornada" not in d:
        faltan.append("combinada_jornada (puede ser null, pero debe existir)")
    if not faltan:
        for nombre, n in (("tabla", 1), ("fuerzas", 1), ("proyeccion.campeon", 1), ("proyeccion.tabla_final", 1)):
            v = _buscar(d, nombre)
            if not isinstance(v, list) or len(v) < n:
                faltan.append(f"{nombre} (debe ser una lista no vacía)")
    if "pendientes" in d and d["pendientes"] is not None:
        if not isinstance(d["pendientes"], list):
            faltan.append("pendientes (debe ser una lista)")
        else:
            for i, p in enumerate(d["pendientes"]):
                for ruta in OBLIGATORIOS_PARTIDO:
                    try:
                        if _buscar(p, ruta) is None:
                            raise KeyError(ruta)
                    except KeyError:
                        quien = f"{p.get('local', '?')} vs {p.get('visitante', '?')}" if isinstance(p, dict) else "?"
                        faltan.append(f"pendientes[{i}].{ruta} ({quien})")
    if faltan:
        raise ErrorDatos("actual.json no cumple el contrato. Falta:\n  - " + "\n  - ".join(faltan))


def _medio(m):
    return {k: m[k] for k in CAMPOS_MEDIO if m.get(k) is not None}


def recortar_medios(medios, datos):
    """Deja de medios.json sólo lo que la página usa. Devuelve (recorte, rutas usadas, avisos)."""
    avisos = []
    usados = []
    disponibles = {}
    for v in medios.get("videos", []):
        if v.get("usar"):
            disponibles[v["archivo"]] = ("video", v)
    for a in medios.get("ambiente", []):
        if a.get("usar"):
            disponibles[a["archivo"]] = ("foto", a)
    fotos_respaldo = [k for k, (t, _) in disponibles.items() if t == "foto"]

    creditos = []
    escenas = {}
    for nombre, archivo in ESCENAS.items():
        if archivo not in disponibles:
            if not fotos_respaldo:
                raise ErrorDatos(f"medios.json no trae «{archivo}» con usar=true ni fotos de ambiente de respaldo.")
            avisos.append(f"escena «{nombre}»: «{archivo}» no está en medios.json con usar=true; se usa «{fotos_respaldo[0]}».")
            archivo = fotos_respaldo[0]
        tipo, m = disponibles[archivo]
        escenas[nombre] = dict(_medio(m), tipo=tipo)
        for ruta in (archivo, m.get("poster")):
            if ruta and ruta not in usados:
                usados.append(ruta)
        if not any(c["archivo"] == archivo for c in creditos):
            creditos.append({"grupo": "Videos" if tipo == "video" else "Ambiente",
                             "titulo": m.get("descripcion") or m.get("alt") or archivo,
                             "archivo": archivo, "credito": m.get("credito"), "licencia": m.get("licencia"),
                             "licencia_url": m.get("licencia_url"), "url_pagina": m.get("url_pagina"),
                             "cambios": m.get("cambios")})

    estadios = []
    for e in medios.get("estadios", []):
        fotos = []
        for i, f in enumerate(e.get("fotos", [])):
            fotos.append(_medio(f))
            usados.append(f["archivo"])
            creditos.append({"grupo": "Estadios", "titulo": f"{e['nombre']}, foto {i + 1}", "archivo": f["archivo"],
                             "credito": f.get("credito"), "licencia": f.get("licencia"),
                             "licencia_url": f.get("licencia_url"), "url_pagina": f.get("url_pagina"),
                             "cambios": f.get("cambios")})
        est = {k: e.get(k) for k in ("slug", "nombre", "apodo", "ciudad", "estado", "altitud_m", "capacidad",
                                      "superficie", "inaugurado", "dato", "equipos")}
        est["fotos"] = fotos
        estadios.append(est)

    equipos = [f["equipo"] for f in datos["tabla"]]
    for p in datos["pendientes"]:
        for eq in (p["local"], p["visitante"]):
            if eq not in equipos:
                equipos.append(eq)
    escudos = {}
    for eq in equipos:
        esc = medios.get("escudos", {}).get(eq)
        if not esc:
            avisos.append(f"sin escudo para «{eq}» en medios.json: la página mostrará sus iniciales.")
            continue
        escudos[eq] = {k: esc.get(k) for k in ("slug", "abr", "escudo", "c1", "c2", "fg")}
        usados.append(esc["escudo"])

    slugs = {e["slug"] for e in estadios}
    for p in datos["pendientes"]:
        slug = (p.get("estadio") or {}).get("slug")
        if slug not in slugs:
            avisos.append(f"{p['local']} vs {p['visitante']}: la sede «{slug}» no tiene fotos en medios.json.")

    # Portada: el favorito al título levantando el trofeo (la ocasión más reciente con foto libre); si no hay
    # foto libre de ese equipo, su estadio. Cambia sola cuando cambia el favorito.
    portada = escenas["portada"]
    leyenda = None
    camp = [c for c in datos["proyeccion"]["campeon"] if c.get("prob")]
    fav = camp[0]["equipo"] if camp else None
    tit = ((datos["proyeccion"].get("titulos") or {}).get(fav) or {}).get("ultimo") if fav else None
    foto = (medios.get("campeon") or {}).get(fav) if fav else None
    if foto and (AQUI / foto["archivo"]).exists():
        portada = dict(_medio(foto), tipo="foto")
        detalle = ", ".join(x for x in (foto.get("torneo"), foto.get("lugar")) if x)
        leyenda = (f"{fav} levanta el trofeo" if foto.get("tipo") == "trofeo" else f"{fav} festeja el título") + (f" · {detalle}" if detalle else "")
        usados.append(foto["archivo"])
        creditos.append({"grupo": "Campeones", "titulo": leyenda, "archivo": foto["archivo"], "credito": foto.get("credito"),
                         "licencia": foto.get("licencia"), "licencia_url": foto.get("licencia_url"),
                         "url_pagina": foto.get("url_pagina"), "cambios": foto.get("cambios")})
    elif fav:
        casa = next((e for e in estadios if fav in (e.get("equipos") or []) and e["fotos"]), None)
        if casa:
            portada = dict(casa["fotos"][0], tipo="foto")
            avisos.append(f"sin foto libre de {fav} con el trofeo: la portada usa su estadio ({casa['nombre']}).")
        if tit:
            leyenda = f"Último título de {fav}: {tit['torneo']}" + (f", {tit['estadio']}" if tit.get("estadio") else "")
    if leyenda and tit and foto and foto.get("torneo") and foto["torneo"] != tit["torneo"]:
        leyenda += f" (su último título fue el {tit['torneo']})"
    escenas["portada"] = portada
    recorte = {"portada": {"equipo": fav, "leyenda": leyenda}, "escenas": escenas, "estadios": estadios, "escudos": escudos,
               "nota_legal": medios.get("nota_legal"), "creditos": creditos}
    return recorte, usados, avisos


def _json_incrustado(obj):
    # "</" no puede aparecer dentro de <script>; el resto de JSON es texto válido ahí.
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def construir(datos, medios, plantilla):
    """Devuelve (fragmento_html, rutas usadas, avisos)."""
    validar(datos)
    recorte, usados, avisos = recortar_medios(medios, datos)
    portada = recorte["escenas"]["portada"]
    a = lambda x: html.escape(str(x or ""), quote=True)
    if portada.get("tipo") == "video":
        fondo = (f'<video id="video-portada" muted playsinline loop autoplay preload="metadata" poster="{a(portada.get("poster"))}" '
                 f'width="1280" height="720" aria-hidden="true" tabindex="-1" disablepictureinpicture>'
                 f'<source src="{a(portada["archivo"])}" type="video/mp4"></video>')
    else:
        fondo = (f'<img src="{a(portada["archivo"])}" alt="{a(portada.get("alt"))}" width="{a(portada.get("ancho") or 1600)}" '
                 f'height="{a(portada.get("alto") or 1000)}" style="object-position:{a(portada.get("pos") or "50% 40%")}" decoding="async" fetchpriority="high">')
    fondo += f'<figcaption class="credito">{html.escape(portada.get("credito") or "")}</figcaption>'
    reemplazos = {
        "{{PORTADA_FONDO}}": fondo,
        "{{DATOS}}": _json_incrustado(datos),
        "{{MEDIOS}}": _json_incrustado(recorte),
    }
    salida = plantilla
    for marca, valor in reemplazos.items():
        if marca not in salida:
            raise ErrorDatos(f"plantilla.html no contiene la marca {marca}.")
        salida = salida.replace(marca, valor)
    cabecera = salida.split('<script type="application/json"')[0]
    for prohibido in (r"<!doctype", r"<html[\s>]", r"<head[\s>]", r"<body[\s>]"):
        if re.search(prohibido, cabecera, re.I):
            raise ErrorDatos(f"plantilla.html debe ser un fragmento: sobra «{prohibido[:6]}».")
    return salida, usados, avisos


def como_documento(fragmento):
    """Envuelve el fragmento en un documento HTML completo (para verlo fuera de la plataforma)."""
    corte = fragmento.index("</style>") + len("</style>")
    cabeza, cuerpo = fragmento[:corte], fragmento[corte:]
    return ("<!doctype html>\n<html lang=\"es-MX\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
            "<meta name=\"theme-color\" content=\"#06120e\">\n"
            + cabeza + "\n</head>\n<body>" + cuerpo + "</body>\n</html>\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Construye web/index.html a partir de salidas/actual.json.")
    ap.add_argument("--datos", type=Path, default=DATOS, help="ruta de actual.json")
    ap.add_argument("--documento", action="store_true",
                    help="además genera un documento HTML completo (con <!doctype>, <head> y <body>)")
    ap.add_argument("--salida", type=Path, default=None,
                    help="directorio del sitio estático (por omisión web/sitio/). Si es la propia carpeta web/, "
                         "sólo escribe documento.html junto a img/ y video/, sin copiar nada")
    args = ap.parse_args(argv)
    t0 = time.time()
    try:
        for ruta in (args.datos, MEDIOS, PLANTILLA):
            if not ruta.exists():
                raise ErrorDatos(f"No existe {ruta}.")
        try:
            datos = json.loads(args.datos.read_text(encoding="utf-8"))
            medios = json.loads(MEDIOS.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ErrorDatos(f"JSON inválido: {e}")
        fragmento, usados, avisos = construir(datos, medios, PLANTILLA.read_text(encoding="utf-8"))
        faltan = [r for r in usados if not (AQUI / r).is_file()]
        if faltan:
            raise ErrorDatos("La página usa archivos que no existen en web/:\n  - " + "\n  - ".join(faltan))
    except ErrorDatos as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    def escribir(ruta, texto):
        tmp = ruta.with_suffix(ruta.suffix + ".tmp")
        tmp.write_text(texto, encoding="utf-8")
        tmp.replace(ruta)  # nunca queda un archivo a medias

    escribir(AQUI / "index.html", fragmento)
    publicados = sorted(set(usados))
    escribir(AQUI / "archivos_publicados.json", json.dumps(publicados, ensure_ascii=False, indent=1) + "\n")
    peso = sum((AQUI / r).stat().st_size for r in publicados)
    print(f"index.html: {len(fragmento.encode('utf-8')) / 1024:.0f} KB · {len(publicados)} archivos de medios "
          f"({peso / 1e6:.1f} MB) en archivos_publicados.json · corte {datos['meta']['corte_local']}")

    if args.documento:
        destino = (args.salida or (AQUI / "sitio")).resolve()
        doc = como_documento(fragmento)
        if destino == AQUI:
            escribir(AQUI / "documento.html", doc)
            print(f"documento: {AQUI / 'documento.html'}")
        else:
            destino.mkdir(parents=True, exist_ok=True)
            escribir(destino / "index.html", doc)
            for r in publicados:
                dst = destino / r
                src = AQUI / r
                if not dst.exists() or dst.stat().st_size != src.stat().st_size or dst.stat().st_mtime < src.stat().st_mtime:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
            print(f"sitio estático: {destino / 'index.html'} (+ {len(publicados)} archivos)")
    for a in avisos:
        print(f"aviso: {a}", file=sys.stderr)
    print(f"listo en {time.time() - t0:.2f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
