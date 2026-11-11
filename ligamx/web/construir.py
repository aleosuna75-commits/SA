#!/usr/bin/env python3
"""Construye la página de Cerebro Liga MX.

    python3 web/construir.py                      # escribe web/index.html (fragmento) y web/archivos_publicados.json
    python3 web/construir.py --documento          # además un sitio estático completo en web/sitio/
    python3 web/construir.py --documento --salida DIR
    python3 web/construir.py --vivo RUTA          # de prueba: incrusta ese documento en vivo (forma: salidas/vivo_ejemplo.json)
    python3 web/construir.py --portada EQUIPO     # de prueba: fuerza el equipo de la portada (para revisar las 16)

Las dos opciones de prueba NO tocan index.html ni archivos_publicados.json: sólo escriben el documento completo
(web/documento.html, o el sitio de --salida), para que un ensayo nunca llegue a publicarse por descuido.

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

# Portada: la foto del estadio del favorito al título, elegida a mano (la mejor nocturna o aérea de cada casa).
#   pos       encuadre en vertical (celular): la foto ocupa la parte alta de la portada
#   pos_ancho encuadre en horizontal (escritorio): la foto cubre toda la portada
#   lado      en pantallas anchas, de qué lado va el texto para no tapar el estadio ("izq" o "der")
#   zoom      en pantallas anchas, acercamiento inicial (1.04 si no se indica); el punto fijo es pos_ancho
#   dx_ancho  (opcional) en pantallas anchas, corre la foto de lado (% de su ancho; negativo = a la izquierda) cuando
#             el estadio está al centro y el texto no cabría a su lado; el borde que queda libre se funde con el fondo
#   tono      "noche" (ya es oscura), "ocaso" o "dia" (se oscurece y se enfría para que no queme el cielo)
PORTADAS = {
    "banorte": {"foto": "img/estadios/banorte-3.jpg", "pos": "9% 50%", "pos_ancho": "100% 100%", "zoom": 1.05, "dx_ancho": "-27%", "lado": "der", "tono": "noche"},
    "bbva": {"foto": "img/estadios/bbva-2.jpg", "pos": "60% 50%", "pos_ancho": "50% 40%", "lado": "izq", "tono": "ocaso"},
    "volcan": {"foto": "img/estadios/volcan-1.jpg", "pos": "50% 30%", "pos_ancho": "50% 35%", "lado": "izq", "tono": "ocaso"},
    "cu": {"foto": "img/estadios/cu-3.jpg", "pos": "55% 60%", "pos_ancho": "50% 62%", "lado": "izq", "tono": "ocaso"},
    "corona": {"foto": "img/estadios/corona-1.jpg", "pos": "42% 50%", "pos_ancho": "50% 42%", "lado": "izq", "tono": "ocaso"},
    "caliente": {"foto": "img/estadios/caliente-2.jpg", "pos": "38% 50%", "pos_ancho": "50% 30%", "lado": "izq", "tono": "noche"},
    "nemesio": {"foto": "img/estadios/nemesio-1.jpg", "pos": "55% 50%", "pos_ancho": "50% 55%", "lado": "izq", "tono": "dia"},
    "akron": {"foto": "img/estadios/akron-2.jpg", "pos": "50% 50%", "pos_ancho": "50% 45%", "lado": "izq", "tono": "dia"},
    "hidalgo": {"foto": "img/estadios/hidalgo-3.jpg", "pos": "28% 40%", "pos_ancho": "50% 38%", "lado": "der", "tono": "noche"},
    "cuauhtemoc": {"foto": "img/estadios/cuauhtemoc-2.jpg", "pos": "40% 60%", "pos_ancho": "50% 62%", "lado": "der", "tono": "dia"},
    "corregidora": {"foto": "img/estadios/corregidora-2.jpg", "pos": "55% 50%", "pos_ancho": "50% 45%", "lado": "izq", "tono": "noche"},
    "jalisco": {"foto": "img/estadios/jalisco-1.jpg", "pos": "45% 50%", "pos_ancho": "50% 55%", "lado": "izq", "tono": "dia"},
    "victoria": {"foto": "img/estadios/victoria-1.jpg", "pos": "50% 50%", "pos_ancho": "50% 60%", "lado": "izq", "tono": "dia"},
    "leon": {"foto": "img/estadios/leon-1.jpg", "pos": "40% 45%", "pos_ancho": "50% 40%", "lado": "izq", "tono": "ocaso"},
    "lastras": {"foto": "img/estadios/lastras-2.jpg", "pos": "50% 50%", "pos_ancho": "50% 45%", "lado": "izq", "tono": "noche"},
    "benitojuarez": {"foto": "img/estadios/benitojuarez-2.jpg", "pos": "40% 45%", "pos_ancho": "50% 40%", "lado": "izq", "tono": "ocaso"},
}
# Fotos de festejo de campeonato (medios.json → campeon): mismo ajuste, por equipo.
PORTADAS_CAMPEON = {
    "Toluca": {"pos": "62% 40%", "pos_ancho": "50% 45%", "lado": "izq", "tono": "noche"},
    "Pumas": {"pos": "55% 30%", "pos_ancho": "50% 30%", "lado": "der", "tono": "dia"},
}
PORTADA_RESPALDO = "banorte"  # si no hay favorito o su estadio no tiene fotos
# Capacidades del Artifact que la página usa (se declaran al publicar; ver LEEME.md).
CAPACIDADES = {"db": {"rules": [{"path": "vivo", "read": "view", "write": "admin"}]}, "user": {}}

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


def recortar_medios(medios, datos, forzar_portada=None):
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

    # Portada: cambia sola con el favorito al título (proyeccion.campeon[0]). Fondo = foto libre de su festejo de
    # campeón si existe (medios.json → campeon); si no, la foto elegida a mano de su estadio (PORTADAS).
    camp = [c for c in datos["proyeccion"]["campeon"] if c.get("prob")]
    fav = forzar_portada or (camp[0]["equipo"] if camp else None)
    casa = next((e for e in medios.get("estadios", []) if fav in (e.get("equipos") or [])), None) if fav else None
    festejo = (medios.get("campeon") or {}).get(fav) if fav else None
    foto, ajuste, pie = None, {}, None
    if festejo and (AQUI / festejo["archivo"]).is_file():
        foto, ajuste = festejo, PORTADAS_CAMPEON.get(fav, {})
        donde = ", ".join(x for x in (festejo.get("torneo"), festejo.get("lugar")) if x)
        pie = ("El trofeo en manos de " if festejo.get("tipo") == "trofeo" else "Festejo del título de ") + fav + (f": {donde}" if donde else "")
        creditos.append({"grupo": "Campeones", "titulo": pie, "archivo": festejo["archivo"], "credito": festejo.get("credito"),
                         "licencia": festejo.get("licencia"), "licencia_url": festejo.get("licencia_url"),
                         "url_pagina": festejo.get("url_pagina"), "cambios": festejo.get("cambios")})
    else:
        if not casa:
            casa = next((e for e in medios.get("estadios", []) if e.get("slug") == PORTADA_RESPALDO), None)
            if fav:
                avisos.append(f"{fav} no tiene estadio en medios.json: la portada usa el {casa['nombre'] if casa else 'fondo liso'}.")
        if casa:
            ajuste = PORTADAS.get(casa["slug"], {})
            foto = next((f for f in casa.get("fotos", []) if f["archivo"] == ajuste.get("foto")), None)
            if not foto and casa.get("fotos"):
                foto = casa["fotos"][0]
                avisos.append(f"portada: PORTADAS no tiene foto válida para «{casa['slug']}»; se usa {foto['archivo']}.")
            if foto:
                de = [e for e in (casa.get("equipos") or [])]
                pie = casa["nombre"] + (f", donde juega {fav}" if fav and fav in de else "")
    if not foto:
        raise ErrorDatos("No hay foto para la portada: revisa PORTADAS y medios.json.")
    portada = dict(_medio(foto), tipo="foto", pos=ajuste.get("pos") or foto.get("pos") or "50% 50%",
                   pos_ancho=ajuste.get("pos_ancho") or foto.get("pos") or "50% 50%",
                   lado=ajuste.get("lado") or "izq", tono=ajuste.get("tono") or "dia", zoom=ajuste.get("zoom") or 1.04,
                   dx_ancho=ajuste.get("dx_ancho") or "", pie=pie)
    if foto["archivo"] not in usados:
        usados.append(foto["archivo"])
    escenas["portada"] = portada
    recorte = {"portada": {"equipo": fav, "estadio": casa["nombre"] if casa else None}, "escenas": escenas, "estadios": estadios,
               "escudos": escudos, "nota_legal": medios.get("nota_legal"), "creditos": creditos}
    return recorte, usados, avisos


def _json_incrustado(obj):
    # "</" no puede aparecer dentro de <script>; el resto de JSON es texto válido ahí.
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def construir(datos, medios, plantilla, forzar_portada=None):
    """Devuelve (fragmento_html, rutas usadas, avisos)."""
    validar(datos)
    recorte, usados, avisos = recortar_medios(medios, datos, forzar_portada)
    if not ((datos.get("liguilla") or {}).get("torneo") or {}).get("rondas"):
        avisos.append("actual.json no trae liguilla.torneo: la sección «Liguilla» mostrará un aviso en lugar del cuadro.")
    portada = recorte["escenas"]["portada"]
    a = lambda x: html.escape(str(x or ""), quote=True)
    credito = portada.get("credito") or ""
    if credito and not re.match(r"(?i)foto", credito):
        credito = "Foto: " + credito
    dx = portada.get("dx_ancho") if re.fullmatch(r"-?\d+(\.\d+)?%", str(portada.get("dx_ancho") or "")) else ""
    fondo = (f'<img class="kb" src="{a(portada["archivo"])}" alt="{a(portada.get("alt"))}" width="{a(portada.get("ancho") or 1600)}" '
             f'height="{a(portada.get("alto") or 900)}" style="--pos:{a(portada["pos"])};--pos-ancho:{a(portada["pos_ancho"])};--zoom:{float(portada["zoom"]):.2f}'
             + (f';--dx-ancho:{dx}" data-dx ' if dx else '" ') + 'decoding="async" fetchpriority="high">')
    reemplazos = {
        "{{PORTADA_FONDO}}": fondo,
        "{{PORTADA_TONO}}": a(portada["tono"]),
        "{{PORTADA_LADO}}": a(portada["lado"]),
        "{{PORTADA_CREDITO}}": html.escape(" · ".join(x for x in (portada.get("pie"), credito) if x)),
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
            "<style>:root{padding:env(safe-area-inset-top,0px) 0 env(safe-area-inset-bottom,0px)}body{margin:0}"
            "img{max-width:100%}[hidden]{display:none!important}</style>\n"
            + cabeza + "\n</head>\n<body>" + cuerpo + "</body>\n</html>\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Construye web/index.html a partir de salidas/actual.json.")
    ap.add_argument("--datos", type=Path, default=DATOS, help="ruta de actual.json")
    ap.add_argument("--documento", action="store_true",
                    help="además genera un documento HTML completo (con <!doctype>, <head> y <body>)")
    ap.add_argument("--salida", type=Path, default=None,
                    help="directorio del sitio estático (por omisión web/sitio/). Si es la propia carpeta web/, "
                         "sólo escribe documento.html junto a img/ y video/, sin copiar nada")
    ap.add_argument("--vivo", type=Path, default=None,
                    help="incrusta este documento en vivo (misma forma que salidas/vivo_ejemplo.json) como datos.vivo; "
                         "sin la opción se incrusta actual.json → vivo si existe")
    ap.add_argument("--portada", default=None, metavar="EQUIPO",
                    help="sólo para revisar: fuerza el equipo de la portada en lugar del favorito al título")
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
        if args.vivo is not None:
            if not args.vivo.exists():
                raise ErrorDatos(f"No existe {args.vivo}.")
            try:
                datos["vivo"] = json.loads(args.vivo.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                raise ErrorDatos(f"JSON inválido en {args.vivo}: {e}")
        if args.portada and args.portada not in medios.get("escudos", {}):
            raise ErrorDatos(f"--portada: «{args.portada}» no es un equipo de medios.json.")
        fragmento, usados, avisos = construir(datos, medios, PLANTILLA.read_text(encoding="utf-8"), args.portada)
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

    publicados = sorted(set(usados))
    de_prueba = args.vivo is not None or bool(args.portada)
    if de_prueba:
        args.documento = True
        if args.salida is None:
            args.salida = AQUI
        print("opción de prueba (--vivo o --portada): no se toca index.html; sólo se escribe el documento")
    else:
        escribir(AQUI / "index.html", fragmento)
        escribir(AQUI / "archivos_publicados.json", json.dumps(publicados, ensure_ascii=False, indent=1) + "\n")
        escribir(AQUI / "capacidades.json", json.dumps(CAPACIDADES, ensure_ascii=False, indent=1) + "\n")
        peso = sum((AQUI / r).stat().st_size for r in publicados)
        print(f"index.html: {len(fragmento.encode('utf-8')) / 1024:.0f} KB · {len(publicados)} archivos de medios "
              f"({peso / 1e6:.1f} MB) en archivos_publicados.json · corte {datos['meta']['corte_local']}"
              + (" · con «vivo» incrustado" if datos.get("vivo") else ""))

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
