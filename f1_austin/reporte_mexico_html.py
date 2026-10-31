"""Reporte HTML 'Día de Muertos + carreras' para el pronóstico de qualy del GP de la Ciudad de México.

Uso:  from reporte_mexico_html import generar_html;  generar_html(R, ruta)
Todo el arte (papel picado, cempasúchil, velas, calavera con casco) es SVG/CSS inline; sólo las
tipografías vienen de Google Fonts. Página estática lista para Netlify.
"""
import base64
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from reporte_html import ETIQUETAS, e

BASE = Path(__file__).resolve().parent

C = {"noche": "#120a1f", "ink": "#f7efe3", "cempa": "#ff9f1c", "naranja": "#f76707", "rosa": "#e6007e",
     "rosa2": "#ff3d9a", "turq": "#19c3b3", "morado": "#7b2cbf", "amarillo": "#ffd23f", "verde": "#7ac943",
     "oscuro": "#1d0f33"}

NOMBRES_CIRCUITO = {"Spa-Francorchamps": "Spa", "Monte Carlo": "Mónaco", "Catalunya": "Barcelona",
                    "Hungaroring": "Hungría", "Mexico City": "México", "Shanghai": "Shanghái", "Baku": "Bakú",
                    "Singapore": "Singapur", "Madring": "Madrid", "Kuala Lumpur": "K. Lumpur",
                    "Sakhir": "Baréin", "Jeddah": "Yeda", "Las Vegas": "Las Vegas", "Lusail": "Catar",
                    "Yas Marina Circuit": "Abu Dabi", "Interlagos": "Brasil", "Imola": "Imola"}


# ----------------------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------------------
def nan(x):
    try:
        return x is None or pd.isna(x)
    except (TypeError, ValueError):
        return False


def pct(x):
    if nan(x):
        return "—"
    return f"{100 * x:.0f}%" if x >= 0.005 else "<1%"


def signo(x, d=2):
    if nan(x):
        return "—"
    return f"+{x:.{d}f}" if x >= 0 else f"−{abs(x):.{d}f}"


def fnum(x, d=1, suf=""):
    """Como reporte_html.fnum pero tolera pd.NA, None y float32 NaN."""
    return "—" if nan(x) else f"{float(x):.{d}f}{suf}"


def fint(x):
    return "—" if nan(x) else f"{int(x)}"


def color(row):
    """Color de escudería; acepta 'FF8000' o '#FF8000' y cae a gris si no es un hex válido."""
    c = row.get("team_colour")
    c = c.strip().lstrip("#") if isinstance(c, str) else ""
    return f"#{c}" if re.fullmatch(r"[0-9A-Fa-f]{6}", c) else "#888888"


# OpenF1 escribe los apellidos en MAYÚSCULAS y sin acentos
ACENTOS = {"Perez": "Pérez", "Hulkenberg": "Hülkenberg", "Raikkonen": "Räikkönen", "Gutierrez": "Gutiérrez"}


def nombre(r):
    fn = r.get("full_name")
    if not (isinstance(fn, str) and fn.strip()):
        return str(r.get("name_acronym", ""))
    # sólo se capitalizan las palabras en mayúsculas (respeta "de la", "van", etc.)
    pal = [w.title() if w.isupper() and len(w) > 1 else w for w in fn.split()]
    return " ".join(ACENTOS.get(w, w) for w in pal)


# ----------------------------------------------------------------------------------------
# Arte SVG
# ----------------------------------------------------------------------------------------
PETALO = "M0,0C-7,-5 -9.5,-18 -6.5,-24.5Q-3.5,-29 0,-25.5Q3.5,-29 6.5,-24.5C9.5,-18 7,-5 0,0Z"


def defs_globales():
    """Gradientes, pétalo y flor de cempasúchil reutilizables con <use>."""
    anillos = [(16, 1.72, 0, "#d9480f", "#9c3606"), (14, 1.38, 12.8, "#f76707", "#c2410c"),
               (12, 1.06, 4, "#ff922b", "#e8590c"), (10, .76, 18, "#ffa94d", "#f76707"),
               (8, .48, 0, "#ffc078", "#fd7e14")]
    pet = []
    for n, s, off, f, st in anillos:
        for k in range(n):
            pet.append(f'<use href="#pt" transform="rotate({off + k * 360 / n:.1f}) scale({s})" fill="{f}" '
                       f'stroke="{st}" stroke-width=".5"/>')
    return f"""<svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false"><defs>
<linearGradient id="gCera" x1="0" x2="1"><stop offset="0" stop-color="#d6c2a6"/><stop offset=".45" stop-color="#fff6e6"/><stop offset="1" stop-color="#c9b193"/></linearGradient>
<linearGradient id="gLlama" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff3bf"/><stop offset=".45" stop-color="#ffd43b"/><stop offset="1" stop-color="#f76707"/></linearGradient>
<radialGradient id="gHalo"><stop offset="0" stop-color="#ffb627" stop-opacity=".6"/><stop offset="1" stop-color="#ffb627" stop-opacity="0"/></radialGradient>
<path id="pt" d="{PETALO}"/>
<symbol id="flor" viewBox="-50 -50 100 100">{''.join(pet)}<circle r="5" fill="#e8590c"/><circle r="2.4" fill="#ffd43b"/></symbol>
</defs></svg>"""


def flor(cls="ic"):
    return f'<svg class="{cls}" viewBox="0 0 100 100" aria-hidden="true"><use href="#flor" width="100" height="100"/></svg>'


def vela(x, base, w, h):
    """Vela con halo y llama (coordenadas SVG). La llama parpadea con CSS (.llama)."""
    cx, top, s = x + w / 2, base - h, w / 24
    f = lambda v: f"{v:.1f}"
    return (f'<circle cx="{f(cx)}" cy="{f(top - 15 * s)}" r="{f(19 * s)}" fill="url(#gHalo)"/>'
            f'<rect x="{f(x)}" y="{f(top)}" width="{f(w)}" height="{f(h)}" rx="{f(3 * s)}" fill="url(#gCera)"/>'
            f'<path d="M{f(x + 3 * s)},{f(top + 1)} v{f(11 * s)} a{f(2.5 * s)},{f(2.5 * s)} 0 0 0 {f(5 * s)},0 v{f(-7 * s)}Z" fill="#fffaf0"/>'
            f'<ellipse cx="{f(cx)}" cy="{f(top + 1)}" rx="{f(w / 2)}" ry="{f(2.5 * s)}" fill="#fffaf0"/>'
            f'<path d="M{f(cx)},{f(top)} v{f(-6 * s)}" stroke="#3a2a1e" stroke-width="{f(1.4 * s)}" stroke-linecap="round"/>'
            f'<g class="llama"><path d="M{f(cx)},{f(top - 27 * s)} C{f(cx + 7.5 * s)},{f(top - 17 * s)} {f(cx + 6.5 * s)},{f(top - 6 * s)} '
            f'{f(cx)},{f(top - 4.5 * s)} C{f(cx - 6.5 * s)},{f(top - 6 * s)} {f(cx - 7.5 * s)},{f(top - 17 * s)} {f(cx)},{f(top - 27 * s)}Z" fill="url(#gLlama)"/>'
            f'<path d="M{f(cx)},{f(top - 16 * s)} C{f(cx + 3 * s)},{f(top - 11 * s)} {f(cx + 3 * s)},{f(top - 7 * s)} {f(cx)},{f(top - 6 * s)} '
            f'C{f(cx - 3 * s)},{f(top - 7 * s)} {f(cx - 3 * s)},{f(top - 11 * s)} {f(cx)},{f(top - 16 * s)}Z" fill="#fff9db"/></g>')


def vela_svg(p):
    """Vela para la sección 'en la burbuja': la altura de la cera es proporcional a P(Q3)."""
    frac = min(max((p - .25) / .5, 0), 1) if not nan(p) else 0
    h = 28 + 62 * frac
    return f'<svg class="vela" viewBox="0 0 40 120" aria-hidden="true">{vela(9, 117, 22, h)}</svg>'


def casco_svg():
    """Calavera de azúcar con casco de piloto, rodeada de cempasúchil y velas."""
    shell = ("M56,200 C46,108 86,30 160,28 C234,30 274,108 264,200 C260,240 230,268 192,274 "
             "L128,274 C90,268 60,240 56,200Z")
    ojos = []
    for ex in (124, 196):
        pet = "".join(f'<use href="#pt" transform="rotate({k * 30 + 15}) scale(.86)" '
                      f'fill="{C["cempa"] if k % 2 else C["rosa"]}" stroke="#120a1f" stroke-width=".6"/>'
                      for k in range(12))
        ojos.append(f'<g transform="translate({ex},146)">{pet}<circle r="12.5" fill="#0b0614"/>'
                    f'<circle cx="-4" cy="-4" r="2.6" fill="#fff" opacity=".85"/></g>')
    puntadas = []
    for x in range(118, 204, 12):
        t = (x - 112) / 96
        y = 226 + 40 * t * (1 - t)
        puntadas.append(f'<path d="M{x},{y - 7:.1f} v14" />')
    mejillas = []
    for mx in (98, 222):
        circ = "".join(f'<circle cx="{mx + 5.6 * math.cos(a):.1f}" cy="{204 + 5.6 * math.sin(a):.1f}" r="4.3"/>'
                       for a in [k * math.pi / 3 for k in range(6)])
        mejillas.append(f'<g fill="{C["rosa"]}">{circ}</g><circle cx="{mx}" cy="204" r="3.2" fill="{C["cempa"]}"/>')
    hojas = "".join(f'<ellipse cx="{x}" cy="{y}" rx="19" ry="6.5" transform="rotate({a} {x} {y})" fill="#2b6a48"/>'
                    for x, y, a in [(26, 246, -35), (294, 246, 35), (112, 304, -12), (208, 304, 12), (60, 300, 20), (260, 300, -20)])
    flores = "".join(f'<use href="#flor" x="{x - s / 2}" y="{y - s / 2}" width="{s}" height="{s}"/>'
                     for x, y, s in [(52, 262, 58), (268, 262, 58), (98, 284, 54), (222, 284, 54), (142, 296, 48),
                                     (178, 296, 48), (74, 302, 36), (246, 302, 36), (160, 308, 40)])
    return f"""<svg class="casco" viewBox="0 0 320 330" role="img" aria-label="Calavera de azúcar con casco de piloto, rodeada de cempasúchil y velas">
<defs>
<radialGradient id="gHaloH" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#ff9f1c" stop-opacity=".42"/><stop offset=".55" stop-color="#e6007e" stop-opacity=".12"/><stop offset="1" stop-color="#7b2cbf" stop-opacity="0"/></radialGradient>
<linearGradient id="gHueso" x1="0" x2="1"><stop offset="0" stop-color="#cdb8a0"/><stop offset=".3" stop-color="#fff8ee"/><stop offset=".7" stop-color="#fff8ee"/><stop offset="1" stop-color="#c4ad93"/></linearGradient>
<linearGradient id="gVisor" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#40216b"/><stop offset="1" stop-color="#0d0618"/></linearGradient>
<clipPath id="cCasco"><path d="{shell}"/></clipPath>
<pattern id="pCuadros" width="12" height="12" patternUnits="userSpaceOnUse"><rect width="12" height="12" fill="#f7efe3"/><rect width="6" height="6" fill="#120a1f"/><rect x="6" y="6" width="6" height="6" fill="#120a1f"/></pattern>
</defs>
<circle cx="160" cy="168" r="160" fill="url(#gHaloH)"/>
<g>{vela(12, 300, 26, 96)}{vela(282, 300, 26, 96)}</g>
<g clip-path="url(#cCasco)">
  <path d="{shell}" fill="url(#gHueso)"/>
  <path d="M30,20 H290 V84 Q160,52 30,84Z" fill="{C['oscuro']}"/>
  <rect x="148" y="20" width="24" height="47" fill="url(#pCuadros)"/>
  <path d="M30,90 Q160,58 290,90" stroke="{C['rosa']}" stroke-width="5" fill="none"/>
  <path d="M30,98 Q160,66 290,98" stroke="{C['turq']}" stroke-width="3" fill="none"/>
  <ellipse cx="114" cy="56" rx="34" ry="9" transform="rotate(-30 114 56)" fill="#fff" opacity=".16"/>
  <path d="M30,262 H290 V300 H30Z" fill="{C['oscuro']}"/>
  <path d="M30,261 H290" stroke="{C['cempa']}" stroke-width="3"/>
</g>
<path d="{shell}" fill="none" stroke="#0d0618" stroke-width="3"/>
<use href="#flor" x="144" y="79" width="32" height="32"/>
<g fill="none" stroke="{C['turq']}" stroke-width="2.6" stroke-linecap="round">
  <path d="M141,97 c-8,-12 -28,-9 -27,3 c1,8 12,8 13,1"/><path d="M179,97 c8,-12 28,-9 27,3 c-1,8 -12,8 -13,1"/>
</g>
<g fill="{C['rosa']}"><circle cx="104" cy="106" r="2.4"/><circle cx="96" cy="111" r="2"/><circle cx="216" cy="106" r="2.4"/><circle cx="224" cy="111" r="2"/></g>
<path d="M76,122 Q160,103 244,122 L248,166 Q160,183 72,166Z" fill="url(#gVisor)" stroke="#0d0618" stroke-width="2.5"/>
{''.join(ojos)}
<path d="M92,127 Q160,111 228,127 L227,133 Q160,118 93,133Z" fill="#fff" opacity=".2"/>
<g fill="{C['oscuro']}" stroke="{C['turq']}" stroke-width="2"><circle cx="73" cy="144" r="7"/><circle cx="247" cy="144" r="7"/></g>
<path d="M160,180 C150,190 146,198 152,202 C156,205 160,201 160,198 C160,201 164,205 168,202 C174,198 170,190 160,180Z" fill="{C['oscuro']}"/>
{''.join(mejillas)}
<path d="M112,226 Q160,246 208,226" stroke="{C['oscuro']}" stroke-width="3" fill="none" stroke-linecap="round"/>
<g stroke="{C['oscuro']}" stroke-width="2.4" stroke-linecap="round">{''.join(puntadas)}</g>
<g fill="{C['turq']}"><circle cx="160" cy="214" r="2"/><circle cx="104" cy="226" r="1.8"/><circle cx="216" cy="226" r="1.8"/></g>
{hojas}{flores}
</svg>"""


def papel_uri(colores=None, fw=64, h=84):
    """Tira de papel picado (SVG en data URI, repetible en x). Calado con bandera a cuadros al centro."""
    colores = colores or [C["rosa"], C["cempa"], C["turq"], C["morado"], C["amarillo"], C["verde"]]
    W = fw * len(colores)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}">',
           f'<path d="M0,3.5 H{W}" stroke="#f7efe3" stroke-opacity=".55" stroke-width="1.4"/>']
    for i, col in enumerate(colores):
        x0, x1, top, bot = i * fw + 5, i * fw + fw - 5, 4, h - 13
        n_esc = 5
        step = (x1 - x0) / n_esc
        d = [f"M{x0},{top} H{x1} V{bot}"]
        for j in range(n_esc):
            d.append(f"A{step / 2:.2f},{step / 2:.2f} 0 0 1 {x1 - (j + 1) * step:.2f},{bot}")
        d.append("Z")
        # fila de perforaciones arriba
        xx = x0 + 6
        while xx <= x1 - 5:
            d.append(f"M{xx - 1.5:.1f},{top + 7} a1.5,1.5 0 1 0 3,0 a1.5,1.5 0 1 0 -3,0Z")
            xx += 6.8
        # bandera a cuadros calada
        s, cols, rows = 5, 6, 5
        gx, gy = (x0 + x1) / 2 - cols * s / 2, top + 15
        for r_ in range(rows):
            for c_ in range(cols):
                if (r_ + c_) % 2 == 0:
                    d.append(f"M{gx + c_ * s:.1f},{gy + r_ * s:.1f} h{s} v{s} h-{s}Z")
        # rombos abajo
        ry = bot - 8
        xx = x0 + 8
        while xx <= x1 - 7:
            d.append(f"M{xx:.1f},{ry - 3} l3,3 l-3,3 l-3,-3Z")
            xx += 9
        rot = 1.6 if i % 2 else -1.6
        out.append(f'<path transform="rotate({rot} {(x0 + x1) / 2} {top})" fill="{col}" fill-rule="evenodd" '
                   f'd="{" ".join(d)}"/>')
    out.append("</svg>")
    return "data:image/svg+xml;base64," + base64.b64encode("".join(out).encode()).decode()


def guirnalda_uri():
    """Guirnalda de cempasúchil (SVG autocontenido en data URI, repetible en x) para la base del altar."""
    anillos = [(16, 1.72, 0, "#d9480f"), (14, 1.38, 12.8, "#f76707"), (12, 1.06, 4, "#ff922b"),
               (10, .76, 18, "#ffa94d"), (8, .48, 0, "#ffc078")]

    def fl(cx, cy, k):
        pet = "".join(f'<use xlink:href="#p" transform="rotate({off + j * 360 / n:.1f}) scale({sc})" fill="{f}"/>'
                      for n, sc, off, f in anillos for j in range(n))
        return f'<g transform="translate({cx} {cy}) scale({k})">{pet}<circle r="5" fill="#e8590c"/></g>'

    hojas = "".join(f'<ellipse cx="{x}" cy="{y}" rx="15" ry="5" transform="rotate({a} {x} {y})" fill="#2b6a48"/>'
                    for x, y, a in [(62, 36, -25), (70, 40, 20), (134, 38, -18), (142, 41, 24)])
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="150" height="46" '
           f'viewBox="0 0 150 46"><defs><path id="p" d="{PETALO}"/></defs>{hojas}'
           f'{fl(30, 28, .42)}{fl(100, 31, .36)}</svg>')
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


FAVICON = ("data:image/svg+xml;base64," + base64.b64encode(
    ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><g transform="translate(32 32)">'
     + "".join(f'<ellipse cx="0" cy="-17" rx="8" ry="13" transform="rotate({k * 30})" fill="{"#f76707" if k % 2 else "#ff9f1c"}"/>'
               for k in range(12))
     + '<circle r="11" fill="#ffb627"/><circle r="5" fill="#e8590c"/></g></svg>').encode()).decode())


ICONOS = {
    "montana": '<path d="M2 20 L9 8 L13 14 L16 10 L22 20Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>'
               '<path d="M7.4 10.8 L9 8 L10.6 10.6" fill="none" stroke="currentColor" stroke-width="1.8"/>',
    "novato": '<rect x="3" y="3" width="18" height="18" rx="3" fill="none" stroke="currentColor" stroke-width="1.8"/>'
              '<path d="M8 16 V8 L16 16 V8" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>',
    "rayo": '<path d="M13 2 L5 13 H11 L10 22 L19 10 H13Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>',
    "bandera": '<path d="M5 21 V3" stroke="currentColor" stroke-width="1.8"/><path d="M5 4 H19 V14 H5" fill="none" stroke="currentColor" stroke-width="1.8"/>'
               '<path d="M5 4h4.7v3.3H5zM14.3 4H19v3.3h-4.7zM9.7 7.3h4.6v3.4H9.7zM5 10.7h4.7V14H5zM14.3 10.7H19V14h-4.7z" fill="currentColor"/>',
}


def icono(k):
    return f'<svg class="oi" viewBox="0 0 24 24" aria-hidden="true">{ICONOS[k]}</svg>'


# ----------------------------------------------------------------------------------------
# Estilos
# ----------------------------------------------------------------------------------------
CSS = """:root{--noche:#120a1f;--card:#1d1030;--card2:#27163f;--ink:#f7efe3;--muted:#c3b4d6;--cempa:#ff9f1c;
--cempa2:#ffb627;--naranja:#f76707;--rosa:#e6007e;--rosa2:#ff3d9a;--turq:#19c3b3;--morado:#7b2cbf;--morado2:#3a1a5c;
--line:rgba(255,159,28,.22);--hit:#3ddc97;--miss:#ff5c7a}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--noche);color:var(--ink);font-family:"Titillium Web",system-ui,sans-serif;line-height:1.45;
background-image:radial-gradient(ellipse at 50% 0%,rgba(123,44,191,.28),transparent 60%),
radial-gradient(circle at 0% 55%,rgba(230,0,126,.07),transparent 30%),radial-gradient(circle at 100% 80%,rgba(255,159,28,.06),transparent 30%)}
.wrap{max-width:1100px;margin:0 auto;padding:0 16px}
h1,h2,h3{font-family:"Bungee",system-ui,sans-serif;font-weight:400}
.deco{font-family:"Sancreek",serif;font-weight:400}
.picado{height:84px;background:url(__PAPEL__) repeat-x 0 0/auto 84px;filter:drop-shadow(0 4px 3px rgba(0,0,0,.35))}
.picado.mini{height:46px;background-size:auto 46px;opacity:.95}
.hero{position:relative;overflow:hidden;background:radial-gradient(ellipse at 78% 62%,rgba(255,159,28,.16),transparent 42%),
linear-gradient(180deg,#1c0b31 0%,#130a22 100%)}
.hero .wrap{display:grid;grid-template-columns:1.15fr .85fr;gap:16px;align-items:center;padding-top:6px;padding-bottom:22px}
.kicker{color:var(--cempa);text-transform:uppercase;letter-spacing:3px;font-weight:700;font-size:13px}
.hdeco{font-family:"Sancreek",serif;color:var(--rosa2);font-size:clamp(22px,3vw,32px);margin-top:14px;line-height:1.1}
h1{font-size:clamp(38px,6.2vw,70px);line-height:.98;margin:6px 0 14px;letter-spacing:1px;text-shadow:0 4px 0 rgba(0,0,0,.35)}
h1 em{font-style:normal;color:var(--cempa)}
.hsub{font-size:18px;line-height:1.5}
.hsub b{color:var(--cempa2);white-space:nowrap}
.tags{display:flex;flex-wrap:wrap;gap:8px;margin-top:18px}
.tag{background:var(--rosa);padding:4px 12px;border-radius:3px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;font-size:12px}
.tag.alt{background:transparent;border:1.5px solid var(--turq);color:var(--turq);padding:2.5px 10.5px}
.casco{width:100%;max-width:370px;display:block;justify-self:center;filter:drop-shadow(0 10px 18px rgba(0,0,0,.45))}
.cuadros{height:14px;background:repeating-conic-gradient(var(--ink) 0 25%,#120a1f 0 50%) 0 0/14px 14px;border-top:3px solid var(--cempa)}
.llama{transform-box:fill-box;transform-origin:50% 100%;animation:llama 2.4s ease-in-out infinite alternate}
.vela:nth-child(2n) .llama{animation-duration:1.9s}
@keyframes llama{0%{transform:scale(1,1) rotate(-2deg)}50%{transform:scale(.93,1.07) rotate(1.5deg)}100%{transform:scale(1.04,.95) rotate(-1deg)}}
@media (prefers-reduced-motion:reduce){.llama{animation:none}}
section{margin:42px 0}
h2{font-size:clamp(20px,2.6vw,26px);margin:0 0 6px;display:flex;align-items:center;gap:10px;letter-spacing:.5px;line-height:1.15}
h2 .ic{width:32px;height:32px;flex:none}
.lead{color:var(--muted);margin:0 0 16px;max-width:780px}
.lead b{color:var(--ink)}
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.kpi{background:linear-gradient(180deg,var(--card2),var(--card));border:1px solid var(--line);border-radius:6px;padding:18px 14px 14px;position:relative;overflow:hidden}
.kpi::before{content:"";position:absolute;left:0;right:0;top:0;height:5px;background:var(--k,var(--cempa))}
.kpi:nth-child(4n+2){--k:var(--rosa)} .kpi:nth-child(4n+3){--k:var(--turq)} .kpi:nth-child(4n+4){--k:var(--morado)}
.kpi b{display:block;font-family:"Bungee",sans-serif;font-weight:400;font-size:clamp(22px,2.8vw,30px);line-height:1.1;margin-bottom:6px}
.kpi b small{font-size:.55em;color:var(--muted)}
.kpi span{color:var(--muted);font-size:13px;line-height:1.3;display:block}
.pista{position:relative;border:2px solid var(--morado2);border-radius:8px;overflow:hidden;
background:radial-gradient(rgba(255,255,255,.035) 1px,transparent 1.6px) 0 0/6px 6px,linear-gradient(180deg,#1b1624,#120f18)}
.pista .meta{height:18px;background:repeating-conic-gradient(#f7efe3 0 25%,#141019 0 50%) 0 0/18px 18px}
.pista .rotulo{position:absolute;right:12px;top:24px;font-family:"Sancreek",serif;color:rgba(247,239,227,.22);font-size:15px;letter-spacing:1px}
.parrilla{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:18px 30px;padding:34px 22px 26px;align-items:start}
.slot{position:relative;min-width:0;display:flex;align-items:center;gap:12px;background:linear-gradient(90deg,var(--card2),#170c27);
border-left:6px solid var(--tc);padding:12px 14px 14px 12px;border-radius:4px;box-shadow:0 3px 0 rgba(0,0,0,.45)}
.slot::before{content:"";position:absolute;left:-6px;right:0;top:-9px;height:9px;border:2px solid rgba(247,239,227,.7);border-bottom:0}
.slot.der{margin-top:40px}
.slot.p1{box-shadow:0 0 0 2px var(--cempa),0 0 26px rgba(255,159,28,.35)}
.pnum{font-family:"Bungee",sans-serif;font-size:26px;color:var(--cempa);min-width:50px;line-height:1}
.pinfo{flex:1;min-width:0}
.pname{font-weight:900;font-size:17px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pname .acr{display:none}
.pteam{color:var(--muted);font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pprob{text-align:right}
.pprob span{font-weight:900;font-size:20px;font-variant-numeric:tabular-nums}
.pprob small{display:block;color:var(--muted);font-size:10.5px;text-transform:uppercase;letter-spacing:1px}
.slot .mini{position:absolute;left:0;right:0;bottom:0;height:3px;background:rgba(255,255,255,.07)}
.slot .mini i{display:block;height:100%;background:linear-gradient(90deg,var(--cempa),var(--rosa))}
.slot .fl{width:22px;height:22px;position:absolute;right:-9px;top:-11px}
.velas{display:grid;grid-template-columns:repeat(var(--n,5),minmax(0,260px));gap:12px}
.velacard{background:linear-gradient(180deg,var(--card2),var(--card));border:1px solid var(--line);border-radius:6px;padding:12px 12px 12px 8px;
display:flex;gap:8px;align-items:flex-end;position:relative;overflow:hidden}
.velacard::after{content:"";position:absolute;left:0;right:0;bottom:0;height:3px;background:var(--tc)}
.velacard .vela{width:36px;height:108px;flex:none}
.velacard .acr{font-family:"Bungee",sans-serif;font-size:22px;line-height:1;display:block}
.velacard .eq{color:var(--muted);font-size:12px;display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.velacard .vp{font-weight:900;font-size:24px;color:var(--cempa2);line-height:1.1;display:block;margin-top:8px}
.velacard .vp small{font-size:11px;color:var(--muted);font-weight:700;letter-spacing:1px;margin-left:4px}
.velacard .rg{font-size:12px;color:var(--muted);display:block;white-space:nowrap;line-height:1.35}
.velacard>div{min-width:0}
.checo{margin-top:16px;display:grid;grid-template-columns:auto 1fr;gap:6px 18px;align-items:center;background:var(--card);
border:1px solid var(--line);border-radius:6px;padding:16px 18px;position:relative;overflow:hidden}
.checo::before{content:"";position:absolute;left:0;top:0;bottom:0;width:6px;background:linear-gradient(180deg,#006847 0 33.3%,#f7efe3 33.3% 66.6%,#ce1126 66.6%)}
.checo .deco{font-size:22px;color:var(--cempa2);grid-column:1/-1;line-height:1.1}
.checo .big{font-family:"Bungee",sans-serif;font-size:40px;line-height:1;color:var(--ink)}
.checo p{margin:0;color:var(--muted);font-size:14.5px}
.checo p b{color:var(--ink)}
.tw{overflow-x:auto;border:1px solid var(--line);border-radius:6px;-webkit-overflow-scrolling:touch}
table{width:100%;border-collapse:collapse;font-size:14px;background:var(--card)}
th{background:var(--morado2);color:var(--ink);text-align:left;padding:9px 8px;font-size:11.5px;text-transform:uppercase;letter-spacing:1px;
white-space:nowrap;border-bottom:2px solid var(--cempa);font-weight:700}
td{padding:7px 8px;border-top:1px solid rgba(255,255,255,.06);white-space:nowrap}
tr:nth-child(even) td{background:rgba(255,255,255,.018)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tr.in td:first-child{color:var(--cempa);font-weight:900}
tr.corte td{border-top:2px dashed var(--rosa2)}
.sub{display:block;color:var(--muted);font-size:11px}
td b + .sub{display:inline-block;margin-left:6px;max-width:170px;overflow:hidden;text-overflow:ellipsis;vertical-align:bottom}
table.real td b + .sub{max-width:min(130px,11vw)}
.chip{display:inline-block;width:4px;height:16px;margin-right:8px;vertical-align:-3px;border-radius:1px}
.prob{display:flex;align-items:center;gap:8px;min-width:150px}
.bar{flex:1;height:8px;background:rgba(255,255,255,.1);border-radius:4px;overflow:hidden}
.bar i{display:block;height:100%;background:linear-gradient(90deg,var(--cempa),var(--rosa))}
.prob span{min-width:34px;text-align:right;font-variant-numeric:tabular-nums}
.fijo{position:sticky;left:0;z-index:1;background-color:var(--card)}
th.fijo{background-color:var(--morado2);z-index:2}
tr:nth-child(even) td.fijo{background-color:#211434}
td.mname{white-space:normal;min-width:220px;line-height:1.3}
.desliza{display:none;font-size:12px;color:var(--muted);margin:-8px 0 8px;letter-spacing:.5px}
tr.win td{background:rgba(255,159,28,.15);font-weight:700}
tr.win td:first-child{box-shadow:inset 4px 0 0 var(--cempa)}
tr.win td.fijo{background:#3f262d}
tr.base td{color:var(--muted)}
.ganador{display:inline-flex;align-items:center;gap:6px}
.ganador .ic{width:18px;height:18px}
.two{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:22px}
.mitades{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px;margin-top:14px;align-items:start}
.card{background:linear-gradient(180deg,var(--card2),var(--card));border:1px solid var(--line);border-radius:6px;padding:18px}
.card h2{font-size:19px}
.card h2 .ic{width:26px;height:26px}
td.hit{color:var(--hit);font-weight:700} td.miss{color:var(--miss);font-weight:700}
.irow{display:grid;grid-template-columns:200px minmax(0,1fr) 50px;gap:10px;align-items:center;font-size:13.5px;margin:6px 0}
.irow span{overflow-wrap:anywhere;line-height:1.25}
.ibar{height:10px;background:rgba(255,255,255,.08);border-radius:5px;overflow:hidden}
.ibar i{display:block;height:100%;background:linear-gradient(90deg,var(--turq),#7ee3d8);border-radius:5px}
.irow b{text-align:right;font-variant-numeric:tabular-nums}
.vchart{position:relative;display:flex;gap:4px;align-items:flex-end;height:270px;padding-top:20px}
.vcol{flex:1;display:flex;flex-direction:column;align-items:center;height:100%;justify-content:flex-end;min-width:0}
.vbox{position:relative;width:100%;height:calc(100% - 66px);display:flex;align-items:flex-end}
.vbar{width:100%;background:linear-gradient(180deg,var(--cempa2),var(--naranja));border-radius:3px 3px 0 0;position:relative;min-height:4px}
.vbar span{position:absolute;top:-18px;left:-4px;right:-4px;text-align:center;font-size:11px;font-weight:700}
.vcol small{font-size:10px;color:var(--muted);writing-mode:vertical-rl;transform:rotate(180deg);margin-top:6px;height:60px;white-space:nowrap;overflow:hidden}
.vprom{position:absolute;left:0;right:0;border-top:2px dashed var(--rosa2);pointer-events:none}
.vleg{font-size:12px;color:var(--muted);margin-top:8px}.vleg i{display:inline-block;width:22px;border-top:2px dashed var(--rosa2);vertical-align:middle;margin-right:6px}
.altar{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:16px 14px;position:relative;z-index:1}
.retrato{position:relative;background:linear-gradient(180deg,#2c1846,#1d1030);border:2px solid var(--cempa);outline:1px solid rgba(255,159,28,.45);
outline-offset:3px;border-radius:3px;padding:14px 8px 11px;text-align:center;margin:4px}
.retrato .anio{font-family:"Bungee",sans-serif;font-size:22px;color:var(--cempa2);line-height:1}
.retrato .nom{font-weight:900;font-size:15px;margin-top:6px;line-height:1.2}
.retrato .eq{color:var(--muted);font-size:12px}
.retrato.vivo{border-color:var(--turq);outline-color:rgba(25,195,179,.45)}
.retrato.vivo .anio{color:var(--turq)}
.retrato .fl{width:22px;height:22px;position:absolute;left:50%;top:-13px;transform:translateX(-50%)}
section.card{padding:20px}
.ofrenda{position:relative;overflow:hidden;padding-bottom:0!important}
.guirnalda{height:46px;margin:14px -20px 0;background:url(__GUIRNALDA__) repeat-x 0 100%/auto 46px}
.tira{display:inline-flex;gap:3px}
.tira i{width:22px;height:20px;border-radius:3px;font-style:normal;font-size:10.5px;font-weight:900;display:inline-flex;align-items:center;justify-content:center;color:#120a1f}
.tira.cab i{background:none;color:var(--ink);font-size:10.5px;height:auto}
i.t1{background:var(--cempa)} i.t3{background:var(--rosa2)} i.t10{background:var(--turq)} i.tx{background:rgba(255,255,255,.22);color:var(--ink)!important}
i.t0{background:transparent;border:1px dashed rgba(255,255,255,.18)}
.leyenda{font-size:12px;color:var(--muted);margin-top:12px;display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center}
.leyenda span{display:inline-flex;align-items:center;gap:6px}
.leyenda i{display:inline-block;width:12px;height:12px;border-radius:2px}
.metodo{font-size:14.5px;line-height:1.65}
.metodo b{color:var(--cempa2)}
.ojo{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px}
.ojo .card{display:grid;grid-template-columns:auto minmax(0,1fr);gap:4px 14px;align-items:start}
.ojo .oi{width:36px;height:36px;color:var(--cempa);grid-row:span 2;margin-top:2px}
.ojo .card:nth-child(2) .oi{color:var(--turq)} .ojo .card:nth-child(3) .oi{color:var(--rosa2)} .ojo .card:nth-child(4) .oi{color:#c79bff}
.ojo h3{font-size:15px;margin:0;letter-spacing:.5px;line-height:1.3}
.ojo p{margin:0;font-size:14px;color:var(--muted);line-height:1.55}
.ojo p b{color:var(--ink)}
footer{margin-top:46px;background:linear-gradient(180deg,transparent,rgba(0,0,0,.35))}
footer .wrap{padding:18px 16px 40px;color:var(--muted);font-size:13px;display:flex;flex-wrap:wrap;gap:10px 24px;justify-content:space-between;align-items:center}
footer .deco{color:var(--cempa);font-size:20px}
@media(max-width:1000px){.velas{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:860px){.hero .wrap{grid-template-columns:1fr 250px}}
@media(max-width:760px){
.picado{height:64px;background-size:auto 64px}
.hero .wrap{grid-template-columns:1fr;gap:0}
.casco{max-width:230px;order:-1;margin-top:4px}
.kpis{grid-template-columns:minmax(0,1fr) minmax(0,1fr)} .two,.mitades{grid-template-columns:minmax(0,1fr)} .ojo{grid-template-columns:minmax(0,1fr)}
.irow{grid-template-columns:140px minmax(0,1fr) 46px} .altar{grid-template-columns:repeat(3,minmax(0,1fr))}
.desliza{display:block} .fijo{box-shadow:inset -1px 0 0 rgba(255,159,28,.25)}
.vcol small{font-size:9px}}
@media(max-width:600px){
.parrilla{gap:12px 12px;padding:30px 10px 18px}
.slot{gap:6px;padding:9px 8px 12px 7px;border-left-width:5px}
.slot.der{margin-top:34px}
.pnum{font-size:17px;min-width:30px}
.pname{font-size:16px} .pname .full{display:none} .pname .acr{display:inline}
.pteam{font-size:11px}
.pprob span{font-size:15px} .pprob small{font-size:9px}
.pista .rotulo{display:none}
.velas{grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:10px}
.velacard .acr{font-size:19px} .velacard .vp{font-size:20px}
.checo{grid-template-columns:minmax(0,1fr)} .reyes .sub{display:none} .altar{grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px 8px}
td b + .sub,table.real td b + .sub{max-width:92px} td.mname{min-width:150px;font-size:13px} table{font-size:13.5px} section.card{padding:16px} .guirnalda{margin:12px -16px 0}
.kpi{padding:16px 12px 12px}
h1{font-size:40px}
.hsub{font-size:16px}}
"""


# ----------------------------------------------------------------------------------------
# Secciones
# ----------------------------------------------------------------------------------------
def leer_real(ruta, mk):
    for d in (Path(ruta).parent / "cache", BASE / "cache"):
        f = d / f"qualy_real_{mk}.json"
        if f.exists():
            try:
                real = pd.DataFrame(json.loads(f.read_text()))
            except (ValueError, OSError):
                return None
            if real.empty or not {"driver_number", "position"} <= set(real.columns):
                return None
            real = real[["driver_number", "position"]].rename(columns={"position": "real"})
            real["real"] = pd.to_numeric(real.real, errors="coerce")
            real["driver_number"] = pd.to_numeric(real.driver_number, errors="coerce")
            return real.dropna(subset=["driver_number"]).drop_duplicates("driver_number")
    return None


def seccion_real(obj, ruta, mk):
    real = leer_real(ruta, mk)
    if real is None or real.real.notna().sum() == 0:
        return ""
    t = obj[["driver_number", "name_acronym", "team_name", "team_colour", "pred_rank"]].copy()
    t["driver_number"] = pd.to_numeric(t.driver_number, errors="coerce")
    t = t.merge(real, on="driver_number", how="left").sort_values(["real", "pred_rank"], na_position="last")
    top_real = set(t[t.real <= 10].driver_number)
    hits = len(top_real & set(t[t.pred_rank <= 10].driver_number))
    hits3 = len(set(t[t.real <= 3].driver_number) & set(t[t.pred_rank <= 3].driver_number))
    con = t.dropna(subset=["real"])
    mae = (con.real - con.pred_rank).abs().mean() if len(con) else np.nan
    pole = con.iloc[0] if len(con) else None
    pole_ok = pole is not None and pole.pred_rank == 1
    filas = []
    for _, r in t.iterrows():
        if nan(r.real):
            ok, delta = "", "—"
        else:
            ok = "hit" if (r.real <= 10) == (r.pred_rank <= 10) else "miss"
            dd = int(r.pred_rank - r.real)
            delta = "=" if dd == 0 else (f"+{dd}" if dd > 0 else f"−{abs(dd)}")
        cls = ("in " if not nan(r.real) and r.real <= 10 else "") + ("corte" if not nan(r.real) and r.real == 11 else "")
        filas.append(f"""<tr class="{cls}"><td class="num">{fint(r.real)}</td>
<td><span class="chip" style="background:{color(r)}"></span><b>{e(r.name_acronym)}</b><span class="sub">{e(r.team_name)}</span></td>
<td class="num {ok}">P{int(r.pred_rank)}</td><td class="num">{delta}</td></tr>""")
    mitad = math.ceil(len(filas) / 2)
    cab = '<tr><th class="num">Real</th><th>Piloto</th><th class="num">Pronóstico</th><th class="num">Δ</th></tr>'
    tablas = "".join(f'<div class="tw"><table class="real">{cab}{"".join(parte)}</table></div>'
                     for parte in (filas[:mitad], filas[mitad:]) if parte)
    return f"""
<section id="real">
  <h2>{flor()}Resultado real vs. pronóstico</h2>
  <p class="lead">Clasificación oficial de la qualy (OpenF1) contra el orden pronosticado. En <span style="color:var(--hit)">verde</span>
  los pilotos que el modelo ubicó del lado correcto del corte de Q3; en <span style="color:var(--miss)">rojo</span>, los que no.
  Δ = posición pronosticada menos la real.</p>
  <div class="kpis">
    <div class="kpi"><b>{e(pole.name_acronym) if pole is not None else '—'}</b><span>Pole real{' · el modelo la tenía en P1' if pole_ok else (f' · el modelo la tenía en P{int(pole.pred_rank)}' if pole is not None else '')}</span></div>
    <div class="kpi"><b>{hits}<small>/10</small></b><span>Aciertos en el Top 10 (pasan a Q3)</span></div>
    <div class="kpi"><b>{hits3}<small>/3</small></b><span>Aciertos en el Top 3</span></div>
    <div class="kpi"><b>{fnum(mae, 1)}</b><span>Error medio de posición</span></div>
  </div>
  <div class="mitades">{tablas}</div>
</section>"""


def seccion_checo(obj, circ):
    per = obj[obj.name_acronym == "PER"]
    if per.empty:
        return ""
    r = per.iloc[0]
    h = circ[circ.code == "PER"].dropna(subset=["pos"])
    if len(h):
        mejor = h.sort_values(["pos", "season"]).iloc[0]
        hist = (f"En el Hermanos Rodríguez ha calificado <b>{len(h)}</b> veces desde 2015: mejor resultado "
                f"<b>P{int(mejor.pos)}</b> ({int(mejor.season)}, {e(mejor.team)}), media <b>P{h.pos.mean():.1f}</b>.")
    else:
        hist = "No tiene qualys registradas en el Hermanos Rodríguez desde 2015."
    return f"""
  <div class="checo">
    <div class="deco">Checo, en casa</div>
    <div class="big">P{int(r.pred_rank)}</div>
    <p>Pronóstico para <b>{e(nombre(r))}</b> ({e(r.team_name)}): P(Q3) <b>{pct(r.p_q3)}</b>, rango
    <b>P{fint(r.pos_p10)}–P{fint(r.pos_p90)}</b>. {hist} La porra del Foro Sol no entra en el modelo.</p>
  </div>"""


# ----------------------------------------------------------------------------------------
# Generador
# ----------------------------------------------------------------------------------------
def generar_html(R, ruta):
    ruta = Path(ruta)
    obj = R["obj"].copy().sort_values("pred_rank").reset_index(drop=True)
    tabla, imp, por_gp, mejor = R["tabla"], R["imp"], R["por_gp"], R["mejor"]
    gp = {"nombre": "Gran Premio de la Ciudad de México", "circuito": "Autódromo Hermanos Rodríguez",
          "ciudad": "Ciudad de México", "fecha_texto": "Sábado 31 de octubre de 2026",
          "hora_texto": "3:00 PM hora CDMX", "meeting_key": 1298, "slug": "mexico-2026"}
    gp.update(R.get("gp") or {})
    for col in ["fp1_rank", "fp1_gap", "fp2_rank", "fp2_gap", "fp2_long_rank", "h_q_mean5", "p_top3", "p_q2",
                "pos_p10", "pos_p90", "pos_media", "full_name", "team_colour"]:
        if col not in obj:
            obj[col] = np.nan

    fila_mejor = tabla[tabla.modelo == mejor].iloc[0] if (tabla.modelo == mejor).any() else tabla.iloc[0]
    bases = tabla[tabla.modelo.str.startswith("Baseline")]
    base = bases.top10_hits.max() if len(bases) else np.nan

    circ = R["circ"].copy()
    circ["season"] = pd.to_numeric(circ.season, errors="coerce")
    circ["pos"] = pd.to_numeric(circ.pos, errors="coerce")
    circ = circ[circ.season >= 2015].copy()
    circ["season"] = circ.season.astype(int)
    circ_med = circ.dropna(subset=["pos"]).groupby("code").pos.agg(["mean", "min", "count"])
    obj["mx_mean"] = obj.name_acronym.map(circ_med["mean"])
    obj["mx_n"] = obj.name_acronym.map(circ_med["count"]).fillna(0)

    # ---------------- Parrilla Top 10 ----------------
    grid = []
    for _, r in obj.head(10).iterrows():
        pr = int(r.pred_rank)
        lado = "izq" if pr % 2 else "der"
        p1 = " p1" if pr == 1 else ""
        fl = flor("fl") if pr == 1 else ""
        q3 = 0 if nan(r.p_q3) else r.p_q3
        grid.append(f"""
      <div class="slot {lado}{p1}" style="--tc:{color(r)}">{fl}
        <div class="pnum">P{pr}</div>
        <div class="pinfo">
          <div class="pname"><span class="full">{e(nombre(r))}</span><span class="acr">{e(r.name_acronym)}</span></div>
          <div class="pteam">{e(r.team_name)}</div>
        </div>
        <div class="pprob"><span>{pct(r.p_q3)}</span><small>Q3</small></div>
        <div class="mini"><i style="width:{100 * q3:.0f}%"></i></div>
      </div>""")

    # ---------------- En la burbuja ----------------
    burbuja = obj[(obj.p_q3 >= 0.25) & (obj.p_q3 <= 0.75)]
    if len(burbuja):
        velas = "".join(f"""
      <div class="velacard" style="--tc:{color(r)}">{vela_svg(r.p_q3)}
        <div><span class="acr">{e(r.name_acronym)}</span><span class="eq">{e(r.team_name)}</span>
        <span class="vp">{pct(r.p_q3)}<small>Q3</small></span>
        <span class="rg">Pronóstico P{int(r.pred_rank)}</span><span class="rg">Rango P{fint(r.pos_p10)}–P{fint(r.pos_p90)}</span></div>
      </div>""" for _, r in burbuja.iterrows())
        n_v = len(burbuja)
        n_col = n_v if n_v <= 6 else min(6, math.ceil(n_v / 2))
        velas = f'<div class="velas" style="--n:{n_col}">{velas}</div>'
    else:
        velas = '<p class="lead"><b>Nadie en la burbuja:</b> el corte entre Q2 y Q3 se ve claro esta vez.</p>'

    # ---------------- Tabla completa ----------------
    filas = []
    for _, r in obj.iterrows():
        pr = int(r.pred_rank)
        q3 = 0 if nan(r.p_q3) else r.p_q3
        fp1, fp2 = (f'{fint(rk)}<span class="sub">{"" if nan(gap) else f"+{gap:.2f}%"}</span>' if not nan(rk)
                    else '—<span class="sub">no rodó</span>'
                    for rk, gap in ((r.fp1_rank, r.fp1_gap), (r.fp2_rank, r.fp2_gap)))
        mx = (f'{fnum(r.mx_mean, 1)}<span class="sub">{int(r.mx_n)} vis.</span>' if r.mx_n > 0
              else '—<span class="sub">debut</span>')
        cls = ("in" if pr <= 10 else "") + (" corte" if pr == 11 else "")
        filas.append(f"""<tr class="{cls}">
<td class="num">{pr}</td>
<td class="fijo"><span class="chip" style="background:{color(r)}"></span><b>{e(r.name_acronym)}</b><span class="sub" title="{e(r.team_name)}">{e(r.team_name)}</span></td>
<td class="num">{fp1}</td><td class="num">{fp2}</td><td class="num">{fint(r.fp2_long_rank)}</td>
<td class="num">{fnum(r.h_q_mean5, 1)}</td><td class="num">{mx}</td>
<td class="num">{fint(r.pos_p10)}–{fint(r.pos_p90)}</td>
<td><div class="prob"><div class="bar"><i style="width:{100 * q3:.0f}%"></i></div><span>{pct(r.p_q3)}</span></div></td>
<td class="num">{pct(r.p_top3)}</td><td class="num">{pct(r.p_pole)}</td>
</tr>""")

    # ---------------- Comparación de modelos ----------------
    mod = []
    for _, r in tabla.iterrows():
        cls = "win" if r.modelo == mejor else ("base" if str(r.modelo).startswith("Baseline") else "")
        nom = (f'<span class="ganador">{flor()}{e(r.modelo)}</span>' if cls == "win" else e(r.modelo))
        mod.append(f"""<tr class="{cls}"><td class="mname fijo">{nom}</td>
<td class="num">{fnum(r.top10_hits, 2)}</td><td class="num">{fnum(r.get('top10_hits_2026'), 2)}</td>
<td class="num">{fnum(r.spearman, 3)}</td><td class="num">{fnum(r.mae, 2)}</td>
<td class="num">{'—' if nan(r.pole_acc) else f'{100 * r.pole_acc:.0f}%'}</td><td class="num">{fnum(r.top3_hits, 2)}</td>
<td class="num">{fint(r.get('n_gp'))}</td></tr>""")

    # ---------------- Importancia de variables ----------------
    imp_top = imp.sort_values(ascending=False).head(15)
    mx_imp = imp_top.max() if len(imp_top) and imp_top.max() > 0 else 1
    imps = "".join(
        f'<div class="irow"><span>{e(ETIQUETAS.get(k, str(k).replace("_", " ")))}</span>'
        f'<div class="ibar"><i style="width:{100 * v / mx_imp:.0f}%"></i></div><b>{100 * v:.1f}%</b></div>'
        for k, v in imp_top.items())

    # ---------------- Validación 2026 ----------------
    g26 = por_gp[pd.to_numeric(por_gp.year, errors="coerce") >= 2026].dropna(subset=["top10_hits"])
    if "date" in R["train"]:   # meeting_key no siempre es cronológico (p. ej. un GP agregado tarde al calendario)
        orden_gp = pd.to_datetime(R["train"].groupby("meeting_key").date.min(), errors="coerce", utc=True)
        g26 = g26.assign(_f=g26.meeting_key.map(orden_gp)).sort_values("_f", kind="stable", na_position="last")
    if len(g26):
        prom = g26.top10_hits.mean()
        cols = "".join(
            f'<div class="vcol" title="{e(r.circuit)} {int(r.year)}: {int(r.top10_hits)}/10 en el Top 10">'
            f'<div class="vbox"><div class="vbar" style="height:{r.top10_hits * 10:.0f}%"><span>{int(r.top10_hits)}</span></div></div>'
            f'<small>{e(NOMBRES_CIRCUITO.get(r.circuit, r.circuit))}</small></div>'
            for _, r in g26.iterrows())
        val = (f'<div class="vchart">{cols}<div class="vprom" style="bottom:calc(66px + (100% - 86px) * {prom / 10:.3f})">'
               f'</div></div><div class="vleg"><i></i>Promedio 2026: {prom:.1f} de 10</div>')
        val_lead = (f"Aciertos del Top 10 en cada GP de esta temporada, prediciendo sin ver el resultado "
                    f"({len(g26)} GPs, promedio <b>{prom:.1f}/10</b>).")
    else:
        val, val_lead = "", "Todavía no hay GPs de 2026 validados."

    # ---------------- Historial del circuito ----------------
    poles = circ[circ.pos == 1].sort_values("season", ascending=False)
    actuales = set(obj.name_acronym)
    altar = "".join(
        f'<div class="retrato{" vivo" if r.code in actuales else ""}">{flor("fl")}<div class="anio">{int(r.season)}</div>'
        f'<div class="nom">{e(r["name"])}</div><div class="eq">{e(r.team)}</div></div>'
        for _, r in poles.iterrows())
    temporadas = sorted(circ.season.unique())
    faltan = [y for y in range(2015, int(max(temporadas)) + 1) if y not in temporadas] if temporadas else []
    nota_faltan = f" (en {', '.join(map(str, faltan))} no hubo GP)" if faltan else ""
    reyes = (circ[circ.code.isin(actuales)].dropna(subset=["pos"]).groupby("code").pos
             .agg(n="count", q3=lambda s: int((s <= 10).sum()), poles=lambda s: int((s == 1).sum()),
                  mejor="min", media="mean")
             .sort_values(["media", "mejor"]).head(10))
    col_by = obj.drop_duplicates("name_acronym").set_index("name_acronym")
    pos_por = circ.dropna(subset=["pos"]).set_index(["code", "season"]).pos
    pos_por = pos_por[~pos_por.index.duplicated()]

    def tira(code):
        celdas = []
        for y in temporadas:
            p_ = pos_por.get((code, y), np.nan)
            if nan(p_):
                celdas.append(f'<i class="t0" title="{y}: no corrió"></i>')
            else:
                k = "t1" if p_ == 1 else ("t3" if p_ <= 3 else ("t10" if p_ <= 10 else "tx"))
                celdas.append(f'<i class="{k}" title="{y}: P{int(p_)}">{int(p_)}</i>')
        return f'<span class="tira">{"".join(celdas)}</span>'

    rey = "".join(
        f"<tr><td><span class='chip' style='background:{color(col_by.loc[k]) if k in col_by.index else '#888'}'></span><b>{e(k)}</b>"
        f"<span class='sub'>{e(col_by.loc[k].team_name) if k in col_by.index else ''}</span></td>"
        f"<td class='num'>{int(r.n)}</td><td class='num'>{int(r.q3)}</td><td class='num'>{int(r.poles)}</td>"
        f"<td class='num'>P{int(r.mejor)}</td><td class='num'>{r.media:.1f}</td><td>{tira(k)}</td></tr>"
        for k, r in reyes.iterrows())
    if not altar:
        altar = '<p class="lead" style="grid-column:1/-1">Sin poles registradas en este circuito desde 2015.</p>'
    if not rey:
        rey = '<tr><td colspan="7">Ningún piloto de la parrilla actual tiene qualys registradas aquí desde 2015.</td></tr>'
    if not imps:
        imps = f'<p class="lead">El modelo elegido ({e(mejor)}) no reporta importancia de variables.</p>'
    imp_lead = ("Importancia de variables (promedio de los modelos de árbol del ensamble)." if str(mejor).startswith("Ensamble")
                else f"Importancia de variables del modelo elegido ({e(mejor)}).")
    anios_tira = (f'<span class="tira cab">{"".join(f"<i>{str(y)[2:]}</i>" for y in temporadas)}</span>'
                  if temporadas else "")

    # ---------------- KPIs y textos ----------------
    favorito = obj.sort_values("p_pole", ascending=False).iloc[0]
    n_train = len(R["train"])
    n_gp = R["train"].meeting_key.nunique()
    n_vars = R.get("n_vars", len(ETIQUETAS))
    sin_fp1 = obj[obj.fp1_rank.isna()]
    if len(sin_fp1):
        lista = ", ".join(f"<b>{e(a)}</b>" for a in sin_fp1.name_acronym)
        n1 = len(sin_fp1)
        txt_fp1 = ((f"En esta FP1 <b>{n1}</b> titulares no rodaron" if n1 > 1 else "En esta FP1 <b>1</b> titular no rodó")
                   + f" (normalmente porque cedieron el coche a un novato): {lista}. Para "
                   + ("ellos" if n1 > 1 else "él") + " el modelo sólo ve FP2 y el historial, así que el pronóstico es más incierto.")
    else:
        txt_fp1 = ("En México los equipos suelen ceder coches a novatos en la FP1; cuando un titular no rueda, "
                   "el modelo sólo ve su FP2 y su historial.")
    real_html = seccion_real(obj, ruta, gp["meeting_key"])
    ahora = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    papel = papel_uri()
    css = CSS.replace("__PAPEL__", papel).replace("__GUIRNALDA__", guirnalda_uri())
    mejora = fila_mejor.top10_hits - base if not nan(base) else np.nan
    anios = pd.to_numeric(por_gp.year, errors="coerce").dropna()
    periodo = (f"{int(anios.min())}–{int(anios.max())}" if len(anios) and anios.min() != anios.max()
               else (f"{int(anios.min())}" if len(anios) else "2024–2026"))
    titulo = f"Qualy {gp['ciudad'].replace('Ciudad de México', 'México')} 2026 · Pronóstico"

    doc = f"""<!doctype html>
<html lang="es-MX"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(titulo)}</title>
<meta name="description" content="Pronóstico del Top 10 de la qualy del {e(gp['nombre'])} 2026 con un modelo de machine learning: FP1, FP2 e historial.">
<meta name="theme-color" content="#120a1f">
<meta property="og:title" content="{e(titulo)}">
<meta property="og:description" content="¿Quién saca la pole en el {e(gp['circuito'])}? Top 10, probabilidades de Q3 y pole.">
<link rel="icon" href="{FAVICON}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bungee&family=Sancreek&family=Titillium+Web:wght@400;600;700;900&display=swap" rel="stylesheet">
<style>
{css}</style></head><body>
{defs_globales()}
<header class="hero">
  <div class="picado" aria-hidden="true"></div>
  <div class="wrap">
    <div class="htext">
      <div class="kicker">{e(gp['circuito'])} · {e(gp['ciudad'])}</div>
      <div class="hdeco">Edición Día de Muertos</div>
      <h1>Pronóstico<br>de <em>Qualy</em></h1>
      <div class="hsub">{e(gp['nombre'])} 2026<br>{e(gp['fecha_texto'])} · <b>{e(gp['hora_texto'])}</b></div>
      <div class="tags"><span class="tag">Top 10 · FP1 + FP2 + historial</span><span class="tag alt">2,240 m de altitud</span></div>
    </div>
    {casco_svg()}
  </div>
  <div class="cuadros"></div>
</header>

<main>
<div class="wrap">
<section>
  <div class="kpis">
    <div class="kpi"><b>{e(favorito.name_acronym)} <small>{pct(favorito.p_pole)}</small></b><span>Favorito a la pole · {e(nombre(favorito))}</span></div>
    <div class="kpi"><b>{fnum(fila_mejor.top10_hits, 1)}<small>/10</small></b><span>Aciertos promedio en el Top 10 (validación {periodo})</span></div>
    <div class="kpi"><b>{signo(mejora)}</b><span>Aciertos de Top 10 vs. el mejor baseline de prácticas</span></div>
    <div class="kpi"><b>{n_gp}</b><span>Grandes Premios de entrenamiento · {n_train:,} filas piloto-GP · {n_vars} variables</span></div>
  </div>
</section>
{real_html}
<section id="parrilla">
  <h2>{flor()}La parrilla según el modelo</h2>
  <p class="lead">Top 10 pronosticado: los que pasan a Q3, acomodados como en la parrilla real. El porcentaje es la probabilidad de
  meterse a Q3 en 20,000 simulaciones Monte Carlo.</p>
  <div class="pista">
    <div class="meta"></div><div class="rotulo">↑ recta principal</div>
    <div class="parrilla">{''.join(grid)}
    </div>
  </div>
</section>

<section id="burbuja">
  <h2>{flor()}En la burbuja</h2>
  <p class="lead">Pilotos con entre 25% y 75% de probabilidad de pasar a Q3. La altura de la vela es su probabilidad:
  a cualquiera se le puede apagar en Q2.</p>
  {velas}
  {seccion_checo(obj, circ)}
</section>

<section id="tabla">
  <h2>{flor()}Todos los pilotos</h2>
  <p class="lead">Rango = posiciones entre los percentiles 10 y 90 de la simulación. Tanda larga = ritmo de carrera en FP2.
  México = qualy media en el Hermanos Rodríguez desde 2015. “No rodó” en FP1 suele ser un titular que cedió el coche a un novato.
  La línea punteada marca el corte de Q3.</p>
  <p class="desliza">Desliza la tabla para ver todas las columnas →</p>
  <div class="tw"><table class="full">
    <tr><th class="num">Pron.</th><th class="fijo">Piloto</th><th class="num">FP1</th><th class="num">FP2</th><th class="num">Tanda larga</th>
    <th class="num">Qualy últ. 5</th><th class="num">México</th><th class="num">Rango</th><th>P(Q3)</th><th class="num">P(Top 3)</th><th class="num">P(Pole)</th></tr>
    {''.join(filas)}
  </table></div>
</section>
</div>

<div class="picado mini" aria-hidden="true"></div>

<div class="wrap">
<section id="modelos">
  <h2>{flor()}Duelo de modelos</h2>
  <p class="lead">Validación walk-forward: cada GP de {periodo} se predijo entrenando <i>sólo</i> con fines de semana anteriores.
  Gana el modelo con más aciertos en el Top 10 (desempate: correlación de Spearman).</p>
  <p class="desliza">Desliza la tabla para ver todas las columnas →</p>
  <div class="tw"><table>
    <tr><th class="fijo">Modelo</th><th class="num">Top 10 aciertos</th><th class="num">Top 10 en 2026</th><th class="num">Spearman</th>
    <th class="num">Error medio (pos.)</th><th class="num">Pole acertada</th><th class="num">Top 3 aciertos</th><th class="num">GPs</th></tr>
    {''.join(mod)}
  </table></div>
</section>

<section class="two">
  <div class="card">
    <h2>{flor()}Qué pesa más</h2>
    <p class="lead">{imp_lead}</p>
    {imps}
  </div>
  <div class="card">
    <h2>{flor()}Así le ha ido en 2026</h2>
    <p class="lead">{val_lead}</p>
    {val}
  </div>
</section>

<section class="card ofrenda">
  <h2>{flor()}Altar de poles</h2>
  <p class="lead">Poles en el {e(gp['circuito'])} desde su regreso al calendario en 2015{nota_faltan}.
  Borde turquesa: el piloto sigue en la parrilla 2026.</p>
  <div class="altar">{altar}</div>
  <div class="guirnalda" aria-hidden="true"></div>
</section>

<section class="card">
  <h2>{flor()}Los que mandan en México</h2>
  <p class="lead">Parrilla actual, ordenada por su qualy media en el Hermanos Rodríguez desde 2015. Q3 = veces en el Top 10.
  La tira muestra su posición de qualy año por año.</p>
  <p class="desliza">Desliza la tabla para ver la tira año por año →</p>
  <div class="tw"><table class="reyes"><tr><th>Piloto</th><th class="num">Visitas</th><th class="num">Q3</th><th class="num">Poles</th>
  <th class="num">Mejor</th><th class="num">Media</th><th>{anios_tira}</th></tr>{rey}</table></div>
  <div class="leyenda tl"><span><i class="t1"></i>Pole</span><span><i class="t3"></i>P2–P3</span><span><i class="t10"></i>P4–P10</span><span><i class="tx"></i>P11 o peor</span><span><i class="t0"></i>No corrió</span></div>
</section>

<section id="metodo">
  <h2>{flor()}Cómo se armó</h2>
  <div class="card metodo">
  <b>Datos:</b> OpenF1 (vueltas, sectores, speed traps, compuestos, stints y clima de FP1/FP2 de 2023–2026) y Jolpica/Ergast
  (qualys y carreras 2018–2026, más el historial del Hermanos Rodríguez desde 2015).<br>
  <b>Variables ({n_vars}):</b> gap y posición de la mejor vuelta en FP1, FP2 y combinada; vuelta ideal por sectores; speed trap e
  intermedias; mejor vuelta con blando; ritmo de tanda larga; consistencia; vueltas completadas; mejora FP1→FP2; ritmo del equipo y delta
  contra el compañero; forma en qualy (últimas 3/5/10, temporada, % de Q3, volatilidad); forma en carrera, puntos y posición en el
  campeonato; historial en el circuito; forma del equipo; sesgo histórico “prácticas → qualy” del piloto y del equipo (quién suele
  esconder ritmo el viernes); lluvia/temperatura y fin de semana sprint.<br>
  <b>Modelos comparados:</b> {len(tabla)} en total, entre baselines, Ridge, Random Forest, Extra Trees, Gradient Boosting, XGBoost, LightGBM,
  rankers (LambdaRank, XGBoost Ranker) y ensambles. Ganó: <b>{e(mejor)}</b>. Lo reciente pesa más: 2026 (nuevo reglamento) cuenta 3× y 2025, 1.5×.<br>
  <b>Entrenamiento:</b> {n_train:,} filas piloto-GP de {n_gp} Grandes Premios.<br>
  <b>Probabilidades:</b> Monte Carlo (20,000 simulaciones) con los errores reales de validación del modelo.
  </div>
</section>

<section id="advertencias">
  <h2>{flor()}Lo que el modelo no ve</h2>
  <div class="ojo">
    <div class="card">{icono("novato")}<h3>Novatos en la FP1</h3>
      <p>{txt_fp1}</p></div>
    <div class="card">{icono("montana")}<h3>2,240 metros de altura</h3>
      <p>El aire de la Ciudad de México es ~20% menos denso: los coches generan menos carga aerodinámica aun con alerón de máximo apoyo,
      alcanzan velocidades punta altísimas en la recta de 1.2 km y sufren para enfriar motor y frenos. Lo que se vio en otras pistas
      se traduce peor aquí.</p></div>
    <div class="card">{icono("rayo")}<h3>Primera vez del reglamento 2026 en la altura</h3>
      <p>Los coches 2026 (más energía eléctrica, aerodinámica activa) nunca han corrido en el Hermanos Rodríguez: el historial del
      circuito viene de otros autos, así que pesa menos de lo que parece.</p></div>
    <div class="card">{icono("bandera")}<h3>Lo que pasa el sábado</h3>
      <p>No ve la FP3, ni lluvia en la qualy, banderas rojas, límites de pista en el Foro Sol o tráfico en la vuelta lanzada.
      Las penalizaciones de motor no cambian la posición de qualy, sólo la salida. Aun el mejor modelo acierta
      ~{fnum(fila_mejor.top10_hits, 0)} de 10.</p></div>
  </div>
</section>
</div>
</main>

<footer>
  <div class="picado mini" aria-hidden="true"></div>
  <div class="cuadros"></div>
  <div class="wrap">
    <span>Generado {ahora} · Datos: OpenF1 &amp; Jolpica-F1 · Proyecto no oficial, sin relación con Formula 1 ni con el {e(gp['nombre'])}.</span>
    <span class="deco">¡Que viva la velocidad!</span>
  </div>
</footer>
</body></html>"""
    ruta.write_text(doc, encoding="utf-8")
    print("HTML ->", ruta)
    return ruta
