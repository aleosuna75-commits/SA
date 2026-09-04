# -*- coding: utf-8 -*-
"""
================================================================================
 mec_devengamiento.py  ·  v2  ·  Método de Emergencia por Cohortes (MEC)
 FRAMEWORK MODULAR — SOLO PARA EL FACTOR DE NO DEVENGAMIENTO (FND)
--------------------------------------------------------------------------------
 Planeación Financiera (BP&A) · Reaseguradora Patria (GPV)

 QUÉ CAMBIÓ EN LA v2 (importante)
 --------------------------------
 La v1 construía el FND de un triángulo de cohortes sobre la columna PrimasNal.
 Se verificó que esa columna es PRIMA REGISTRADA (suscrita/causada en el mes
 contable), no prima devengada por riesgo corrido:

   · La BD se genera de dbo_aMOG_MovGonzalo (Tipo=5); en Gonz "devengado" es
     causación contable, cuyo opuesto es pagado/caja.
   · La BD no tiene columna de prima devengada ni de reservas; sí tiene
     Cuentas Rendidas, Dentro de, A pagar en, Periodos y Meses Periodo.
   · Evidencia empírica: 94% de la prima tiene vigencia <=12 meses (mediana 11),
     pero el triángulo llegaba a "100% emergido" hacia el mes 6. Eso es la cuenta
     que terminó de llegar, no el riesgo expirado.

 Por eso el FND ya NO sale de un triángulo de registro. Sale de la PRORRATA
 EXACTA de las fechas de vigencia reales de cada registro (PF+), agregada por
 ramo. El patrón de registro se conserva, pero en su lugar correcto: mide prima
 aún no reportada (afecta a PT), NO el devengamiento.

 ALCANCE (candado): esto sustituye SOLO la fuente del FND. FS/BELMEDIA, el
 desarrollo de siniestros (1-LAG), el margen de riesgo, el IRR y el índice se
 mantienen con el método vigente.

 Módulos:
   M1 datos       · registros de prima con vigencia (ini, fin) y ramo
   M2 prorrata    · FND(ramo, antiguedad) exacto por fechas reales   <- LA BASE
   M3 apertura    · qué ramos merecen vector propio vs el de cartera
   M4 frecuencia  · escenarios por periodicidad de cuentas (t)
   M5 exposicion  · curva no lineal dentro de la vigencia (PENDIENTE: SIREC)
   M6 publicacion · TablaFND (ramo x antiguedad) + API de integración
================================================================================
"""
from __future__ import annotations
import os
import numpy as np
import pandas as pd

EPOCH_EXCEL = pd.Timestamp('1899-12-30')   # los seriales de fecha de la BD nacen aquí


# =============================================================================
# CONFIGURACIÓN
# =============================================================================
class ConfigMEC:
    # Archivo de registros que produce construir_input_mec.py
    ARCHIVO_REGISTROS = "Registros_Vigencia_MEC.csv"

    HORIZONTE = 24            # meses del vector FND publicado (cola plana después)
    # --- compuerta de apertura por ramo (back-testing fuera de muestra, en pesos) ---
    MARGEN_APERTURA = 0.10    # reducción relativa mínima del error para abrir el ramo
    FRAC_TRAIN = 0.70         # percentil de fechas de inicio que separa train/test
    PARTICIONES = (0.55, 0.60, 0.65, 0.70, 0.75, 0.80)  # cortes para la prueba de estabilidad
    MIN_PARTICIONES = 6       # el ramo debe ganar en TODAS las particiones para abrir
    UMBRAL_MATERIAL = 0.04    # dif media mínima vs cartera (pp) para que abrir valga la pena
    N_CORTES = 4              # fechas de valuación usadas en la evaluación
    MIN_RESERVA_BACKTEST = 5e5  # reserva mínima evaluada para que la decisión cuente
    DIAS_MES = 30.0          # convención de la casa para el desplazamiento por frecuencia
    DIAS_ANIO = 365.0

    # Campos del row que usan las funciones de integración (RRC / SONR)
    COL_RAMO = "Ramo"
    COL_CALMONTH = "CALMONTH"     # mes contable de valuación (AAAAMM)
    COL_INIVIG = "IniVig"         # inicio de vigencia -> ancla de la antigüedad
    COL_FINVIG = "FinVig"         # fin de vigencia -> permite FND EXACTO (sin vector)
    USAR_EXACTO_SI_HAY_FECHAS = True   # prorrata exacta del registro cuando ambas fechas existen
    COL_FREC = "FRECUENCIA"       # periodicidad de cuentas

    # Mapeo de la FRECUENCIA del script a meses del periodo de cuentas.
    # AJUSTAR si el catálogo de la casa usa otra codificación.
    FREC_MESES = {1: 1, 2: 3, 3: 4, 4: 6, 5: 12}


# =============================================================================
# M1 · DATOS — registros de prima con vigencia real
# =============================================================================
def m1_cargar_registros(ruta_o_dir, cfg: ConfigMEC = ConfigMEC()) -> pd.DataFrame | None:
    """Lee el archivo de registros (Ramo | ini | fin | Prima). Devuelve None si no
    existe: en ese caso la tabla queda inactiva y todo opera con el método legado."""
    ruta = ruta_o_dir
    if os.path.isdir(str(ruta_o_dir)):
        ruta = os.path.join(ruta_o_dir, cfg.ARCHIVO_REGISTROS)
    if not os.path.exists(ruta):
        print(f"[MEC] Aviso: no encontré '{ruta}'. El devengamiento usará el método "
              f"legado (xPND) hasta que se genere el archivo de registros.")
        return None
    df = pd.read_csv(ruta, parse_dates=["ini", "fin"])
    faltan = {"Ramo", "ini", "fin", "Prima"} - set(df.columns)
    if faltan:
        print(f"[MEC] Aviso: al archivo de registros le faltan columnas {faltan}. Se usa el legado.")
        return None
    dur = (df["fin"] - df["ini"]).dt.days
    df = df[(dur > 0) & (dur <= 3660)].copy()
    return df


# =============================================================================
# M2 · PRORRATA — el FND exacto por fechas reales  (LA BASE DEL MÉTODO)
# =============================================================================
def _fnd_registro(ini: pd.Series, fin: pd.Series, k: int) -> np.ndarray:
    """Fracción NO expirada de la vigencia al CIERRE del mes k, contado desde el
    mes de inicio de vigencia. k=0 es el cierre del propio mes de inicio."""
    per = (ini.dt.year * 12 + (ini.dt.month - 1)) + k
    corte = pd.to_datetime(dict(year=per // 12, month=per % 12 + 1, day=1)) + pd.offsets.MonthEnd(0)
    rest = (fin - corte).dt.days
    dur = (fin - ini).dt.days
    return np.clip(rest / dur, 0.0, 1.0)


def m2_fnd_prorrata(df: pd.DataFrame, cfg: ConfigMEC = ConfigMEC()):
    """FND(ramo, antigüedad) por prorrata exacta, ponderado por prima.
    Devuelve (vectores_por_ramo, vector_cartera, pesos_por_ramo)."""
    H = cfg.HORIZONTE
    d = df.copy()
    for k in range(H):
        d[f"_f{k}"] = _fnd_registro(d["ini"], d["fin"], k)

    total = d["Prima"].sum()
    if total == 0:
        return {}, None, {}
    cartera = np.array([(d["Prima"] * d[f"_f{k}"]).sum() / total for k in range(H)])

    vectores, pesos = {}, {}
    for ramo, g in d.groupby("Ramo"):
        t = g["Prima"].sum()
        if abs(t) < 1.0:
            continue
        vectores[str(ramo)] = np.array([(g["Prima"] * g[f"_f{k}"]).sum() / t for k in range(H)])
        pesos[str(ramo)] = abs(t) / abs(total)
    return vectores, cartera, pesos


# =============================================================================
# M3 · APERTURA — qué ramos merecen vector propio
# =============================================================================
def _backtest_particion(df: pd.DataFrame, vectores: dict, cartera, pesos: dict,
                        cfg: ConfigMEC, frac_train: float) -> dict:
    """Decide por BACK-TESTING FUERA DE MUESTRA, medido en PESOS DE RESERVA.

    Por qué no basta comparar curvas: dos vectores pueden verse distintos y aun así
    aproximar peor la reserva, porque lo que importa es el error ponderado por la
    prima realmente vigente a cada antigüedad, no la distancia entre curvas. Se
    verificó con datos reales que el criterio de "diferencia de curvas" abría un
    ramo cuyo vector propio aproximaba PEOR y dejaba fuera a cuatro que mejoraban.

    Procedimiento:
      1. Se estiman vectores SOLO con las vigencias iniciadas antes del corte de
         entrenamiento (percentil FRAC_TRAIN de las fechas de inicio).
      2. Se evalúan sobre el negocio POSTERIOR a ese corte, en varias fechas de
         valuación, comparando contra la verdad (prorrata exacta de cada registro).
      3. Abre el ramo si su vector propio reduce el error al menos MARGEN_APERTURA
         en términos relativos.
    """
    fechas = df["ini"].sort_values()
    corte_train = fechas.quantile(frac_train)
    tr = df[df["ini"] < corte_train]
    te = df[df["ini"] >= corte_train]
    if len(tr) < 50 or len(te) < 20:          # sin historia suficiente: prudente
        return {r: dict(abrir=False, err_propio=np.nan, err_cartera=np.nan,
                        mejora=0.0, peso=pesos.get(r, 0.0), reserva=0.0) for r in vectores}

    vec_tr, cart_tr, _ = m2_fnd_prorrata(tr, cfg)
    if cart_tr is None:
        return {r: dict(abrir=False, err_propio=np.nan, err_cartera=np.nan,
                        mejora=0.0, peso=pesos.get(r, 0.0), reserva=0.0) for r in vectores}

    fin_max = te["ini"].max()
    cortes = pd.date_range(end=fin_max, periods=cfg.N_CORTES, freq="QE")
    acum = {}
    for corte in cortes:
        d = te[(te["ini"] <= corte) & (te["fin"] > corte)].copy()
        if d.empty:
            continue
        d["k"] = (corte.year - d["ini"].dt.year) * 12 + (corte.month - d["ini"].dt.month)
        d = d[(d["k"] >= 0) & (d["k"] < cfg.HORIZONTE)]
        if d.empty:
            continue
        d["real"] = np.clip((d["fin"] - corte).dt.days / (d["fin"] - d["ini"]).dt.days, 0, 1)
        for ramo, g in d.groupby("Ramo"):
            rs = str(ramo)
            if rs not in vec_tr:
                continue
            a = acum.setdefault(rs, dict(real=0.0, prop=0.0, cart=0.0))
            ks = g["k"].to_numpy()
            a["real"] += float((g["Prima"] * g["real"]).sum())
            a["prop"] += float((g["Prima"].to_numpy() * vec_tr[rs][ks]).sum())
            a["cart"] += float((g["Prima"].to_numpy() * cart_tr[ks]).sum())

    dec = {}
    for ramo in vectores:
        a = acum.get(ramo)
        if not a or abs(a["real"]) < cfg.MIN_RESERVA_BACKTEST:
            dec[ramo] = dict(abrir=False, err_propio=np.nan, err_cartera=np.nan,
                             mejora=0.0, peso=pesos.get(ramo, 0.0), reserva=abs(a["real"]) if a else 0.0)
            continue
        ep = abs(a["prop"] - a["real"]) / abs(a["real"])
        ec = abs(a["cart"] - a["real"]) / abs(a["real"])
        mejora = (1.0 - ep / ec) if ec > 0 else 0.0
        dec[ramo] = dict(abrir=bool(mejora >= cfg.MARGEN_APERTURA),
                         err_propio=ep, err_cartera=ec, mejora=mejora,
                         peso=pesos.get(ramo, 0.0), reserva=abs(a["real"]))
    return dec


def m3_decision_apertura(df: pd.DataFrame, vectores: dict, cartera, pesos: dict,
                         cfg: ConfigMEC = ConfigMEC()) -> dict:
    """Compuerta final de apertura. El ramo abre SÓLO si cumple LAS DOS cosas:

      (A) MATERIALIDAD: su vector PF+ se separa de la cartera al menos
          UMBRAL_MATERIAL en promedio. Si el vector es casi idéntico a la cartera
          (2-3 pp), darle vector propio es sobre-ingeniería: no cambia la reserva.
      (B) PERSISTENCIA: gana el back-test fuera de muestra (en pesos de reserva)
          en TODAS las particiones de entrenamiento, para que la diferencia no sea
          un capricho de la mezcla de un solo año.

    Por qué las dos: con prorrata casi todos los ramos quedan pegados a la cartera
    (la vigencia es ~12 meses en todo el libro), así que el back-test por sí solo
    abría ramos cuya mejora era grande en términos RELATIVOS pero sobre errores
    diminutos, con vectores prácticamente iguales a la cartera. La materialidad
    filtra eso y deja sólo a los que de verdad se comportan distinto por duración
    (p. ej. Vida, con cola multianual). Nota: la particularidad de Agro es
    ESTACIONAL, no de duración, y la prorrata no la ve — eso se resuelve con la
    curva de exposición (M5, pendiente de SIREC), no aquí."""
    H = min(cfg.HORIZONTE, len(cartera))
    resultados = [_backtest_particion(df, vectores, cartera, pesos, cfg, f)
                  for f in cfg.PARTICIONES]
    base = resultados[len(resultados) // 2]          # partición central, para reportar
    ca_full = np.asarray(cartera[:H])
    dec = {}
    for ramo, v in vectores.items():
        va = np.asarray(v[:H])
        # materialidad SÓLO en la ventana ACTIVA (donde el FND aún es > ~1%): incluir la
        # cola de ceros dilingiría la diferencia. Para negocio anual son ~12 meses; para
        # Vida (multianual) la ventana se extiende sola porque su FND sigue > 0.
        activo = np.maximum(va, ca_full) >= 0.01
        if activo.sum() >= 1:
            dif_media = float(np.mean(np.abs(va[activo] - ca_full[activo])))
            dif_max = float(np.max(np.abs(va[activo] - ca_full[activo])))
        else:
            dif_media = dif_max = 0.0
        material = dif_media >= cfg.UMBRAL_MATERIAL
        votos = sum(1 for r in resultados if r.get(ramo, {}).get("abrir"))
        persistente = votos >= cfg.MIN_PARTICIONES
        b = base.get(ramo, {})
        dec[ramo] = dict(
            abrir=bool(material and persistente),
            material=material, dif_media=dif_media, dif_max=dif_max,
            votos=votos, n_particiones=len(resultados),
            err_propio=b.get("err_propio", np.nan), err_cartera=b.get("err_cartera", np.nan),
            mejora=b.get("mejora", 0.0), peso=pesos.get(ramo, 0.0), reserva=b.get("reserva", 0.0))
    return dec


# =============================================================================
# M4 · FRECUENCIA — escenarios por periodicidad de cuentas
# =============================================================================
def m4_escenario_frecuencia(vec, meses_cuenta: int, cfg: ConfigMEC = ConfigMEC()) -> np.ndarray:
    """FND_t(k) = max(0, FND_mensual(k) - (t-1)/2 * 30/365).

    Con cuentas de t meses la prima llega agrupada, así que al registrarla ya
    corrió en promedio (t-1)/2 meses de riesgo. Regla verificada EXACTA contra los
    vectores oficiales NT (diferencia 0.000000) en trimestral (30 días),
    cuatrimestral (45), semestral (75) y anual (165)."""
    desp = (meses_cuenta - 1) / 2 * cfg.DIAS_MES / cfg.DIAS_ANIO
    return np.maximum(0.0, np.asarray(vec, dtype=float) - desp)


# =============================================================================
# M5 · EXPOSICIÓN — curva no lineal dentro de la vigencia (PENDIENTE)
# =============================================================================
def m5_curva_exposicion(*args, **kwargs):
    """PENDIENTE — requiere FECHA DE OCURRENCIA de siniestros (SIREC).

    La prorrata supone riesgo uniforme a lo largo de la vigencia. Es razonable
    para la mayoría de los ramos, pero NO para Agrícola (ciclo de cosecha) ni para
    los expuestos a temporada. Sustituir la recta por una curva exige saber CUÁNDO
    ocurre el siniestro dentro de la vigencia.

    Se intentó estimar con los siniestros de la BD y NO es viable: traen el mismo
    rezago de registro (0% en los meses 0-2 de todos los ramos, lo cual es
    imposible). La fecha de ocurrencia está en SIREC, no en la BD del presupuesto.

    Mientras tanto Agrícola opera con el vector de cartera; NO se inventa una curva.
    """
    raise NotImplementedError(
        "Curva de exposición pendiente: requiere fecha de ocurrencia de siniestros "
        "(SIREC). No se estima con los siniestros de la BD porque traen rezago de registro."
    )


# =============================================================================
# M6 · PUBLICACIÓN — TablaFND + API de integración
# =============================================================================
def _int_o_none(v):
    try:
        return int(float(v))
    except Exception:
        return None


def fnd_exacto(inivig, finvig, calmonth, cfg: ConfigMEC = ConfigMEC()):
    """FND EXACTO de un registro: fracción de SU vigencia no expirada al cierre del
    mes contable. No usa vectores ni promedios, así que no arrastra error de mezcla.

    Se midió sobre la cartera real que aproximar con un vector por ramo x antiguedad
    deja un sesgo del orden de 5% en la reserva, mientras que esta vía es exacta.
    Devuelve None si falta alguna fecha (entonces se cae al vector)."""
    ini = _a_fecha_libre(inivig)
    fin = _a_fecha_libre(finvig)
    if ini is None or fin is None:
        return None
    try:
        cal = int(calmonth)
    except Exception:
        return None
    corte = pd.Timestamp(year=cal // 100, month=cal % 100, day=1) + pd.offsets.MonthEnd(0)
    dur = (fin - ini).days
    if dur <= 0:
        return None
    return float(np.clip((fin - corte).days / dur, 0.0, 1.0))


def _a_fecha_libre(v):
    """Convierte a fecha lo mismo un serial de Excel que un datetime o texto."""
    if v is None:
        return None
    try:
        if isinstance(v, (int, float, np.integer, np.floating)):
            if not np.isfinite(float(v)) or float(v) <= 0:
                return None
            return EPOCH_EXCEL + pd.Timedelta(days=float(v))
        ts = pd.Timestamp(v)
        return None if pd.isna(ts) else ts
    except Exception:
        return None


class TablaFND:
    """Tabla publicada del FND por ramo × antigüedad, con FALLBACK garantizado al
    valor legado (xPND) cuando falte información. Si la tabla está inactiva, los
    scripts se comportan EXACTAMENTE como hoy."""

    def __init__(self, tabla: dict, cartera, cfg: ConfigMEC, decisiones: dict | None = None):
        self.tabla = tabla
        self.cartera = cartera
        self.cfg = cfg
        self.decisiones = decisiones or {}
        self.activa = bool(tabla) and cartera is not None

    def _a_fecha(self, v):
        if v is None:
            return None
        try:
            if isinstance(v, (int, float, np.integer, np.floating)):
                return EPOCH_EXCEL + pd.Timedelta(days=float(v))
            ts = pd.Timestamp(v)
            return None if pd.isna(ts) else ts
        except Exception:
            return None

    def antiguedad_de_row(self, row) -> int | None:
        """Antigüedad = meses entre el inicio de vigencia y el mes contable."""
        cfg = self.cfg
        try:
            cal = int(row[cfg.COL_CALMONTH])
        except Exception:
            return None
        iv = self._a_fecha(row[cfg.COL_INIVIG]) if cfg.COL_INIVIG in getattr(row, "index", row) else None
        if iv is None:
            return None
        a = (cal // 100 - iv.year) * 12 + (cal % 100 - iv.month)
        return a if a >= 0 else None

    def factor(self, ramo, antiguedad, frecuencia=None, fallback=0.0) -> float:
        if not self.activa or antiguedad is None:
            return fallback
        vec = self.tabla.get(str(ramo))
        if vec is None:
            ri = _int_o_none(ramo)
            vec = self.tabla.get(str(ri)) if ri is not None else None
        if vec is None:
            vec = self.cartera                       # ramo sin vector propio -> cartera
        if vec is None:
            return fallback
        if frecuencia is not None:                   # escenario por periodicidad de cuentas
            t = self.cfg.FREC_MESES.get(_int_o_none(frecuencia))
            if t and t > 1:
                vec = m4_escenario_frecuencia(vec, t, self.cfg)
        k = int(antiguedad)
        if k < 0:
            return fallback
        return float(vec[-1]) if k >= len(vec) else float(vec[k])


def m6_publicar(vectores: dict, cartera, decisiones: dict,
                cfg: ConfigMEC = ConfigMEC()) -> TablaFND:
    """Publica el vector propio sólo a los ramos que abrieron; el resto, cartera."""
    tabla = {ramo: (v if decisiones.get(ramo, {}).get("abrir") else cartera)
             for ramo, v in vectores.items()}
    return TablaFND(tabla, cartera, cfg, decisiones)


# =============================================================================
# ORQUESTADOR
# =============================================================================
def construir(ruta_registros, cfg: ConfigMEC = ConfigMEC()) -> TablaFND:
    """Recorre los módulos y devuelve la TablaFND lista para consumir.
    Si no hay datos, devuelve una tabla inactiva (todo por fallback = xPND)."""
    df = m1_cargar_registros(ruta_registros, cfg)
    if df is None or df.empty:
        return TablaFND({}, None, cfg)
    vectores, cartera, pesos = m2_fnd_prorrata(df, cfg)
    if cartera is None:
        return TablaFND({}, None, cfg)
    decisiones = m3_decision_apertura(df, vectores, cartera, pesos, cfg)
    tabla = m6_publicar(vectores, cartera, decisiones, cfg)
    abiertos = sorted([r for r, d in decisiones.items() if d["abrir"]])
    print(f"[MEC] Tabla FND (prorrata exacta) · {len(vectores)} ramos · "
          f"abiertos con vector propio: {abiertos or 'ninguno'}")
    return tabla


# =============================================================================
# EXTRA · el triángulo de registro, en su lugar correcto (NO es el FND)
# =============================================================================
def extra_triangulo_registro(df_largo: pd.DataFrame) -> dict:
    """Triángulo de cohortes de prima REGISTRADA. Mide el rezago con que entra la
    prima a las cuentas, es decir cuánta prima de un periodo ya iniciado todavía no
    se ha reportado. Es información útil, pero afecta a PT (el monto), NO al FND.
    Se conserva para no perderla y para que la distinción quede explícita."""
    tri = {}
    for ramo, g in df_largo.groupby("Ramo"):
        tri[str(ramo)] = g.pivot_table(index="CohorteAAAAMM", columns="Antiguedad",
                                       values="PrimaDevAcum", aggfunc="sum").sort_index()
    return tri


# =============================================================================
# API DE INTEGRACIÓN — reemplaza la búsqueda en xPND dentro de los reforecast
# =============================================================================
def factor_no_devengado(tabla: TablaFND, row, fallback_value: float,
                        cfg: ConfigMEC = ConfigMEC()) -> float:
    """Para el RRC. El llamador pasa el VALOR LEGADO EXACTO en `fallback_value`
    (p. ej. xPND.get(...).get(...)), de modo que si la tabla no aplica, el
    comportamiento es idéntico al de hoy."""
    if not tabla.activa:
        return fallback_value
    try:
        ramo = row[cfg.COL_RAMO]
    except Exception:
        return fallback_value
    # 1) si el registro trae SUS DOS fechas de vigencia, el FND es exacto (sin vector)
    if cfg.USAR_EXACTO_SI_HAY_FECHAS:
        try:
            idx = getattr(row, "index", row)
            if cfg.COL_INIVIG in idx and cfg.COL_FINVIG in idx:
                v = fnd_exacto(row[cfg.COL_INIVIG], row[cfg.COL_FINVIG], row[cfg.COL_CALMONTH], cfg)
                if v is not None:
                    return v
        except Exception:
            pass
    # 2) si no, el vector del ramo (o el de cartera) por antigüedad
    antig = tabla.antiguedad_de_row(row)
    try:
        frec = row[cfg.COL_FREC]
    except Exception:
        frec = None
    return tabla.factor(ramo, antig, frecuencia=frec, fallback=fallback_value)


def valor_fnd_directo(tabla: TablaFND, ramo, mesproc, inivig, frecuencia,
                      fallback_value: float, cfg: ConfigMEC = ConfigMEC(),
                      finvig=None) -> float:
    """Para las funciones zFND* del SONR, que reciben valores sueltos.
    Si se pasa `finvig`, el FND se calcula EXACTO con las fechas del registro."""
    if not tabla.activa:
        return fallback_value
    if cfg.USAR_EXACTO_SI_HAY_FECHAS and finvig is not None:
        v = fnd_exacto(inivig, finvig, mesproc, cfg)
        if v is not None:
            return v
    try:
        cal = int(mesproc)
    except Exception:
        return fallback_value
    iv = tabla._a_fecha(inivig)
    if iv is None:
        return fallback_value
    antig = (cal // 100 - iv.year) * 12 + (cal % 100 - iv.month)
    return tabla.factor(ramo, antig, frecuencia=frecuencia, fallback=fallback_value)
