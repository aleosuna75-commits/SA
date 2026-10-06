# -*- coding: utf-8 -*-
"""Insumos para los scripts de valuacion del area (RRC y SONR) tomados de la BD proyectada.

Lee ``BD_ BEL - IRR - MR_Proyeccion.xlsx`` (la salida de ``proyeccion_reservas.py``) y arma, con la forma que
esperan los scripts del area, las tablas que antes venian de CSV o de constantes:

================================  ==========================================================================
Insumo del script                 De donde sale en la BD
================================  ==========================================================================
ParametrosMens (RRC)              HParametros: Ind Sin RRC / Ind sin RRC 99.5% (``Real`` hasta el ultimo mes real
                                  y ``Proyección`` despues; en los ramos de RAMOS_IS_FA, el IS (FA) de la hoja
                                  IS_FA en los meses proyectados) y el bloque FACTOR GTO de la hoja de montos como
                                  Ind. Gasto, los dos por mes (``-1`` a ``-12``). Duracion y retencion para el MR
                                  (Pesos_dur, Resto Monedas_dur, Pesos_ret, Resto Monedas_ret) no estan en la BD:
                                  se toman del CSV del area si se indica.
IS_Cat (RRC, ramos 71 y 73)        Ind Sin RRC de TEV e Hidro por mes (Real / Proyección).
ParamSONR (SONR)                   HParametros: Ind Sin SONR Media / 99.5% y LAG 1 a LAG 10 por mes y ramo (con el
                                  IS (FA) en los ramos de RAMOS_IS_FA en los meses proyectados) y Factor_Ret =
                                  1 - IRR / BEL de SONR de la hoja de montos (en los meses proyectados, con la
                                  CESION y el FACTOR MR proyectados).
FACTOR MR (RRC y SONR)             Bloque FACTOR MR de la hoja de montos (MR / PND o PD) por mes y ramo: el MR de los
                                  scripts es PND del contrato x FACTOR MR (config MR_DESDE = "BD").
Tipo de cambio USD                 Columna TC de la hoja de montos (real hasta el ultimo mes y pronostico despues).
Escenario base (0)                 Montos reales de diciembre del ano anterior de la hoja de montos.
Saldos proyectados                 Montos proyectados de la hoja de montos (BEL por FND y sus derivados).
================================  ==========================================================================

Los montos y factores proyectados de la hoja de montos son formulas: se leen de los valores que Excel guardo
(abrir y guardar la BD en Excel) y, si no los hay, del ``Diagnostico_Proyeccion.xlsx`` de la misma corrida.
Las claves de ramo son las de los scripts (10, 31, 35, 39, 40, 50, 60, 71, 73, 80, 90, 100, 110).
"""
from __future__ import annotations

import math
import re
import warnings
from pathlib import Path

import openpyxl
import pandas as pd

HOJA_MONTOS = "BD_Montos_RRC_SONR"
HOJA_IS_FA = "IS_FA"
HOJA_DIAG_INDICADORES = "Indicadores_Ramo"
HOJA_DIAG_MONTOS = "Montos_Proyectados"
RAMOS_SCRIPT = [10, 31, 35, 39, 40, 50, 60, 71, 73, 80, 90, 100, 110]
RAMOS_SONR = [10, 31, 35, 39, 40, 50, 60, 80, 90, 100, 110]          # 71 y 73 no tienen parametros de SONR
ETIQUETA_HP = {71: ("TEV", "Tev"), 73: ("Hidro",)}                     # clave del script -> etiqueta en HParametros
RAMO_BD = {31: "30", 35: "34", 39: "37"}                               # clave del script -> columna RAM_ de la BD
RAMOS_IS_FA = {"RRC": (40, 50, 80, 90), "SONR": (40, 50, 80, 90)}      # mismos ramos que el BEL por FND de la BD
PARAMETROS_HP = {"IS_RRC": "Ind Sin RRC", "IS_RRC_99": "Ind sin RRC 99.5%",
                 "IS_SONR": "Ind Sin SONR Media", "IS_SONR_99": "Ind Sin SONR 99.5%"}
LAGS = [f"LAG {k}" for k in range(1, 11)]
SIGNO = {"RRC": {"BEL": -1, "BELG": -1, "IRR": -1, "MR": -1, "BRUTO": 1, "NETO": 1},   # convencion de la salida del
         "SONR": {"BEL": 1, "IRR": 1, "MR": 1, "BRUTO": 1, "NETO": 1}}                 # area (RRC_esc / SONR_esc)
CONCEPTO_BD = {"BELG": "GTO"}                                          # tipo de monto del area -> concepto de la BD
COLUMNAS_ESC = ["Reserva", "Escenario", "Tipo de Monto", "Ramo", "Periodo", "Monto_MXN", "Monto_USD", "TC"]
UMBRAL_CERO = 1.0                                                      # USD: debajo, el monto cuenta como cero


def norm(t) -> str:
    return re.sub(r"\s+", " ", str(t or "").replace("\xa0", " ")).strip().upper()


def mes_mas(periodo: int, k: int) -> int:
    """Periodo AAAAMM mas k meses (k puede ser negativo)."""
    i = (periodo // 100) * 12 + (periodo % 100 - 1) + k
    return (i // 12) * 100 + i % 12 + 1


def rango_meses(p0: int, p1: int) -> list[int]:
    out, p = [], p0
    while p <= p1:
        out.append(p)
        p = mes_mas(p, 1)
    return out


def _num(v):
    if isinstance(v, bool) or v is None:
        return math.nan
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(float(v)) else math.nan
    t = str(v).strip().replace("\xa0", "").replace(" ", "").replace(",", "")
    try:
        return float(t)
    except ValueError:
        return math.nan


def _interpolar(valores: dict, periodos: list[int], huecos_reg: list, etiqueta: str) -> dict:
    """Serie mensual sobre periodos: huecos interiores interpolados linealmente, orillas con el vecino mas cercano.
    Los huecos se anotan en huecos_reg como (etiqueta, primer mes, ultimo mes, n)."""
    xs = [valores.get(p, math.nan) for p in periodos]
    n = len(xs)
    idx = [i for i, x in enumerate(xs) if not math.isnan(x)]
    if not idx:
        return {p: math.nan for p in periodos}
    out = list(xs)
    huecos = []
    for i in range(n):
        if math.isnan(out[i]):
            huecos.append(periodos[i])
            ant = max((j for j in idx if j < i), default=None)
            sig = min((j for j in idx if j > i), default=None)
            if ant is not None and sig is not None:
                out[i] = xs[ant] + (xs[sig] - xs[ant]) * (i - ant) / (sig - ant)
            else:
                out[i] = xs[ant if ant is not None else sig]
    if huecos:
        huecos_reg.append((etiqueta, huecos[0], huecos[-1], len(huecos)))
    return dict(zip(periodos, out))


class InsumosBD:
    """Lee la BD proyectada y entrega los insumos de los scripts del area."""

    def __init__(self, ruta_bd, ruta_diagnostico=None, usar_is_fa: bool = True, ramos_is_fa: dict | None = None,
                 tipo_real: str = "Real", tipo_proyeccion: str = "Proyección", verbose: bool = True):
        self.ruta_bd = Path(ruta_bd)
        if not self.ruta_bd.exists():
            raise FileNotFoundError(f"No esta la BD proyectada: {self.ruta_bd}")
        self.ruta_diagnostico = Path(ruta_diagnostico) if ruta_diagnostico else self.ruta_bd.with_name("Diagnostico_Proyeccion.xlsx")
        self.usar_is_fa = usar_is_fa
        self.ramos_is_fa = ramos_is_fa if ramos_is_fa is not None else RAMOS_IS_FA
        self.tipo_real, self.tipo_proyeccion = norm(tipo_real), norm(tipo_proyeccion)
        self.avisos: list[str] = []
        self._huecos: list[tuple] = []          # (etiqueta, desde, hasta, n) de los meses llenados con los vecinos
        self._series: dict = {}
        self._diag: dict | None = None
        wb = openpyxl.load_workbook(self.ruta_bd, read_only=True, data_only=True)
        try:
            self.hoja_hp = next((n for n in wb.sheetnames if norm(n).startswith("HPARAMETROS")), None)
            if self.hoja_hp is None or HOJA_MONTOS not in wb.sheetnames:
                raise ValueError(f"La BD debe traer las hojas HParametros_* y {HOJA_MONTOS}; trae {wb.sheetnames}")
            self._leer_hp(wb[self.hoja_hp])
            self._leer_montos(wb[HOJA_MONTOS])
            self._leer_is_fa(wb[HOJA_IS_FA] if HOJA_IS_FA in wb.sheetnames else None)
        finally:
            wb.close()
        self.anio, self.mes = self.ultimo_real // 100, self.ultimo_real % 100
        self._validar_valores()
        if verbose:
            for linea in self.resumen():
                print("   " + linea, flush=True)

    def _validar_valores(self):
        """Comprueba al inicio que los montos proyectados (formulas) tengan valor guardado o diagnostico, para no fallar a
        media corrida: prueba BEL, IRR y MR de RRC y SONR del primer y ultimo mes proyectado en todos los ramos."""
        if self.primer_proyectado is None:
            return
        for p in (self.primer_proyectado, self.ultimo_proyectado):
            if p not in self.periodos_con_montos:
                continue
            for reserva in ("RRC", "SONR"):
                for conc in ("BEL", "IRR", "MR"):
                    for clave in RAMOS_SCRIPT:
                        if (norm(f"{reserva} {conc}"), p, self.ramo_bd(clave)) in self.montos:
                            self.monto(f"{reserva} {conc}", p, clave)       # (levanta ValueError con el mensaje claro)
        if self._diag and (self._diag["montos"] or self._diag["ind"]):
            self.avisos.append(f"los montos y factores proyectados se leyeron de {self.ruta_diagnostico.name} (la BD no "
                               "trae los valores guardados de las formulas)")

    # ------------------------------------------------------------------ lectura
    @staticmethod
    def _encabezado(ws, marcas: tuple, max_filas: int = 12):
        for i, fila in enumerate(ws.iter_rows(min_row=1, max_row=max_filas, values_only=True), 1):
            nombres = [norm(x) for x in fila]
            if all(norm(m) in nombres for m in marcas):
                return i, {norm(x): j for j, x in enumerate(fila) if x is not None}
        raise ValueError(f"No se encontro el encabezado con {marcas} en la hoja {ws.title}")

    @staticmethod
    def _clave_ramo(v) -> int | None:
        t = str(v).strip() if v is not None else ""
        if t.isdigit():
            return int(t)
        for clave, etiquetas in ETIQUETA_HP.items():
            if norm(t) in {norm(e) for e in etiquetas}:
                return clave
        return None

    def _leer_hp(self, ws):
        fila, col = self._encabezado(ws, ("Tipo de Indice", "Fecha", "Ramo", "LAG 1"))
        c_tipo, c_fecha, c_ramo = col[norm("Tipo de Indice")], col[norm("Fecha")], col[norm("Ramo")]
        c_par = {k: col.get(norm(n)) for k, n in PARAMETROS_HP.items()}
        c_lag = {k: col.get(norm(k)) for k in LAGS}
        faltan = [n for k, n in PARAMETROS_HP.items() if c_par[k] is None] + [k for k in LAGS if c_lag[k] is None]
        if faltan:
            raise ValueError(f"En {ws.title} faltan las columnas {faltan}")
        self.hp: dict = {}                       # (tipo, periodo, clave) -> {param: valor}
        self.tipos: dict = {}
        for r in ws.iter_rows(min_row=fila + 1, values_only=True):
            tipo = norm(r[c_tipo]) if c_tipo < len(r) else ""
            if not tipo:
                continue
            periodo = _num(r[c_fecha]) if c_fecha < len(r) else math.nan
            clave = self._clave_ramo(r[c_ramo]) if c_ramo < len(r) else None
            if math.isnan(periodo) or clave is None:
                continue
            periodo = int(periodo)
            d = {k: _num(r[c]) if c < len(r) else math.nan for k, c in c_par.items()}
            lags = [_num(r[c]) if c < len(r) else math.nan for c in c_lag.values()]
            max_previo = 0.0                       # (como el modelo principal) un LAG en 0 despues de que el patron
            for k, v in enumerate(lags):           # acumulado supero 50 % es marcador de faltante, en toda la corrida
                if not math.isnan(v) and v == 0 and (k == 0 or max_previo > 0.5):
                    lags[k] = math.nan
                elif not math.isnan(v):
                    max_previo = max(max_previo, v)
            d.update(dict(zip(LAGS, lags)))
            self.hp[(tipo, periodo, clave)] = d
            self.tipos.setdefault(tipo, set()).add(periodo)
        if self.tipo_real not in self.tipos:
            raise ValueError(f"{ws.title} no trae renglones '{self.tipo_real}'; tipos: {sorted(self.tipos)}")
        reales = self.tipos[self.tipo_real]
        proy = self.tipos.get(self.tipo_proyeccion, set())
        self.ultimo_real = mes_mas(min(proy), -1) if proy else max(reales)
        self.primer_proyectado = min(proy) if proy else None
        self.ultimo_proyectado = max(proy) if proy else None
        self.primer_periodo_hp = min(reales)

    def _leer_montos(self, ws):
        fila, col = self._encabezado(ws, ("CONCEPTO", "PERIODO", "TC"))
        self.col_ramo_bd = {h[4:]: c for h, c in col.items() if h.startswith("RAM_")}
        self.col_bloque = {}                     # (nombre, ramo_bd) -> columna
        for h, c in col.items():
            m = re.match(r"^(.*\S)\s+(\d+)$", h)
            if m and not h.startswith("RAM_") and m.group(2) in self.col_ramo_bd:
                self.col_bloque[(m.group(1), m.group(2))] = c
        c_con, c_per, c_tc = col["CONCEPTO"], col["PERIODO"], col["TC"]
        self.montos: dict = {}                   # (concepto, periodo, ramo_bd) -> valor o None
        self.bloques: dict = {}                  # (nombre, reserva, periodo, ramo_bd) -> valor o None
        self.tc: dict = {}
        self.periodos_montos: set = set()
        self.periodos_con_montos: set = set()    # meses con algun monto (los de prima sin montos quedan fuera)
        for r in ws.iter_rows(min_row=fila + 1, values_only=True):
            concepto = norm(r[c_con]) if c_con < len(r) else ""
            periodo = _num(r[c_per]) if c_per < len(r) else math.nan
            if not concepto or math.isnan(periodo):
                continue
            periodo = int(periodo)
            self.periodos_montos.add(periodo)
            tc = _num(r[c_tc]) if c_tc < len(r) else math.nan
            if not math.isnan(tc) and tc > 0:
                self.tc.setdefault(periodo, tc)
            for ramo_bd, c in self.col_ramo_bd.items():
                v = r[c] if c < len(r) else None
                self.montos[(concepto, periodo, ramo_bd)] = v
                if v is not None and v != "":
                    self.periodos_con_montos.add(periodo)
            if concepto in ("RRC BEL", "SONR BEL"):
                reserva = concepto.split()[0]
                for (nombre, ramo_bd), c in self.col_bloque.items():
                    self.bloques[(nombre, reserva, periodo, ramo_bd)] = r[c] if c < len(r) else None
        if not self.tc:
            raise ValueError(f"La columna TC de {ws.title} esta vacia")
        if self.periodos_con_montos:               # la historia y la proyeccion son contiguas: desde el primer mes con monto
            primero = min(self.periodos_con_montos)
            self.periodos_con_montos = {p for p in self.periodos_montos if p >= primero}

    def _leer_is_fa(self, ws):
        self.is_fa: dict = {}                    # (reserva, clave, periodo) -> {"media": v, "99.5": v}
        if ws is None:
            self.avisos.append(f"la BD no trae la hoja {HOJA_IS_FA}: el IS (FA) no se usa")
            return
        try:
            fila, col = self._encabezado(ws, ("Ramo", "MesProc", "IS RRC", "IS SONR"))
        except ValueError:
            self.avisos.append(f"la hoja {HOJA_IS_FA} no trae Ramo, MesProc, IS RRC e IS SONR: el IS (FA) no se usa")
            return
        c = {k: col.get(norm(k)) for k in ("Ramo", "MesProc", "IS RRC", "IS SONR", "IS RRC 99.5%", "IS SONR 99.5%")}
        for r in ws.iter_rows(min_row=fila + 1, values_only=True):
            clave = self._clave_ramo(r[c["Ramo"]]) if c["Ramo"] < len(r) else None
            periodo = _num(r[c["MesProc"]]) if c["MesProc"] < len(r) else math.nan
            if clave is None or math.isnan(periodo):
                continue
            periodo = int(periodo)
            for reserva, k_m, k_99 in (("RRC", "IS RRC", "IS RRC 99.5%"), ("SONR", "IS SONR", "IS SONR 99.5%")):
                media = _num(r[c[k_m]]) if c[k_m] is not None and c[k_m] < len(r) else math.nan
                p99 = _num(r[c[k_99]]) if c[k_99] is not None and c[k_99] < len(r) else math.nan
                if not math.isnan(media):
                    self.is_fa.setdefault((reserva, clave, periodo), {"media": media, "99.5": p99})   # primer renglon
        if not self.is_fa:
            self.avisos.append(f"la hoja {HOJA_IS_FA} no trae indices: el IS (FA) no se usa")

    def _cargar_diag(self):
        if self._diag is not None:
            return self._diag
        self._diag = {"ind": {}, "montos": {}}
        if not self.ruta_diagnostico.exists():
            return self._diag
        wb = openpyxl.load_workbook(self.ruta_diagnostico, read_only=True, data_only=True)
        try:
            if HOJA_DIAG_INDICADORES in wb.sheetnames:
                filas = wb[HOJA_DIAG_INDICADORES].iter_rows(values_only=True)
                enc = [str(h) if h is not None else "" for h in next(filas)]
                for f in filas:
                    d = dict(zip(enc, f))
                    if d.get("Reserva") in ("RRC", "SONR") and d.get("Periodo"):
                        self._diag["ind"][(d["Reserva"], str(d["Ramo"]), int(d["Periodo"]))] = d
            if HOJA_DIAG_MONTOS in wb.sheetnames:
                filas = wb[HOJA_DIAG_MONTOS].iter_rows(values_only=True)
                next(filas)
                for libro, concepto, periodo, ramo, valor in filas:
                    if libro == "DANOS" and periodo:
                        self._diag["montos"][(norm(concepto), int(periodo), str(ramo))] = valor
        finally:
            wb.close()
        return self._diag

    # ------------------------------------------------------------------ parametros de HParametros
    @staticmethod
    def ramo_bd(clave: int) -> str:
        return RAMO_BD.get(clave, str(clave))

    def _tipo_de(self, periodo: int) -> str:
        return self.tipo_real if periodo <= self.ultimo_real else self.tipo_proyeccion

    def serie_cruda(self, param: str, clave: int) -> dict:
        """Serie mensual del parametro sin llenar huecos: {periodo: valor o nan} (Real hasta el ultimo mes real,
        Proyección despues)."""
        fin = self.ultimo_proyectado or self.ultimo_real
        periodos = rango_meses(self.primer_periodo_hp, fin)
        return {p: self.hp.get((self._tipo_de(p), p, clave), {}).get(param, math.nan) for p in periodos}

    def serie(self, param: str, clave: int) -> dict:
        """Serie mensual del parametro (IS_RRC, IS_RRC_99, IS_SONR, IS_SONR_99 o 'LAG k') para el ramo, Real hasta el
        ultimo mes real y Proyección despues, con los huecos llenados; {periodo: valor} (nan si el ramo no lo trae)."""
        k = (param, clave)
        if k not in self._series:
            fin = self.ultimo_proyectado or self.ultimo_real
            periodos = rango_meses(self.primer_periodo_hp, fin)
            crudo = {p: self.hp.get((self._tipo_de(p), p, clave), {}).get(param, math.nan) for p in periodos}
            self._series[k] = _interpolar(crudo, periodos, self._huecos, f"{param} ramo {clave}")
        return self._series[k]

    def parametro(self, param: str, clave: int, periodo: int) -> float:
        s = self.serie(param, clave)
        if periodo in s:
            return s[periodo]
        if not s:
            return math.nan
        return s[min(s)] if periodo < min(s) else s[max(s)]      # fuera del rango: el extremo mas cercano

    def indice(self, reserva: str, clave: int, periodo: int, cual: str = "media") -> float:
        """IS media o 99.5 de la reserva para el ramo y mes: el IS (FA) en los ramos de RAMOS_IS_FA en los meses
        proyectados (si lo trae), si no el de HParametros."""
        if self.usar_is_fa and periodo > self.ultimo_real and clave in self.ramos_is_fa.get(reserva, ()):
            fa = self.is_fa.get((reserva, clave, periodo))
            if fa and not math.isnan(fa.get(cual, math.nan)):
                return fa[cual]
        base = "IS_RRC" if reserva == "RRC" else "IS_SONR"
        return self.parametro(base if cual == "media" else base + "_99", clave, periodo)

    def fuente_indice(self, reserva: str, clave: int, periodo: int) -> str:
        if self.usar_is_fa and periodo > self.ultimo_real and clave in self.ramos_is_fa.get(reserva, ()) \
                and (reserva, clave, periodo) in self.is_fa:
            return "IS (FA)"
        return self._tipo_de(periodo)

    # ------------------------------------------------------------------ valores de la hoja de montos
    def monto(self, concepto: str, periodo: int, clave: int) -> float:
        """Monto USD del concepto ('RRC BEL', 'SONR IRR', ...) del ramo y mes: el valor que guardo Excel; si la celda
        es formula sin valor, el del diagnostico; si tampoco, error."""
        ramo_bd = self.ramo_bd(clave)
        if periodo not in self.periodos_con_montos:        # (meses de prima sin montos: no hay dato)
            return math.nan
        v = _num(self.montos.get((norm(concepto), periodo, ramo_bd)))
        if math.isnan(v) and (norm(concepto), periodo, ramo_bd) in self.montos:
            v = _num(self._cargar_diag()["montos"].get((norm(concepto), periodo, ramo_bd)))
            if math.isnan(v):
                raise ValueError(f"{concepto} {periodo} ramo {clave}: la celda es formula sin valor guardado. Abre la BD "
                                 f"en Excel y guardala, o pon {self.ruta_diagnostico.name} junto a la BD")
        return v

    def bloque(self, nombre: str, reserva: str, clave: int, periodo: int) -> float:
        ramo_bd = self.ramo_bd(clave)
        v = _num(self.bloques.get((nombre, reserva, periodo, ramo_bd)))
        if math.isnan(v) and (nombre, reserva, periodo, ramo_bd) in self.bloques:
            d = self._cargar_diag()["ind"].get((reserva, ramo_bd, periodo))
            v = _num(d.get(nombre)) if d else math.nan
        return v

    def factor_gasto(self, clave: int, periodo: int) -> float:
        """Ind. Gasto del RRC = FACTOR GTO (GTO / PND) del ramo y mes."""
        v = self.bloque("FACTOR GTO", "RRC", clave, periodo)
        if math.isnan(v) and periodo <= self.ultimo_real and periodo in self.periodos_con_montos:
            bel, gto = self.monto("RRC BEL", periodo, clave), self.monto("RRC GTO", periodo, clave)
            is_ = self.parametro("IS_RRC", clave, periodo)
            v = gto * is_ / bel if bel and not math.isnan(bel) and abs(bel) >= UMBRAL_CERO and not math.isnan(is_) else math.nan
        return v

    def _factor_mr_crudo(self, reserva: str, clave: int, periodo: int) -> float:
        v = self.bloque("FACTOR MR", reserva, clave, periodo)
        if math.isnan(v) and periodo <= self.ultimo_real and periodo in self.periodos_con_montos:
            bel, mr = self.monto(f"{reserva} BEL", periodo, clave), self.monto(f"{reserva} MR", periodo, clave)
            is_ = self.parametro("IS_RRC" if reserva == "RRC" else "IS_SONR", clave, periodo)
            v = mr * is_ / bel if bel and not math.isnan(bel) and abs(bel) >= UMBRAL_CERO and not math.isnan(is_) else math.nan
        return v

    def factor_mr(self, reserva: str, clave: int, periodo: int) -> float:
        """FACTOR MR = MR / PND (RRC) o MR / PD (SONR) del ramo y mes: el bloque de la hoja de montos (en un mes real sin
        valor guardado, MR / (BEL / IS) de los montos); en un mes sin BEL, el del mes mas cercano con dato."""
        k = ("FACTOR_MR", reserva, clave)
        if k not in self._series:
            periodos = sorted(self.periodos_con_montos)
            crudo = {p: self._factor_mr_crudo(reserva, clave, p) for p in periodos}
            self._series[k] = _interpolar(crudo, periodos, self._huecos, f"FACTOR MR {reserva} ramo {clave}")
        s = self._series[k]
        if periodo in s:
            return s[periodo]
        return s[min(s)] if periodo < min(s) else s[max(s)]

    def _factor_ret_crudo(self, clave: int, periodo: int) -> float:
        bel = _num(self.montos.get(("SONR BEL", periodo, self.ramo_bd(clave))))
        irr = _num(self.montos.get(("SONR IRR", periodo, self.ramo_bd(clave))))
        if not math.isnan(bel) and not math.isnan(irr) and bel >= UMBRAL_CERO:
            return 1.0 - irr / bel
        if periodo > self.ultimo_real and periodo in self.periodos_con_montos:
            try:
                bel_p = self.monto("SONR BEL", periodo, clave)
            except ValueError:
                bel_p = math.nan
            if math.isnan(bel_p) or abs(bel_p) < UMBRAL_CERO:  # la BD no proyecta IBNR en ese mes: no hay retencion que leer
                return math.nan
            ces, fm = self.bloque("CESION", "SONR", clave, periodo), self.bloque("FACTOR MR", "SONR", clave, periodo)
            is_b = self.indice("SONR", clave, periodo)
            if not math.isnan(ces) and not math.isnan(fm) and not math.isnan(is_b) and is_b > 0:
                return 1.0 - ces * (1.0 + fm / is_b)           # IRR / BEL = CESION x BRUTO / BEL = CESION x (1 + FM / IS)
        return math.nan

    def factor_ret(self, clave: int, periodo: int) -> float:
        """Factor de retencion del SONR (IRR = BEL x (1 - Factor_Ret)) = 1 - IRR / BEL del ramo y mes; en un mes sin
        BEL (p. ej. el ramo 80 en la historia) el del mes mas cercano con dato; acotado a [0, 1]."""
        k = ("FACTOR_RET", clave)
        if k not in self._series:
            periodos = sorted(self.periodos_con_montos)
            crudo = {p: self._factor_ret_crudo(clave, p) for p in periodos}
            s = _interpolar(crudo, periodos, self._huecos, f"Factor_Ret SONR ramo {clave}")
            fuera = [p for p, v in s.items() if not math.isnan(v) and not 0 <= v <= 1]
            if fuera:
                self.avisos.append(f"Factor_Ret SONR ramo {clave}: {len(fuera)} mes(es) con IRR mayor que el BEL en la BD "
                                   f"({fuera[0]} a {fuera[-1]}): retencion 0 (todo cedido). Revisalo; con "
                                   f"RAMOS_FACTOR_RET_CSV = ({clave},) se toma el Factor_Ret del area")
            self._series[k] = {p: (min(max(v, 0.0), 1.0) if not math.isnan(v) else v) for p, v in s.items()}
        s = self._series[k]
        if periodo in s:
            return s[periodo]
        return s[min(s)] if periodo < min(s) else s[max(s)]

    # ------------------------------------------------------------------ tablas para los scripts
    def parametros_rrc(self, anio: int | None = None, csv_duracion=None) -> pd.DataFrame:
        """ParametrosMens del RRC: un renglon por ramo con 'IS Bel Media-m', 'IS Bel 99.5%-m', 'Ind. Gasto-m' y
        'FACTOR MR-m' (MR / PND de la BD) para m = 1..12 del ano (mes de valuacion), mas Pesos_dur, Resto Monedas_dur,
        Pesos_ret y Resto Monedas_ret del CSV del area (csv_duracion) si se indica."""
        anio = anio or self.anio
        filas = []
        for clave in RAMOS_SCRIPT:
            f = {"Ramo": clave}
            for m in range(1, 13):
                p = anio * 100 + m
                f[f"IS Bel Media-{m}"] = self.indice("RRC", clave, p, "media")
                f[f"IS Bel 99.5%-{m}"] = self.indice("RRC", clave, p, "99.5")
                f[f"Ind. Gasto-{m}"] = self.factor_gasto(clave, p)
                f[f"FACTOR MR-{m}"] = self.factor_mr("RRC", clave, p)
            filas.append(f)
        df = pd.DataFrame(filas)
        dur = ["Pesos_dur", "Resto Monedas_dur", "Pesos_ret", "Resto Monedas_ret"]
        if csv_duracion and Path(csv_duracion).exists():
            csv = pd.read_csv(csv_duracion)
            if all(c in csv.columns for c in dur + ["Ramo"]):
                csv = csv[["Ramo"] + dur].drop_duplicates("Ramo")
                csv["Ramo"] = pd.to_numeric(csv["Ramo"], errors="coerce")
                df = df.merge(csv, how="left", on="Ramo")
                sin = df.loc[df[dur].isna().any(axis=1), "Ramo"].tolist()
                if sin:
                    self.avisos.append(f"duracion / retencion del MR: sin dato en {Path(csv_duracion).name} para los "
                                       f"ramos {sin}")
            else:
                self.avisos.append(f"{Path(csv_duracion).name} no trae las columnas {dur}: el MR del RRC no se puede "
                                   "calcular")
        else:
            self.avisos.append("sin CSV de duracion / retencion (ParametrosMens del area): el MR del RRC no se puede "
                               "calcular; indica csv_duracion")
        for c in dur:
            if c not in df.columns:
                df[c] = math.nan
        return df

    def is_cat(self, csv_is_cat=None) -> pd.DataFrame:
        """IS_Cat del RRC: 'IS Bel Media' = mes (CALMONTH), '71' y '73' = Ind Sin RRC de TEV e Hidro de ese mes. Los
        meses que HParametros no trae (anteriores a la hoja o vacios en ella) salen del CSV del area si se indica; si no,
        los anteriores llevan el primer mes de HParametros y los vacios se llenan con los meses vecinos."""
        fin = self.ultimo_proyectado or self.ultimo_real
        periodos = rango_meses(self.primer_periodo_hp, fin)
        csv_val: dict = {}
        if csv_is_cat and Path(csv_is_cat).exists():
            csv = pd.read_csv(csv_is_cat)
            if all(c in csv.columns for c in ("IS Bel Media", "71", "73")):
                for m, a, b in zip(pd.to_numeric(csv["IS Bel Media"], errors="coerce"),
                                   pd.to_numeric(csv["71"], errors="coerce"), pd.to_numeric(csv["73"], errors="coerce")):
                    if not math.isnan(m):
                        csv_val[int(m)] = {71: a, 73: b}
        cols = {}
        for clave in (71, 73):
            crudo = self.serie_cruda("IS_RRC", clave)
            del_csv = [p for p in periodos if math.isnan(crudo[p]) and not math.isnan(csv_val.get(p, {}).get(clave, math.nan))]
            for p in del_csv:
                crudo[p] = csv_val[p][clave]
            if del_csv:
                self.avisos.append(f"IS_Cat ramo {clave}: {len(del_csv)} mes(es) sin indice en HParametros ({del_csv[0]} a "
                                   f"{del_csv[-1]}) tomados de {Path(csv_is_cat).name}")
            lleno = _interpolar(crudo, periodos, self._huecos, f"IS_Cat ramo {clave}")
            cols[clave] = [lleno[p] for p in periodos]
        df = pd.DataFrame({"IS Bel Media": periodos, "71": cols[71], "73": cols[73]})
        previos = pd.DataFrame({"IS Bel Media": [m for m in sorted(csv_val) if m < self.primer_periodo_hp]})
        if len(previos):
            previos["71"] = [csv_val[m][71] for m in previos["IS Bel Media"]]
            previos["73"] = [csv_val[m][73] for m in previos["IS Bel Media"]]
            df = pd.concat([previos, df], ignore_index=True)
        else:
            inicio = mes_mas(self.primer_periodo_hp, -12 * 12)
            extra = rango_meses(inicio, mes_mas(self.primer_periodo_hp, -1))
            df = pd.concat([pd.DataFrame({"IS Bel Media": extra, "71": df["71"].iloc[0], "73": df["73"].iloc[0]}), df],
                           ignore_index=True)
            self.avisos.append(f"IS_Cat (71 y 73): los meses anteriores a {self.primer_periodo_hp} llevan el indice de "
                               "ese primer mes (no hay CSV del area con los anteriores)")
        return df.reset_index(drop=True)

    def param_sonr(self, desde: int | None = None, hasta: int | None = None, csv_param_sonr=None,
                   ramos_factor_ret_csv: tuple = ()) -> pd.DataFrame:
        """ParamSONR: un renglon por mes y ramo con Llave 'AAAAMM-ramo', Factor_Ret, Factor_MR (MR / PD de la BD), Ind
        Sin SONR Media, Ind Sin SONR 99.5% y LAG 1 a LAG 10 (los parametros del mes de valuacion). En los ramos de ramos_factor_ret_csv el Factor_Ret
        sale del ParamSONR del area (csv_param_sonr, por Llave; en un mes que el CSV no trae, el ultimo que trae)."""
        desde = desde or self.primer_periodo_hp
        hasta = hasta or self.ultimo_proyectado or self.ultimo_real
        fr_csv: dict = {}
        if ramos_factor_ret_csv:
            if csv_param_sonr and Path(csv_param_sonr).exists():
                csv = pd.read_csv(csv_param_sonr)
                if "Llave" in csv.columns and "Factor_Ret" in csv.columns:
                    for llave, fr in zip(csv["Llave"].astype(str), pd.to_numeric(csv["Factor_Ret"], errors="coerce")):
                        partes = llave.split("-")
                        if len(partes) == 2 and partes[0].isdigit() and partes[1].isdigit() and not math.isnan(fr):
                            fr_csv[(int(partes[1]), int(partes[0]))] = float(fr)
                if not fr_csv:
                    self.avisos.append(f"{Path(csv_param_sonr).name} no trae Llave y Factor_Ret: el Factor_Ret de los ramos "
                                       f"{list(ramos_factor_ret_csv)} sale de la BD")
                else:
                    self.avisos.append(f"Factor_Ret de los ramos {list(ramos_factor_ret_csv)} tomado de "
                                       f"{Path(csv_param_sonr).name} (RAMOS_FACTOR_RET_CSV), no de la BD")
            else:
                self.avisos.append(f"RAMOS_FACTOR_RET_CSV = {list(ramos_factor_ret_csv)} pero no esta el CSV del ParamSONR "
                                   "del area: el Factor_Ret sale de la BD")

        def factor_ret_de(clave, p):
            if clave in ramos_factor_ret_csv and fr_csv:
                meses = sorted(m for (c, m) in fr_csv if c == clave)
                if meses:
                    m = p if p in meses else max([m for m in meses if m <= p] or [meses[0]])
                    return fr_csv[(clave, m)]
            return self.factor_ret(clave, p)
        filas = []
        primer_dato = {}
        for clave in RAMOS_SONR:
            cr = self.serie_cruda("IS_SONR", clave)
            con = [p for p, v in cr.items() if not math.isnan(v)]
            primer_dato[clave] = min(con) if con else None
        for p in rango_meses(desde, hasta):
            for clave in RAMOS_SONR:
                if primer_dato[clave] is None or p < primer_dato[clave]:   # (antes del primer dato del ramo no hay parametro)
                    continue
                lags = {k: self.parametro(k, clave, p) for k in LAGS}
                media = self.indice("SONR", clave, p, "media")
                if math.isnan(media) and all(math.isnan(v) for v in lags.values()):
                    continue
                filas.append({"Llave": f"{p}-{clave}", "AñoMes": p, "Ramo": clave,
                              "Factor_Ret": factor_ret_de(clave, p), "Factor_MR": self.factor_mr("SONR", clave, p),
                              "Ind Sin SONR Media": media, "Ind Sin SONR 99.5%": self.indice("SONR", clave, p, "99.5"),
                              **lags, "Fuente IS": self.fuente_indice("SONR", clave, p)})
        return pd.DataFrame(filas)

    def tc_tabla(self) -> pd.DataFrame:
        """TC USD por mes como la tabla de tipo de cambio del area: cTCAD_FecAMD (AAAAMM), cTCAD_Mnt."""
        return pd.DataFrame({"cTCAD_FecAMD": sorted(self.tc), "cTCAD_Mnt": [self.tc[p] for p in sorted(self.tc)]})

    def tc_dict(self) -> dict:
        return dict(sorted(self.tc.items()))

    def tc_de(self, periodo: int) -> float:
        if periodo in self.tc:
            return self.tc[periodo]
        anteriores = [p for p in self.tc if p <= periodo]
        return self.tc[max(anteriores)] if anteriores else self.tc[min(self.tc)]

    def saldos(self, reserva: str, periodos: list[int], escenario: int, tipos: tuple | None = None) -> pd.DataFrame:
        """Saldos de la BD (reales o proyectados) por ramo, mes y tipo de monto en la forma del escenario base de los
        scripts (COLUMNAS_ESC), con la convencion de signos del area (SIGNO)."""
        tipos = tipos or tuple(SIGNO[reserva])
        filas = []
        for p in periodos:
            tc = self.tc_de(p)
            for clave in RAMOS_SCRIPT:
                for tipo in tipos:
                    concepto = f"{reserva} {CONCEPTO_BD.get(tipo, tipo)}"
                    if (norm(concepto), p, self.ramo_bd(clave)) not in self.montos:
                        continue
                    usd = self.monto(concepto, p, clave)
                    usd = 0.0 if math.isnan(usd) or abs(usd) < UMBRAL_CERO else usd * SIGNO[reserva][tipo]
                    filas.append({"Reserva": reserva, "Escenario": escenario, "Tipo de Monto": tipo, "Ramo": clave,
                                  "Periodo": p, "Monto_MXN": usd * tc, "Monto_USD": usd, "TC": tc})
        return pd.DataFrame(filas, columns=COLUMNAS_ESC)

    def escenario_base(self, reserva: str, anio: int | None = None) -> pd.DataFrame:
        """Escenario 0 (ano base): saldos reales de diciembre del ano anterior."""
        anio = anio or self.anio
        return self.saldos(reserva, [(anio - 1) * 100 + 12], 0)

    def saldos_proyectados(self, reserva: str, desde: int | None = None, hasta: int | None = None,
                           escenario: int = 1) -> pd.DataFrame:
        """Saldos proyectados de la BD (BEL por FND y derivados) de desde a hasta, para los meses que el script no
        valua (los 'meses faltantes' del escenario 3 o el escenario 1)."""
        desde = desde or self.primer_proyectado
        hasta = hasta or self.ultimo_proyectado
        if desde is None or hasta is None:
            return pd.DataFrame(columns=COLUMNAS_ESC)
        return self.saldos(reserva, rango_meses(desde, hasta), escenario)

    # ------------------------------------------------------------------ informes
    def avisos_texto(self) -> list[str]:
        """Avisos, con los meses llenados agrupados por rango (un aviso por rango, con los parametros que abarca)."""
        grupos: dict = {}
        for etiqueta, d, h, n in self._huecos:
            grupos.setdefault((d, h, n), []).append(etiqueta)
        out = list(self.avisos)
        for (d, h, n), etiquetas in sorted(grupos.items()):
            rango = f"{d}" if d == h else f"{d} a {h}"
            out.append(f"{n} mes(es) sin dato ({rango}) llenados con los meses vecinos en {len(etiquetas)} serie(s): "
                       + ", ".join(etiquetas[:6]) + (" ..." if len(etiquetas) > 6 else ""))
        return out

    def resumen(self) -> list[str]:
        n_fa = len({(r, c) for (r, c, _) in self.is_fa})
        lineas = [f"Insumos de {self.ruta_bd.name}: HParametros '{self.hoja_hp}' con {len(self.hp)} renglones; tipos "
                  f"{', '.join(sorted(self.tipos))}; ultimo mes real {self.ultimo_real}; proyeccion "
                  f"{self.primer_proyectado} a {self.ultimo_proyectado}",
                  f"Hoja de montos: {len(self.periodos_montos)} meses ({min(self.periodos_montos)} a "
                  f"{max(self.periodos_montos)}), ramos {', '.join(sorted(self.col_ramo_bd, key=int))}, TC de "
                  f"{min(self.tc)} a {max(self.tc)}",
                  (f"IS (FA): {n_fa} series (reserva x ramo), {min(p for (_, _, p) in self.is_fa)} a "
                   f"{max(p for (_, _, p) in self.is_fa)}; se usa en los meses proyectados de RRC "
                   f"{self.ramos_is_fa.get('RRC')} y SONR {self.ramos_is_fa.get('SONR')}" if self.is_fa and self.usar_is_fa
                   else "IS (FA): no se usa")]
        return lineas

    def exportar(self, ruta, anio: int | None = None, csv_duracion=None, csv_is_cat=None, csv_param_sonr=None,
                 ramos_factor_ret_csv: tuple = ()):
        """Escribe en un xlsx las tablas que reciben los scripts (para auditar que insumo se uso)."""
        anio = anio or self.anio
        tablas = [("ParametrosMens_RRC", self.parametros_rrc(anio, csv_duracion)),
                  ("IS_Cat", self.is_cat(csv_is_cat)),
                  ("ParamSONR", self.param_sonr(csv_param_sonr=csv_param_sonr, ramos_factor_ret_csv=ramos_factor_ret_csv)),
                  ("TC_USD", self.tc_tabla()),
                  ("Escenario_base", pd.concat([self.escenario_base("RRC", anio), self.escenario_base("SONR", anio)],
                                               ignore_index=True)),
                  ("Saldos_proyectados", pd.concat([self.saldos_proyectados("RRC"), self.saldos_proyectados("SONR")],
                                                   ignore_index=True))]
        avisos = self.avisos_texto()               # (ya con los que levantaron las tablas)
        with pd.ExcelWriter(ruta, engine="openpyxl") as xw:
            pd.DataFrame({"Dato": ["BD", "Ultimo mes real", "Proyeccion", "IS (FA)"] + [f"Aviso {i + 1}" for i in range(len(avisos))],
                          "Valor": [str(self.ruta_bd), self.ultimo_real,
                                    f"{self.primer_proyectado} a {self.ultimo_proyectado}",
                                    "si" if self.is_fa and self.usar_is_fa else "no"] + avisos}).to_excel(
                xw, sheet_name="Resumen", index=False)
            for nombre, df in tablas:
                df.to_excel(xw, sheet_name=nombre, index=False)


if __name__ == "__main__":          # uso: python insumos_bd.py <ruta de la BD> [xlsx de salida]
    import sys
    ins = InsumosBD(sys.argv[1])
    if len(sys.argv) > 2:
        ins.exportar(sys.argv[2])
        print(f"   Tablas en {sys.argv[2]}")
    for a in ins.avisos_texto():
        print("   AVISO:", a)
