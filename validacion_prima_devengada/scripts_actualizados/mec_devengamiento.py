# -*- coding: utf-8 -*-
"""
================================================================================
 mec_devengamiento.py  ·  v3  ·  Método de Emergencia por Cohortes (MEC)
 FRAMEWORK MODULAR — SOLO PARA EL FACTOR DE NO DEVENGAMIENTO (FND)

 QUÉ CAMBIÓ EN LA v3 (validación contra la prima devengada REAL)
 ---------------------------------------------------------------
 Se validó la v2 contra la prima devengada real (prima emitida − ΔRRC bruta;
 prima retenida − ΔRRC neta, con los saldos de la base BEL-IRR-MR) y NO cuadra:
 reproducía el 22% de la RRC real y sobreestimaba la prima devengada entre 2.6% y
 8.4% al año. La causa está medida:

   · El 69% de la prima de Patria (79% del proporcional) se REGISTRA en un año
     calendario posterior al de su inicio de vigencia. La v2 le asigna el FND de su
     cohorte de vigencia, que ya es ~0 cuando la cuenta llega.
   · La RRC real devenga esa prima como riesgo NUEVO desde el mes de registro, con
     la recta de 24-avos de la Nota Técnica (misma lógica de xPND[CALMONTH]).
   · Verificado por ramo: con antigüedad de REGISTRO y δ=0, Incendio, Diversos, RC y
     MyT reproducen la RRC real (ratio 0.99–1.01, error medio mensual 2.4%–5.2%).

 Por eso el FND de PROPORCIONAL y FACULTATIVO (TipoRea 1 y 3) se indexa por
 ANTIGÜEDAD DE REGISTRO y su único parámetro por ramo es el desplazamiento δ de la
 regla M4 (frecuencia de cuentas):

       FND_ramo(k_reg) = min(1, max(0, NT(k_reg) − δ_ramo)),  k_reg = 0..11

 El NO PROPORCIONAL (TipoRea 2) conserva la prorrata exacta por fechas de vigencia
 (M2), que es donde esa regla sí describe al negocio.

 Ajuste logrado (202301–202605): RRC real reproducida con error medio mensual de
 3.1%; prima devengada anual con error de −2.3% (2023), +1.4% (2024), +0.7% (2025)
 y +1.2% (2026 ene–may), tanto tomada como retenida.

 ALCANCE (candado, sin cambios): esto sustituye SOLO la fuente del FND. FS/BELMEDIA,
 el desarrollo de siniestros (1−LAG), el margen de riesgo, el IRR y el índice se
 mantienen con el método vigente.

 --- Documentación de la v2 (la prorrata sigue vigente para el no proporcional) ---
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

    # --- v3: FND calibrado por antigüedad de REGISTRO (proporcional y facultativo) ---
    COL_TIPOREA = "TipoRea"       # 1 proporcional · 2 no proporcional · 3 facultativo
    USAR_CALIBRADO = True         # False -> comportamiento v2 (todo por cohorte de vigencia)
    ARCHIVO_DELTA = "delta_calibrado.json"   # opcional: recalibración sin tocar código

    # δ por ramo, ajustado por mínimos cuadrados contra la prima no devengada real
    # (base BEL-IRR-MR, 202301–202605; CAT desde 202401 por el índice TEV/Hidro).
    # δ es el desplazamiento de la regla M4: δ = (t−1)/2 · 30/365, t = meses de cuenta.
    DELTA_RAMO = {
        10: 0.070,    # Vida                       ~trimestral
        30: 0.045,    # Accidentes y Enfermedades  ~bimestral
        40: 0.000,    # Responsabilidad Civil      NT mensual
        50: -0.010,   # Marítimo y Transportes     NT mensual
        60: 0.000,    # Incendio                   NT mensual
        70: -0.035,   # Terremoto / Cat            ligeramente sobre NT mensual
        80: 0.095,    # Agrícola                   ~trimestral-cuatrimestral
        90: 0.130,    # Automóviles                ~cuatrimestral
        100: -0.085,  # Crédito                    sobre NT mensual (ramo de bajo peso)
        110: 0.000,   # Diversos                   NT mensual
    }
    # subramos del catálogo SIREC que caen en cada ramo de la tabla
    SUBRAMO_A_RAMO = {20: 10, 31: 30, 34: 30, 35: 30, 37: 30, 39: 30, 71: 70, 73: 70}


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
    # se acota a [0, 1]: un desplazamiento negativo (δ<0) no puede pasar del 100%
    return np.clip(np.asarray(vec, dtype=float) - desp, 0.0, 1.0)


# =============================================================================
# M4b · REGISTRO — FND calibrado por antigüedad de REGISTRO   <- LA BASE DE LA v3
# =============================================================================
# Recta de la Nota Técnica (24-avos) por antigüedad de registro k = 0..11, donde
# k = 0 es el propio mes en que la cuenta entra. Es la tabla xPND 'NA' de los
# reforecast, verificada contra los vectores oficiales NT.
NT_MENSUAL = np.array([0.95890411, 0.876712329, 0.791780822, 0.706849315,
                       0.624657534, 0.539726027, 0.457534247, 0.37260274,
                       0.295890411, 0.210958904, 0.126027397, 0.043835616])


def cargar_delta(ruta_o_dir, cfg: ConfigMEC = ConfigMEC()) -> dict:
    """Lee δ por ramo del JSON de la recalibración (validar_prima_devengada.py).
    Si no existe, devuelve el δ de ConfigMEC. Así una recalibración trimestral no
    exige tocar código: se sustituye el JSON y se vuelve a correr."""
    import json
    ruta = ruta_o_dir
    if os.path.isdir(str(ruta_o_dir)):
        ruta = os.path.join(ruta_o_dir, cfg.ARCHIVO_DELTA)
    if not os.path.exists(str(ruta)):
        return dict(cfg.DELTA_RAMO)
    GRUPO = {"Vida": 10, "AyE": 30, "RC": 40, "MyT": 50, "Incendio": 60,
             "CAT": 70, "Agro": 80, "Autos": 90, "Credito": 100, "Diversos": 110}
    with open(ruta, encoding="utf-8") as f:
        d = json.load(f)
    out = dict(cfg.DELTA_RAMO)
    for k, v in d.items():
        r = GRUPO.get(k, _int_o_none(k))
        if r is not None:
            out[int(r)] = float(v)
    return out


def ramo_de_tabla(ramo, cfg: ConfigMEC = ConfigMEC()):
    """Colapsa el subramo del catálogo al ramo de la tabla de δ (31->30, 71->70…)."""
    r = _int_o_none(ramo)
    return None if r is None else cfg.SUBRAMO_A_RAMO.get(r, r)


def antiguedad_registro(mes_valuacion, mes_registro) -> int | None:
    """k_reg = meses entre el mes CONTABLE DE REGISTRO de la cuenta y el mes de
    VALUACIÓN. Ojo: en los reforecast el mes de registro es CALMONTH
    (aPog_MesProc) y el de valuación es la variable `Meses`; no son lo mismo."""
    try:
        a, b = int(mes_valuacion), int(mes_registro)
    except Exception:
        return None
    return (a // 100 - b // 100) * 12 + (a % 100 - b % 100)


def vector_registro(ramo, delta: dict | None = None, horizonte: int = 24,
                    cfg: ConfigMEC = ConfigMEC()) -> np.ndarray:
    """Vector FND del ramo por antigüedad de registro, con cola en CERO."""
    d = (delta or cfg.DELTA_RAMO).get(ramo_de_tabla(ramo, cfg), 0.0)
    v = np.zeros(int(horizonte))
    v[:12] = np.clip(NT_MENSUAL - d, 0.0, 1.0)
    return v


def fnd_registro(ramo, k_reg, delta: dict | None = None,
                 cfg: ConfigMEC = ConfigMEC()) -> float:
    """FND de una cuenta proporcional/facultativa registrada hace k_reg meses."""
    if k_reg is None or k_reg < 0 or k_reg >= 12:
        return 0.0
    d = (delta or cfg.DELTA_RAMO).get(ramo_de_tabla(ramo, cfg), 0.0)
    return float(np.clip(NT_MENSUAL[int(k_reg)] - d, 0.0, 1.0))


def tabla_registro(delta: dict | None = None, horizonte: int = 12,
                   cfg: ConfigMEC = ConfigMEC()) -> pd.DataFrame:
    """Tabla publicable ramo × antigüedad de registro (el objeto que consume RRC)."""
    d = delta or cfg.DELTA_RAMO
    t = pd.DataFrame({r: vector_registro(r, d, horizonte, cfg) for r in sorted(d)}).T
    t.columns = [f"k={k}" for k in range(int(horizonte))]
    t.index.name = "Ramo"
    return t


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


def fnd_exacto(inivig, finvig, mes_valuacion, cfg: ConfigMEC = ConfigMEC()):
    """FND EXACTO de un registro: fracción de SU vigencia no expirada al cierre del
    MES DE VALUACIÓN. No usa vectores ni promedios, así que no arrastra error de
    mezcla. Es la regla del no proporcional (TipoRea 2).

    OJO (corregido en v3): el corte es el mes de VALUACIÓN, no el CALMONTH del
    registro. En los reforecast CALMONTH es el mes contable en que entró la cuenta
    (aPog_MesProc); pasarlo como corte hace que cada registro se valúe en su propio
    mes y no en la fecha de valuación.

    Devuelve None si falta alguna fecha (entonces se cae al vector)."""
    ini = _a_fecha_libre(inivig)
    fin = _a_fecha_libre(finvig)
    if ini is None or fin is None:
        return None
    try:
        cal = int(mes_valuacion)
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

    def antiguedad_de_row(self, row, mes_valuacion=None) -> int | None:
        """Antigüedad de COHORTE = meses entre el inicio de vigencia y el mes de
        valuación (si no se pasa, el mes contable del registro, como en la v2)."""
        cfg = self.cfg
        try:
            cal = int(mes_valuacion if mes_valuacion is not None else row[cfg.COL_CALMONTH])
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
        # cola en CERO (v3): antes devolvía vec[-1], que dejaba un FND residual
        # permanente (4.3% en Vida con horizonte 24) para antigüedades muy altas.
        return 0.0 if k >= len(vec) else float(vec[k])


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
                        cfg: ConfigMEC = ConfigMEC(), mes_valuacion=None,
                        fecha_valuacion=None, delta: dict | None = None) -> float:
    """Para el RRC. Sustituye la búsqueda en xPND dentro de ConsultaReal*.

    Jerarquía (v3):
      1. NO PROPORCIONAL (TipoRea 2) con sus dos fechas -> prorrata EXACTA al mes de
         valuación. Es la regla que la RRC real aplica a ese negocio.
      2. PROPORCIONAL y FACULTATIVO (TipoRea 1 y 3) -> tabla calibrada por
         ANTIGÜEDAD DE REGISTRO (mes de valuación − CALMONTH) con δ del ramo.
      3. Si falta información -> `fallback_value`, el valor legado EXACTO que pasa el
         llamador (p. ej. xPND.get(...).get(...)), así el comportamiento no cambia.

    `mes_valuacion` es AAAAMM de la valuación (variable `Meses` del reforecast). Si no
    se pasa, se cae al CALMONTH del registro y el resultado es el de la v2.
    """
    try:
        ramo = row[cfg.COL_RAMO]
    except Exception:
        return fallback_value
    idx = getattr(row, "index", row)
    mv = mes_valuacion if mes_valuacion is not None else (
        row[cfg.COL_CALMONTH] if cfg.COL_CALMONTH in idx else None)

    tipo = _int_o_none(row[cfg.COL_TIPOREA]) if cfg.COL_TIPOREA in idx else None

    # 1) no proporcional: prorrata exacta por fechas de vigencia
    if cfg.USAR_EXACTO_SI_HAY_FECHAS and tipo == 2:
        try:
            if cfg.COL_INIVIG in idx and cfg.COL_FINVIG in idx:
                v = fnd_exacto(row[cfg.COL_INIVIG], row[cfg.COL_FINVIG], mv, cfg)
                if v is not None:
                    return v
        except Exception:
            pass

    # 2) proporcional / facultativo: tabla calibrada por antigüedad de REGISTRO
    if cfg.USAR_CALIBRADO and tipo != 2 and cfg.COL_CALMONTH in idx:
        k = antiguedad_registro(mv, row[cfg.COL_CALMONTH])
        if k is not None:
            return 0.0 if k < 0 else fnd_registro(ramo, k, delta, cfg)

    # 3) legado v2: vector del ramo (o de cartera) por antigüedad de cohorte
    if not tabla.activa:
        return fallback_value
    antig = tabla.antiguedad_de_row(row, mes_valuacion=mv)
    try:
        frec = row[cfg.COL_FREC]
    except Exception:
        frec = None
    return tabla.factor(ramo, antig, frecuencia=frec, fallback=fallback_value)


def valor_fnd_directo(tabla: TablaFND, ramo, mesproc, inivig, frecuencia,
                      fallback_value: float, cfg: ConfigMEC = ConfigMEC(),
                      finvig=None, tiporea=None, mes_valuacion=None,
                      delta: dict | None = None) -> float:
    """Para las funciones zFND* del SONR, que reciben valores sueltos.

    `mesproc`        = mes contable de REGISTRO de la cuenta (CALMONTH)
    `mes_valuacion`  = AAAAMM de la valuación (si falta, se usa `mesproc`, = v2)
    `tiporea`        = 2 -> prorrata exacta por fechas; 1 y 3 -> tabla calibrada
    """
    mv = mes_valuacion if mes_valuacion is not None else mesproc

    # 1) no proporcional con fechas: prorrata exacta al mes de valuación
    if cfg.USAR_EXACTO_SI_HAY_FECHAS and finvig is not None and (
            tiporea is None or _int_o_none(tiporea) == 2):
        v = fnd_exacto(inivig, finvig, mv, cfg)
        if v is not None:
            return v

    # 2) proporcional / facultativo: antigüedad de REGISTRO
    if cfg.USAR_CALIBRADO and _int_o_none(tiporea) != 2:
        k = antiguedad_registro(mv, mesproc)
        if k is not None:
            return 0.0 if k < 0 else fnd_registro(ramo, k, delta, cfg)

    # 3) legado v2
    if not tabla.activa:
        return fallback_value
    try:
        cal = int(mv)
    except Exception:
        return fallback_value
    iv = tabla._a_fecha(inivig)
    if iv is None:
        return fallback_value
    antig = (cal // 100 - iv.year) * 12 + (cal % 100 - iv.month)
    return tabla.factor(ramo, antig, frecuencia=frecuencia, fallback=fallback_value)
