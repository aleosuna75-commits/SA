# -*- coding: utf-8 -*-
"""
================================================================================
  EXTRACTOR LIGA MX — 10 AÑOS  (alimenta al Cerebro Liga MX 2026)   v6
================================================================================
Conecta a una base pública que YA contiene el histórico de Liga MX y descarga
los últimos ~10 años (20 torneos cortos: Apertura + Clausura de cada campaña),
dejándolos en el CSV exacto que consume cerebro_ligamx_2026.py:

    fecha,local,visitante,gl,gv,fase

FUENTE PRINCIPAL: FBref.com (Sports Reference) vía la librería `soccerdata`.
FUENTE DE RESPALDO: ESPN (mismo paquete soccerdata) si FBref cambia el HTML.

--------------------------------------------------------------------------------
CAMBIOS v6 (respecto a v5):
  * Soporte para redes corporativas que interceptan HTTPS (proxy TLS / MITM).
    El error 'CERTIFICATE_VERIFY_FAILED' aparece porque Python (OpenSSL estricto)
    no confia en la CA corporativa que Windows SI acepta. Se agrega truststore
    para validar con el almacen de Windows; se instala con --instalar.
  * Nuevo flag --sin-verificar-ssl como ultimo recurso (datos publicos en red
    de confianza).
  * Mensajes de error detectan la causa SSL y guian al fix correcto.

CAMBIOS v5 (respecto a v4):
  * FBref por HTTP es ahora el DEFAULT (--fuente fbref-http). Se ELIMINO por
    completo la ruta con Chrome/Selenium: en la maquina corporativa la mataba
    Elastic Security, asi que ya no tiene sentido tenerla.
  * La ruta default (fbref-http) NO usa soccerdata ni Chrome: es HTTP puro. Solo
    se pide/instala soccerdata si eliges --fuente espn (o --con-elo).
  * Correr el script SIN flags ya va por HTTP directo.

CAMBIOS v4 (respecto a v3):
  * Nueva fuente --fuente fbref-http: baja FBref con HTTP puro (sin navegador),
    util cuando la seguridad corporativa (Elastic Security de GPV) bloquea la
    automatizacion de Chrome ("Browser Debugging from Unusual Parent"). No burla
    ningun control: es un GET normal a una pagina publica. Puede fallar si
    Cloudflare responde 403; en ese caso, --fuente espn.
  * Mensajes de error especificos por fuente (fbref / fbref-http / espn).

CAMBIOS v3 (respecto a v2):
  * El CSV se guarda en una carpeta destino FIJA:
        C:\\Users\\asunad\\OneDrive - GPV\\Documents\\Liga MX
    (si esa carpeta no existe -p.ej. en otra maquina- usa la del script).
  * Blindaje contra la "salida silenciosa" de FBref: si Selenium/Chrome mata
    el proceso con SystemExit y sin traceback, ahora se atrapa y se muestra un
    mensaje claro que manda al respaldo ESPN.

CAMBIOS v2 (respecto a v1):
  * Chequeo de dependencia AL ARRANQUE: si falta `soccerdata`, imprime el
    comando exacto de instalación usando TU intérprete (sys.executable) y sale
    limpio. Con --instalar lo instala solo.
  * Mensaje de respaldo corregido: ESPN también usa soccerdata, así que solo se
    sugiere como fallback ante errores de scraping/red, no de librería faltante.
  * El CSV se guarda JUNTO AL SCRIPT por defecto (da igual desde qué carpeta
    lo corras). Antes usaba el directorio actual y podía caer en otra carpeta.
--------------------------------------------------------------------------------
INSTALACIÓN (una sola vez):
    <tu-python> -m pip install soccerdata
  o deja que el script lo haga:
    <tu-python> extractor_ligamx_10anios.py --instalar

USO:
    <tu-python> extractor_ligamx_10anios.py                 # 10 anios -> CSV
    <tu-python> extractor_ligamx_10anios.py --anios 8       # ultimos 8 anios
    <tu-python> extractor_ligamx_10anios.py --fuente espn   # usar ESPN
    <tu-python> extractor_ligamx_10anios.py --con-elo       # + ratings ClubElo

  (<tu-python> = C:\\Users\\asunad\\.venv\\Scripts\\python.exe en tu caso)

SALIDA:
    historico_ligamx.csv   (junto a este script)  ->  se lo pasas al Cerebro:
        <tu-python> cerebro_ligamx_2026.py --historico historico_ligamx.csv
--------------------------------------------------------------------------------
Autor: Ale (asunad) + Claude | Proyecto actuarial, sin fines de lucro
================================================================================
"""

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd

# Carpeta donde vive este script (fallback para guardar el CSV)
BASE_DIR = Path(__file__).resolve().parent

# Carpeta destino PREFERIDA para el CSV (solicitada explicitamente).
# Si existe, el CSV cae aqui; si no (p.ej. otra maquina), usa BASE_DIR.
CARPETA_PREFERIDA = Path(r"C:\Users\asunad\OneDrive - GPV\Documents\Liga MX")


def carpeta_salida() -> Path:
    """Carpeta donde se guardara el CSV: la preferida si existe, si no la del script."""
    return CARPETA_PREFERIDA if CARPETA_PREFERIDA.exists() else BASE_DIR


# ==============================================================================
# 0-BIS. TLS EN REDES CORPORATIVAS (proxy que intercepta HTTPS)
# ------------------------------------------------------------------------------
# GPV intercepta el trafico HTTPS y re-firma los certificados con una CA
# corporativa. Windows confia en ella (por eso el navegador y pip funcionan),
# pero Python (OpenSSL 3.x estricto) la rechaza -> 'CERTIFICATE_VERIFY_FAILED:
# Basic Constraints of CA cert not marked critical'.
#
# Solucion limpia: 'truststore' hace que Python valide con el almacen de
# certificados de Windows (que SI tiene la CA corporativa). Arregla TODO el
# HTTPS del script (fbref-http y ESPN por igual).
# Ultimo recurso: --sin-verificar-ssl desactiva la verificacion (solo datos
# publicos en una red corporativa de confianza).
# ==============================================================================

def configurar_ssl(sin_verificar: bool, auto_instalar: bool):
    if sin_verificar:
        import ssl
        ssl._create_default_https_context = ssl._create_unverified_context
        print("  [SSL] AVISO: verificacion de certificado DESACTIVADA (--sin-verificar-ssl).")
        print("        Aceptable solo para datos publicos en red corporativa de confianza.")
        return

    if importlib.util.find_spec("truststore") is None:
        if auto_instalar:
            print("  [SSL] instalando truststore (para usar la CA corporativa de Windows) ...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "truststore"])
            except subprocess.CalledProcessError:
                print("  [SSL] no se pudo instalar truststore.")
        else:
            print("  [SSL] Recomendado: instala truststore para usar la CA corporativa:")
            print(f'        & "{sys.executable}" -m pip install truststore')
            print("        (o corre con --instalar; ultimo recurso: --sin-verificar-ssl)")

    if importlib.util.find_spec("truststore") is not None:
        import truststore
        truststore.inject_into_ssl()
        print("  [SSL] validando con el almacen de certificados de Windows (truststore).")
    else:
        print("  [SSL] truststore no disponible; si falla por certificado, usa --sin-verificar-ssl.")


# ==============================================================================
# 0. CHEQUEO DE DEPENDENCIA (lo primero, con mensaje claro)
# ==============================================================================

def soccerdata_disponible() -> bool:
    return importlib.util.find_spec("soccerdata") is not None


def instalar_soccerdata():
    """Instala soccerdata en el MISMO interprete que corre este script."""
    print(f"  [pip] instalando soccerdata en:\n        {sys.executable}")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "soccerdata"])
        print("  [pip] instalacion completada.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [pip] fallo la instalacion (codigo {e.returncode}).")
        return False


def exigir_soccerdata(auto_instalar: bool):
    """Verifica soccerdata; si falta, instala (si --instalar) o explica y sale."""
    if soccerdata_disponible():
        return
    print("\n  [FALTA] La libreria 'soccerdata' no esta instalada en este Python:")
    print(f"          {sys.executable}\n")
    if auto_instalar:
        if instalar_soccerdata() and soccerdata_disponible():
            return
        sys.exit(1)
    print("  Instalala con ESTE comando (usa exactamente este interprete):\n")
    print(f'      & "{sys.executable}" -m pip install soccerdata\n')
    print("  O deja que el script lo haga por ti:\n")
    print(f'      & "{sys.executable}" "{Path(__file__).name}" --instalar\n')
    print("  NOTA: --fuente espn NO evita este paso; ESPN tambien usa soccerdata.")
    sys.exit(1)


# ==============================================================================
# 1. REGISTRO DE LIGA MX EN soccerdata (via league_dict.json)
# ==============================================================================

LIGA_MX_ENTRY = {
    "MEX-Liga MX": {
        "ClubElo": "MEX_1",
        "FBref": "Liga MX",
        "ESPN": "mex.1",
        "Sofascore": "Liga MX",
        "WhoScored": "Mexico - Liga MX",
        "season_start": "Jul",
        "season_end": "May",
    }
}


def registrar_liga_mx():
    """Crea/actualiza league_dict.json para que soccerdata reconozca Liga MX."""
    cfg_dir = Path(
        os.environ.get("SOCCERDATA_DIR", Path.home() / "soccerdata")
    ) / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    f = cfg_dir / "league_dict.json"

    actual = {}
    if f.is_file():
        try:
            actual = json.loads(f.read_text(encoding="utf8"))
        except Exception:
            actual = {}

    if "MEX-Liga MX" not in actual:
        actual.update(LIGA_MX_ENTRY)
        f.write_text(json.dumps(actual, indent=2, ensure_ascii=False), encoding="utf8")
        print(f"  [config] Liga MX registrada en {f}")
    else:
        print(f"  [config] Liga MX ya estaba registrada en {f}")


# ==============================================================================
# 2. NORMALIZACION DE NOMBRES (FBref/ESPN -> nombres canonicos del Cerebro)
# ==============================================================================

MAPA_NOMBRES = {
    # Grandes / actuales
    "Club América": "América", "America": "América", "Club America": "América",
    "Guadalajara": "Chivas", "CD Guadalajara": "Chivas", "Chivas Guadalajara": "Chivas",
    "Cruz Azul": "Cruz Azul",
    "UNAM": "Pumas", "Pumas UNAM": "Pumas", "Club Universidad Nacional": "Pumas",
    "UANL": "Tigres", "Tigres UANL": "Tigres",
    "Monterrey": "Monterrey", "CF Monterrey": "Monterrey",
    "Toluca": "Toluca", "Deportivo Toluca": "Toluca",
    "León": "León", "Club León": "León", "Leon": "León",
    "Pachuca": "Pachuca", "CF Pachuca": "Pachuca",
    "Santos Laguna": "Santos", "Santos": "Santos",
    "Necaxa": "Necaxa", "Club Necaxa": "Necaxa",
    "Puebla": "Puebla", "Club Puebla": "Puebla",
    "Querétaro": "Querétaro", "Queretaro": "Querétaro", "Querétaro FC": "Querétaro",
    "Atlas": "Atlas", "Atlas FC": "Atlas",
    "Tijuana": "Tijuana", "Club Tijuana": "Tijuana", "Xolos": "Tijuana",
    "Atlético San Luis": "Atlético San Luis", "Atletico San Luis": "Atlético San Luis",
    "FC Juárez": "Juárez", "Juárez": "Juárez", "FC Juarez": "Juárez", "Bravos": "Juárez",
    "Atlante": "Atlante", "Atlante FC": "Atlante",
    # Historicos (se conservan con su nombre para el H2H)
    "Mazatlán": "Mazatlán", "Mazatlán FC": "Mazatlán", "Mazatlan": "Mazatlán",
    "Veracruz": "Veracruz", "Tiburones Rojos": "Veracruz",
    "Monarcas Morelia": "Morelia", "Morelia": "Morelia", "Atlético Morelia": "Morelia",
    "Lobos BUAP": "Lobos BUAP", "BUAP": "Lobos BUAP",
    "Chiapas": "Chiapas", "Jaguares": "Chiapas", "Jaguares Chiapas": "Chiapas",
}


def norm(nombre: str) -> str:
    n = str(nombre).strip()
    return MAPA_NOMBRES.get(n, n)


# ==============================================================================
# 3. DETECCION DE FASE (regular vs liguilla)
# ==============================================================================

PALABRAS_LIGUILLA = re.compile(
    r"final|semi|quarter|cuartos|semis|liguilla|reclasific|play|repechaje",
    re.IGNORECASE,
)


def detectar_fase(valor_round: str) -> str:
    s = str(valor_round or "")
    if PALABRAS_LIGUILLA.search(s):
        return "liguilla"
    return "regular"


# ==============================================================================
# 4. PARSEO DE MARCADOR ("2-1", "1 (4)-1 (2)" en penales)
# ==============================================================================

def parsear_marcador(score):
    """Devuelve (gl, gv) o (None, None) si el partido no se jugo."""
    if score is None or (isinstance(score, float) and pd.isna(score)):
        return None, None
    s = str(score)
    s = re.sub(r"\s*\(\d+\)", "", s)  # quita penales entre parentesis
    m = re.match(r"\s*(\d+)\s*[–\-−]\s*(\d+)\s*", s)  # en-dash, guion o menos
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


# ==============================================================================
# 5. LISTA DE TEMPORADAS (ultimos N anios -> paginas de FBref)
# ==============================================================================

def temporadas_ultimos(anios: int):
    hoy = datetime.today()
    inicio_reciente = hoy.year - 1  # 2025 -> temporada 2025-2026
    return [f"{y}-{y + 1}" for y in range(inicio_reciente - anios + 1, inicio_reciente + 1)]


# ==============================================================================
# 6. EXTRACCION
# ==============================================================================

def extraer_espn(seasons):
    import soccerdata as sd
    print(f"  [ESPN] descargando temporadas: {seasons[0]} ... {seasons[-1]}")
    esp = sd.ESPN(leagues="MEX-Liga MX", seasons=seasons)
    return esp.read_schedule().reset_index()


def extraer_fbref_http(seasons):
    """
    Descarga FBref con HTTP PURO (sin navegador, sin Selenium).

    Por que existe: en maquinas con seguridad corporativa (p.ej. Elastic
    Security de GPV) la automatizacion de Chrome que usa soccerdata se BLOQUEA
    y mata el proceso ("Browser Debugging from Unusual Parent"). Esto NO burla
    ese control: es un GET normal a una pagina publica, exactamente lo que hace
    tu navegador al abrir la URL; simplemente no automatiza Chrome, asi que no
    dispara la alerta.

    Limitacion: FBref esta detras de Cloudflare y a veces responde 403 a
    peticiones sin navegador. Si eso pasa, usa --fuente espn.
    """
    import io
    import time
    import urllib.request
    import urllib.error

    COMP_ID = 31  # ID de Liga MX en FBref
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"),
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    dfs = []
    hubo_ssl = False
    print(f"  [FBref-HTTP] descargando via HTTP (sin Chrome): "
          f"{seasons[0]} ... {seasons[-1]}")
    for season in seasons:
        url = (f"https://fbref.com/en/comps/{COMP_ID}/{season}/schedule/"
               f"{season}-Liga-MX-Scores-and-Fixtures")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as e:
            print(f"    [{season}] HTTP {e.code} (Cloudflare/bloqueo). Saltada.")
            time.sleep(3)
            continue
        except Exception as e:
            if "CERTIFICATE_VERIFY" in str(e) or "SSL" in str(e):
                hubo_ssl = True
            print(f"    [{season}] fallo de red: {e}. Saltada.")
            time.sleep(3)
            continue

        # FBref a veces envuelve tablas en comentarios HTML: los quitamos
        html = html.replace("<!--", "").replace("-->", "")
        try:
            tablas = pd.read_html(io.StringIO(html))
        except ValueError:
            print(f"    [{season}] sin tablas legibles (posible reto Cloudflare). Saltada.")
            time.sleep(3)
            continue

        elegida = None
        for t in tablas:
            if isinstance(t.columns, pd.MultiIndex):  # aplanar si hace falta
                t.columns = [c[-1] if isinstance(c, tuple) else c for c in t.columns]
            cols = [str(c) for c in t.columns]
            if any("Score" in c for c in cols) and any("Home" in c for c in cols):
                elegida = t.copy()
                break
        if elegida is None:
            print(f"    [{season}] no se hallo tabla de fixtures. Saltada.")
            time.sleep(3)
            continue

        elegida["season"] = season
        dfs.append(elegida)
        print(f"    [{season}] OK ({len(elegida)} filas crudas)")
        time.sleep(3)  # respeta el limite de FBref (~1 req / 3 s)

    if not dfs:
        if hubo_ssl:
            raise RuntimeError(
                "FBref-HTTP fallo por CERTIFICATE_VERIFY (proxy corporativo SSL). "
                "Instala truststore (--instalar) o usa --sin-verificar-ssl."
            )
        raise RuntimeError(
            "FBref-HTTP no devolvio datos (Cloudflare o red corporativa bloqueando). "
            "Usa --fuente espn."
        )
    return pd.concat(dfs, ignore_index=True)


def normalizar_a_cerebro(df: pd.DataFrame, fuente: str) -> pd.DataFrame:
    """Lleva el DataFrame crudo al esquema fecha,local,visitante,gl,gv,fase."""
    filas = []
    cols = {c.lower(): c for c in df.columns}

    def pick(*cands):
        for c in cands:
            if c in cols:
                return cols[c]
        return None

    c_date = pick("date")
    c_home = pick("home_team", "home")
    c_away = pick("away_team", "away")
    c_round = pick("round", "notes", "week", "stage")
    c_score = pick("score")
    c_hs = pick("home_score", "home_goals")
    c_as = pick("away_score", "away_goals")

    for _, r in df.iterrows():
        if c_score is not None:
            gl, gv = parsear_marcador(r[c_score])
        else:
            try:
                gl = int(r[c_hs]); gv = int(r[c_as])
            except (ValueError, TypeError):
                gl, gv = None, None
        if gl is None or gv is None:
            continue

        try:
            fecha = pd.to_datetime(r[c_date]).date().isoformat()
        except Exception:
            continue

        filas.append({
            "fecha": fecha,
            "local": norm(r[c_home]),
            "visitante": norm(r[c_away]),
            "gl": gl,
            "gv": gv,
            "fase": detectar_fase(r[c_round]) if c_round else "regular",
        })

    return pd.DataFrame(filas).sort_values("fecha").reset_index(drop=True)


# ==============================================================================
# 7. BONUS: ratings ClubElo (opcional)
# ==============================================================================

def extraer_elo(seasons):
    import soccerdata as sd
    print("  [ClubElo] descargando ratings historicos ...")
    try:
        elo = sd.ClubElo()
        anio = seasons[-1].split("-")[0]
        snap = elo.read_by_date(f"{anio}-07-15").reset_index()
        snap["team_norm"] = snap["team"].map(norm)
        return snap
    except Exception as e:
        print(f"  [ClubElo] no disponible: {e}")
        return None


# ==============================================================================
# 8. MAIN
# ==============================================================================

def main():
    ap = argparse.ArgumentParser(description="Extractor 10 anios Liga MX -> CSV para el Cerebro")
    ap.add_argument("--anios", type=int, default=10, help="Anios de historico (default 10)")
    ap.add_argument("--fuente", choices=["fbref-http", "espn"], default="fbref-http",
                    help="fbref-http=FBref por HTTP (default, sin Chrome); espn=respaldo HTTP")
    ap.add_argument("--salida", default=None,
                    help="Ruta del CSV (default: junto a este script)")
    ap.add_argument("--con-elo", action="store_true", help="Tambien exporta ratings ClubElo")
    ap.add_argument("--instalar", action="store_true",
                    help="Instala truststore (y soccerdata si usas ESPN) y continua")
    ap.add_argument("--sin-verificar-ssl", action="store_true",
                    help="Desactiva verificacion TLS (ultimo recurso en red corporativa con proxy)")
    args = ap.parse_args()

    print("=" * 74)
    print("  EXTRACTOR LIGA MX — 10 ANIOS  (v6)")
    print("=" * 74)

    # 0. TLS: en redes corporativas (proxy que intercepta HTTPS) hay que confiar
    # en la CA corporativa; truststore usa el almacen de Windows para lograrlo.
    configurar_ssl(args.sin_verificar_ssl, auto_instalar=args.instalar)

    # salida por defecto: carpeta Liga MX del usuario (o junto al script como fallback)
    salida = Path(args.salida) if args.salida else (carpeta_salida() / "historico_ligamx.csv")
    seasons = temporadas_ultimos(args.anios)

    # soccerdata SOLO se necesita para ESPN (y para --con-elo). La ruta por
    # DEFAULT (fbref-http) es HTTP puro: no usa soccerdata ni Chrome, asi que
    # no dispara la seguridad corporativa (Elastic) ni pide instalar nada.
    necesita_soccerdata = (args.fuente == "espn") or args.con_elo
    if necesita_soccerdata:
        print("[1/3] Preparando soccerdata (requerido por ESPN/ClubElo) ...")
        exigir_soccerdata(auto_instalar=args.instalar)
        registrar_liga_mx()
    else:
        print("[1/3] Fuente HTTP pura (sin Chrome, sin soccerdata).")

    print(f"[2/3] {args.anios} anios -> {len(seasons)} temporadas ({len(seasons)*2} torneos cortos)")
    print(f"      Descargando desde {args.fuente.upper()} ...")
    try:
        if args.fuente == "fbref-http":
            crudo = extraer_fbref_http(seasons)
        else:
            crudo = extraer_espn(seasons)
    except ImportError as e:
        print(f"\n  [ERROR] Falta una libreria: {e}")
        print(f'  Instala con:  & "{sys.executable}" -m pip install soccerdata')
        sys.exit(1)
    except Exception as e:
        msg = str(e) or type(e).__name__
        print(f"\n  [ERROR] Fallo la descarga de {args.fuente.upper()}: {msg}")
        n = Path(__file__).name
        if "CERTIFICATE_VERIFY" in msg or "SSL" in msg:
            print("  Causa: certificado corporativo (proxy que intercepta HTTPS).")
            print("  Arreglalo con truststore (usa la CA de Windows):")
            print(f'    & "{sys.executable}" "{n}" --instalar')
            print(f'  O ultimo recurso:  & "{sys.executable}" "{n}" --sin-verificar-ssl')
        elif args.fuente == "fbref-http":
            print("  Causa probable: Cloudflare (403). Usa el respaldo ESPN:")
            print(f'    & "{sys.executable}" "{n}" --fuente espn')
        sys.exit(1)

    df = normalizar_a_cerebro(crudo, args.fuente)
    if df.empty:
        print("\n  [AVISO] No se extrajo ningun partido jugado. Revisa la fuente/temporadas.")
        sys.exit(1)

    df.to_csv(salida, index=False, encoding="utf-8-sig")

    print("[3/3] Listo.")
    print("-" * 74)
    print(f"  Partidos jugados exportados : {len(df):,}")
    print(f"  Rango de fechas             : {df['fecha'].min()}  ->  {df['fecha'].max()}")
    print(f"  Equipos distintos           : {df['local'].nunique()}")
    print(f"  Partidos de liguilla        : {(df['fase']=='liguilla').sum():,}")
    print(f"  Archivo                     : {salida}")
    print("-" * 74)
    print("  Siguiente paso:")
    print(f'    & "{sys.executable}" cerebro_ligamx_2026.py --historico "{salida}"')
    print("  El Cerebro recalibra por MLE y mina patrones H2H automaticamente.")

    if args.con_elo:
        elo = extraer_elo(seasons)
        if elo is not None:
            ruta_elo = carpeta_salida() / "elo_ligamx.csv"
            elo.to_csv(ruta_elo, index=False, encoding="utf-8-sig")
            print(f"\n  [ClubElo] ratings -> {ruta_elo} ({len(elo)} clubes)")


if __name__ == "__main__":
    main()
