# -*- coding: utf-8 -*-
"""
Convierte los datos de Liga MX de openfootball (formato Football.TXT, dominio
publico CC0) al CSV que consume el Cerebro: fecha,local,visitante,gl,gv,fase.

Fuente: https://github.com/openfootball/world -> north-america/mexico/*_mx1.txt
Descarga (una vez):
    curl -sL https://codeload.github.com/openfootball/world/tar.gz/refs/heads/master -o world.tar.gz
    tar xzf world.tar.gz
Uso:
    python parsear_openfootball.py
"""
import re, glob, csv

MAP = {
    "CF América": "América", "Deportivo Guadalajara": "Chivas",
    "UANL Tigres": "Tigres", "Pumas UNAM": "Pumas",
    "Atlas Guadalajara": "Atlas", "Gallos Blancos": "Querétaro",
    "Deportivo Toluca": "Toluca", "Club León": "León",
    "Santos Laguna": "Santos", "CF Monterrey": "Monterrey",
    "CF Pachuca": "Pachuca", "Club Necaxa": "Necaxa",
    "Club Tijuana": "Tijuana", "Atlético San Luis": "Atlético San Luis",
    "Mazatlán FC": "Mazatlán", "FC Juárez": "Juárez",
    "Puebla FC": "Puebla", "Cruz Azul": "Cruz Azul", "Atlante": "Atlante",
    # historicos (se conservan para el H2H)
    "CD Veracruz": "Veracruz", "Chiapas FC": "Chiapas",
    "Jaguares Chiapas": "Chiapas", "Monarcas Morelia": "Morelia",
    "Club San Luis": "San Luis", "Dorados de Sinaloa": "Dorados",
    "Estudiantes Tecos": "Tecos", "Leones Negros": "Leones Negros",
    "Lobos BUAP": "Lobos BUAP",
}
MES = {m: i for i, m in enumerate(
    ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], 1)}

RE_HEADER = re.compile(r"^=\s*Liga MX\s+(\d{4})/\d{2}")
RE_STAGE  = re.compile(r"^▪\s*(.+?),")
RE_DATE   = re.compile(r"^\s+[A-Z][a-z]{2}\s+([A-Z][a-z]{2})\s+(\d{1,2})(?:\s+(\d{4}))?\s*$")
RE_MATCH  = re.compile(r"^\s*(?:\d{1,2}:\d{2})?\s+(\S.*?\S)\s+v\s+(\S.*?\S)\s{2,}(.+)$")


def parse_score(rest):
    """Marcador real del partido: si hubo tiempo extra usa el de a.e.t. (no penales)."""
    if "a.e.t." in rest:
        m = re.search(r"(\d+)-(\d+)\s+a\.e\.t\.", rest)
        if m:
            return int(m.group(1)), int(m.group(2))
    m = re.match(r"\s*(\d+)-(\d+)", rest)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None  # [cancelled], [awarded], etc.


def norm(t):
    return MAP.get(t.strip(), t.strip())


def main():
    filas, sin_match = [], []
    for f in sorted(glob.glob("world-master/north-america/mexico/*_mx1.txt")):
        cur_year, cur_month, fase = None, None, "regular"
        for raw in open(f, encoding="utf-8"):
            ln = raw.rstrip("\n").rstrip("\r")
            h = RE_HEADER.match(ln)
            if h:
                cur_year = int(h.group(1))
                continue
            s = RE_STAGE.match(ln)
            if s:
                fase = "liguilla" if "Playoffs" in s.group(1) else "regular"
                continue
            d = RE_DATE.match(ln)
            if d:
                cur_month = MES[d.group(1)]
                day = int(d.group(2))
                if d.group(3):
                    cur_year = int(d.group(3))
                cur_day = day
                continue
            mt = RE_MATCH.match(ln)
            if mt and cur_year and cur_month:
                sc = parse_score(mt.group(3))
                if sc is None:
                    continue
                gl, gv = sc
                filas.append({
                    "fecha": f"{cur_year:04d}-{cur_month:02d}-{cur_day:02d}",
                    "local": norm(mt.group(1)),
                    "visitante": norm(mt.group(2)),
                    "gl": gl, "gv": gv, "fase": fase,
                })
            elif " v " in ln and re.search(r"\d-\d", ln) and not mt:
                sin_match.append((f, ln))

    filas.sort(key=lambda r: r["fecha"])
    with open("historico_ligamx.csv", "w", newline="", encoding="utf-8-sig") as out:
        w = csv.DictWriter(out, fieldnames=["fecha","local","visitante","gl","gv","fase"])
        w.writeheader()
        w.writerows(filas)

    print(f"Partidos exportados : {len(filas):,}")
    print(f"Rango de fechas     : {filas[0]['fecha']} -> {filas[-1]['fecha']}")
    eq = sorted(set(r['local'] for r in filas) | set(r['visitante'] for r in filas))
    print(f"Equipos distintos   : {len(eq)}")
    print(f"Partidos liguilla   : {sum(1 for r in filas if r['fase']=='liguilla'):,}")
    if sin_match:
        print(f"\n[QA] Lineas con ' v ' y digito que NO parsearon: {len(sin_match)}")
        for f, l in sin_match[:10]:
            print("   ", l.strip())
    else:
        print("\n[QA] Todas las lineas de partido parsearon correctamente.")


if __name__ == "__main__":
    main()
