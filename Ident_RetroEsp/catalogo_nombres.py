# -*- coding: utf-8 -*-
"""
Traduccion de claves a nombres para las consultas de Identificacion RetroEsp.

Este modulo concentra la logica que convierte las claves numericas que entrega
SIREC (corredor, cedente, pais, ramo, subramo, territorio) al texto descriptivo
que aparece en la hoja "Catalogo".

Se usa desde:
    - Ident_RetroEsp__Prop_aod_nombres.py
    - Ident_RetroEsp__Fac_aod_nombres.py
    - Convertir_Ident_RetroEsp_a_nombres.py

Los scripts de consulta lo importan si esta en la misma carpeta; si no lo
encuentran, traen una copia interna equivalente, de modo que se pueden correr
tal cual desde Spyder sin depender de este archivo.
"""

import pandas as pd

# Encabezado de la clave -> encabezado de la descripcion, tal como estan en la
# hoja "Catalogo" del archivo "Catalogo consulta ident_retroesp.xlsx".
CATALOGOS_COLUMNAS = {
    'Cedente':    ('No. Cedente',    'Nombre Cedente'),
    'Corredor':   ('No. Corredor',   'Nombre Corredor'),
    'Pais':       ('ID Pais',        'Pais'),
    'Ramo':       ('ID Ramo',        'Ramo'),
    'Subramo':    ('ID Subramo',     'Subramo'),
    'Territorio': ('ID Territorios', 'Territorio'),
}

# Campos que no viven en el catalogo pero que tampoco conviene dejar como clave.
SI_NO = {'0': 'No', '1': 'Si'}

# Como se muestra una clave que no aparece en el catalogo. Se deja marcada para
# que no se confunda con un nombre y para saber que hay que dar de alta la clave.
# Si se prefiere ver la clave pelona, poner FORMATO_CLAVE_DESCONOCIDA = "{clave}".
FORMATO_CLAVE_DESCONOCIDA = "{clave} (sin catálogo)"

# Aqui se van guardando las claves que no se encontraron, por catalogo, para
# poder reportarlas al final de la corrida.
CLAVES_SIN_CATALOGO = {}

# Catalogos que se completan con otro cuando la clave no existe.
# Hay claves de ramo (30 Accidentes Personales General, 70 Catastroficos en
# General) que solo estan dadas de alta en el catalogo de subramos.
CATALOGO_RESPALDO = {'Ramo': 'Subramo'}

# Claves que se completaron con el catalogo de respaldo, y cuales se usaron.
CLAVES_DE_RESPALDO = {}
CLAVES_USADAS_DE_RESPALDO = {}


def _normaliza_texto(valor):
    """Quita acentos y espacios sobrantes para poder comparar encabezados."""
    if valor is None:
        return ''
    texto = str(valor).strip()
    reemplazos = {'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ü': 'u',
                  'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U', 'Ü': 'U',
                  'ñ': 'n', 'Ñ': 'N'}
    for viejo, nuevo in reemplazos.items():
        texto = texto.replace(viejo, nuevo)
    return texto


def normaliza_clave(valor):
    """Deja la clave como texto sin decimales: 1, 1.0, '1', ' 1 ' -> '1'."""
    if valor is None:
        return ''
    if isinstance(valor, float) and pd.isna(valor):
        return ''
    try:
        if pd.isna(valor):
            return ''
    except (TypeError, ValueError):
        pass
    texto = str(valor).strip()
    if not texto or texto.lower() == 'nan':
        return ''
    try:
        return str(int(float(texto)))
    except (TypeError, ValueError):
        return texto


def cargar_catalogos_desde_filas(filas):
    """Arma los diccionarios clave -> nombre a partir de las filas del catalogo.

    'filas' es una lista de listas (la primera es la de encabezados). Para cada
    catalogo se busca el encabezado de la clave y se toma como descripcion la
    columna inmediata de la derecha, que es como esta armado el archivo.
    """
    if not filas:
        return {nombre: {} for nombre in CATALOGOS_COLUMNAS}

    encabezados = [_normaliza_texto(v) for v in filas[0]]
    catalogos = {}

    for nombre, (col_clave, col_desc) in CATALOGOS_COLUMNAS.items():
        clave_norm = _normaliza_texto(col_clave)
        desc_norm = _normaliza_texto(col_desc)
        catalogo = {}

        if clave_norm in encabezados:
            i = encabezados.index(clave_norm)
            j = i + 1
            # El archivo trae la descripcion pegada a la derecha de la clave.
            if j < len(encabezados) and encabezados[j] != desc_norm:
                if desc_norm in encabezados:
                    j = encabezados.index(desc_norm)
            for fila in filas[1:]:
                if len(fila) <= max(i, j):
                    continue
                clave = normaliza_clave(fila[i])
                descripcion = fila[j]
                if not clave or descripcion is None or str(descripcion).strip() == '':
                    continue
                catalogo.setdefault(clave, str(descripcion).strip())

        catalogos[nombre] = catalogo

    _aplicar_respaldos(catalogos)
    return catalogos


def _aplicar_respaldos(catalogos):
    """Completa un catalogo con las claves que solo existen en otro."""
    CLAVES_DE_RESPALDO.clear()
    for destino, origen in CATALOGO_RESPALDO.items():
        catalogo_destino = catalogos.get(destino, {})
        catalogo_origen = catalogos.get(origen, {})
        agregadas = set()
        for clave, descripcion in catalogo_origen.items():
            if clave not in catalogo_destino:
                catalogo_destino[clave] = descripcion
                agregadas.add(clave)
        catalogos[destino] = catalogo_destino
        CLAVES_DE_RESPALDO[destino] = agregadas
    return catalogos


def cargar_catalogos(ruta_catalogo, hoja='Catálogo'):
    """Lee el archivo de catalogo (.xlsx) y regresa los diccionarios de nombres."""
    try:
        crudo = pd.read_excel(ruta_catalogo, sheet_name=hoja, header=None)
    except Exception:
        crudo = pd.read_excel(ruta_catalogo, header=None)
    filas = crudo.where(pd.notna(crudo), None).values.tolist()
    return cargar_catalogos_desde_filas(filas)


def traducir(valor, catalogo, conservar_clave_desconocida=True, separador=', ',
             formato_desconocida=None, nombre_catalogo=None):
    """Traduce una clave o una lista de claves separadas por coma.

    Ejemplos:
        traducir('60, 71', catalogos['Ramo'])  ->  'General, Terremoto y Erupcion Volcanica'
        traducir(789, catalogos['Cedente'])    ->  'XS Latam LLC'

    Se respeta el orden original de la lista. Las claves que no estan en el
    catalogo no se pierden: se muestran con FORMATO_CLAVE_DESCONOCIDA y se
    registran en CLAVES_SIN_CATALOGO para poder darlas de alta despues.
    """
    if valor is None:
        return valor
    try:
        if pd.isna(valor):
            return valor
    except (TypeError, ValueError):
        pass

    texto = str(valor).strip()
    if not texto or texto.lower() == 'nan':
        return valor

    formato = FORMATO_CLAVE_DESCONOCIDA if formato_desconocida is None else formato_desconocida

    partes = [p.strip() for p in texto.split(',')]
    traducidas = []
    for parte in partes:
        if not parte:
            continue
        clave = normaliza_clave(parte)
        nombre = catalogo.get(clave)
        if nombre is None:
            if nombre_catalogo:
                CLAVES_SIN_CATALOGO.setdefault(nombre_catalogo, set()).add(clave or parte)
            if not conservar_clave_desconocida:
                continue
            nombre = formato.format(clave=parte)
        elif nombre_catalogo and clave in CLAVES_DE_RESPALDO.get(nombre_catalogo, ()):
            CLAVES_USADAS_DE_RESPALDO.setdefault(nombre_catalogo, set()).add(clave)
        if nombre not in traducidas:
            traducidas.append(nombre)

    if not traducidas:
        return valor

    return separador.join(traducidas)


def reporte_claves_sin_catalogo():
    """Texto con las claves que no se encontraron y las que se resolvieron con
    el catalogo de respaldo, para poder revisar el catalogo."""
    lineas = []

    if CLAVES_USADAS_DE_RESPALDO:
        lineas.append("Claves resueltas con otro catálogo (conviene darlas de alta en el suyo):")
        for nombre in sorted(CLAVES_USADAS_DE_RESPALDO):
            claves = sorted(CLAVES_USADAS_DE_RESPALDO[nombre], key=lambda z: (len(z), z))
            origen = CATALOGO_RESPALDO.get(nombre, '')
            lineas.append(f"  - {nombre} (tomadas de {origen}): {', '.join(claves)}")

    if not CLAVES_SIN_CATALOGO:
        lineas.append("Todas las claves se encontraron en el catálogo.")
        return "\n".join(lineas)

    lineas.append("Claves que NO estan en el catálogo (revisar 'Catálogo consulta ident_retroesp.xlsx'):")
    for nombre in sorted(CLAVES_SIN_CATALOGO):
        claves = sorted(CLAVES_SIN_CATALOGO[nombre], key=lambda z: (len(z), z))
        lineas.append(f"  - {nombre}: {', '.join(claves)}")
    return "\n".join(lineas)


def traducir_si_no(valor):
    """0 -> 'No', 1 -> 'Si'. Cualquier otra cosa se deja igual."""
    clave = normaliza_clave(valor)
    return SI_NO.get(clave, valor)


# Encabezado que aparece en el Excel -> catalogo que le corresponde.
# Sirve para los encabezados repetidos (cedido y tomado comparten nombre).
ENCABEZADOS_A_CATALOGO = {
    'Corredor':               'Corredor',
    'Ramos Cubiertos':        'Ramo',
    'Subramos Excluidos':     'Subramo',
    'Subramos Cubiertos':     'Subramo',
    'Territorios Cubiertos':  'Territorio',
    'Territorio llave':       'Territorio',
    'Paises Excluidos':       'Pais',
    'Paises Cubiertos':       'Pais',
}

# Nombre interno de la columna en el DataFrame -> catalogo que le corresponde.
COLUMNAS_A_CATALOGO = {
    'Corredor':               'Corredor',   # corredor del cedido
    'Ramos_Cubiertos':        'Ramo',
    'Subramos_Excluidos':     'Subramo',
    'Territorios_Cubiertos':  'Territorio',
    'Paises_Excluidos':       'Pais',
    'Corredor_':              'Corredor',   # corredor del tomado
    'cTER_Id':                'Territorio',
    'Ramos_Cubiertos_':       'Ramo',
    'Subramos_Cubiertos':     'Subramo',
    'Territorio':             'Territorio',
    'Paises_Cubiertos':       'Pais',
}


def traducir_dataframe(df, catalogos, columnas=None, columnas_si_no=('Negocio_MGA_TP',)):
    """Regresa una copia del DataFrame con las claves ya convertidas a nombres."""
    columnas = COLUMNAS_A_CATALOGO if columnas is None else columnas
    salida = df.copy()

    for columna, nombre_catalogo in columnas.items():
        if columna not in salida.columns:
            continue
        catalogo = catalogos.get(nombre_catalogo, {})
        if not catalogo:
            continue
        salida[columna] = salida[columna].apply(
            lambda v, c=catalogo, n=nombre_catalogo: traducir(v, c, nombre_catalogo=n))

    for columna in columnas_si_no:
        if columna in salida.columns:
            salida[columna] = salida[columna].apply(traducir_si_no)

    return salida
