# Metodología de redistribución de primas, comisiones y siniestros entre Terremoto (ramo 73) e Hidrometeorológicos y Otros Riesgos (ramo 71)

**Presupuesto Técnico 2027 (RPAT / Patria Re)**
Versión 1.4, 16 de octubre de 2026. Documento de trabajo para Planeación Financiera; pensado para que una persona que no estuvo en el equipo pueda reproducir, auditar y defender el procedimiento. Acompaña a `0a_Actualizar_Base1.py` (v1.0), a `0_Redistribucion_TEV_HyOR.py` (v1.4), a `README_Script_Redistribucion.md` y a la carpeta `pruebas/`.

---

## 0. Resumen ejecutivo

* **Problema.** En el Presupuesto Técnico 2027 (archivo `PptoTecnico2027.csv`, insumo de `CtaMens.py`) hay negocios multirramo cuya prima quedó cargada en un solo ramo catastrófico. A nivel compañía, la participación de Terremoto dentro de la prima catastrófica (73 ÷ (73 + 71)) fue de 58.4 % a 58.8 % cada año entre 2023 y 2026, y en el FCST 2027 cae a 30.2 % (Terremoto −45 %, HyOR +81 %). El error está en el **porcentaje por ramo aplicado a cada negocio en la carga**, no en el total del negocio.
* **Solución.** Un script previo a `CtaMens.py` (`0_Redistribucion_TEV_HyOR.py`) que, negocio por negocio (LLAVE), reparte el monto de cada fila entre los ramos 73 y 71 con un porcentaje **observado** (histórico real contabilizado del propio negocio, o condición contractual documentada), conservando exactamente el total del negocio por cuenta, mes y firma de fila, y dejando trazabilidad fila a fila.
* **Sin números inventados.** Cada porcentaje proviene de un dato verificable y queda registrado con su fuente. Sólo se ajustan automáticamente los negocios cargados en un solo ramo cuya historia es creíble y estable; todo lo demás (particiones ya cargadas en ambos ramos, reclasificaciones completas, historia escasa o inestable, facultativos, contratos sin número) queda en `REVISAR` hasta que el negocio lo confirme por escrito. Los negocios sin información **no se ajustan** y se reportan. La participación global histórica (≈59 %) se usa **sólo como validación**, nunca como objetivo.
* **Coherencia con 2026.** Se conserva la unidad de negocio (LLAVE = TipoRea-Cedente-Contrato-LN), la lógica de clonar la fila al ramo faltante cambiando únicamente el centro de beneficio, el reparto proporcional al perfil mensual original, el redondeo con cierre al centavo, los umbrales de 2026 como validación y la trazabilidad. Cambia, de forma deliberada y documentada (sección 3), que 2027 **conserva totales** (2026 permitió cambiar niveles por negocio con montos objetivo capturados a mano), toca **sólo** los ramos 71 y 73, y es un solo script reproducible.
* **Lo que sigue después del script.** Las matrices de costos XL y de siniestros catastróficos que usa CtaMens se dimensionan con la propia base, así que el procedimiento completo es de **dos pasadas** de CtaMens con regeneración de matrices entre ellas (sección 9), y el efecto llega hasta reservas (sección 10).

---

## 1. Diagnóstico

### 1.1 Evidencia a nivel compañía (captura `Res_Rec_Ajustes_Form_f`)

| Año | HyOR (71) | Terremoto (73) | 73 + 71 | Participación 73 |
|---|---:|---:|---:|---:|
| 2023 | 1,262,584,088 | 1,804,029,461 | 3,066,613,549 | 58.8 % |
| 2024 | 1,698,151,532 | 2,388,431,292 | 4,086,582,824 | 58.4 % |
| 2025 | 2,292,019,444 | 3,257,278,008 | 5,549,297,452 | 58.7 % |
| 2026 (al corte de la captura) | 1,743,336,974 | 2,484,104,761 | 4,227,441,735 | 58.8 % |
| FCST 2027 | 4,158,455,158 | 1,795,630,092 | 5,954,085,250 | **30.2 %** |

La participación de Terremoto es notablemente estable durante cuatro años y se rompe en 2027. La suma 73 + 71 del FCST 2027 crece 7.3 % contra 2025 (último cierre completo; la columna 2026 es parcial y no debe usarse como base de crecimiento sin anualizar): el total no es la anomalía, el reparto sí.

### 1.2 Evidencia en el detalle (extracto `PptoTecnico2027.xlsx`, LN04001 y LN04002, 69,999 filas)

* **El cargador aplica un porcentaje fijo por ramo a todas las filas del negocio.** En las tres LLAVEs que ya traen 71 y 73, las filas de ambos ramos son idénticas en todos sus atributos (mes, año de suscripción, corredor, región, moneda, tipo de cesión) y sólo cambian el centro de beneficio y el monto; la razón 73 ÷ (71 + 73) es constante fila a fila (0.3333, 0.26, 0.32) en primas y en comisiones, y la razón comisión ÷ prima es la misma en ambos ramos (0.25 / 0.25; 0.155 / 0.155). El mismo patrón aparece en 148 LLAVEs que mezclan Incendio (ramo 60) con 71/73, con porcentajes redondos (0.50, 0.45, 0.52, 0.40, 0.60) idénticos por mes, por año de suscripción y por corredor. El porcentaje es también idéntico en los años fiscales 2026 y 2028 en adelante.
* **Los siniestros catastróficos no vienen en el presupuesto.** No existe ninguna fila de siniestros (GL 54) para los ramos 71 ni 73 en ningún año fiscal del archivo; `CtaMens.py` los modela con las matrices `xDnEvCat` / `xDnAttritional` por centro de beneficio y región, prorrateadas por la prima (GL 61).
* **El extracto no contiene el problema global.** En LN04001/LN04002 Terremoto es el 89 % de la prima 71 + 73; el "todo en Hidro" está en otras líneas o regiones. Por eso el procedimiento es **bidireccional** (71→73 y 73→71), igual que los fallbacks `73:71, 71:73` del proceso 2026.
* Hay 162 filas de ajuste con signo contrario (reversos) en 10 LLAVEs; el método respeta el signo de cada fila.
* Los montos tienen a lo sumo dos decimales y no hay filas duplicadas (misma firma y mismo centro de beneficio).
* 33 LLAVEs de los ramos 71/73 tienen contrato nulo (hasta 5 corredores cada una); 32 son facultativas y una es un negocio proporcional de 17 millones que agrupa varios contratos distintos bajo contrato "0".

### 1.3 Conclusión del diagnóstico

Corregir el presupuesto equivale a **recalcular el porcentaje por ramo de cada negocio afectado y volver a aplicarlo fila por fila**, exactamente como lo hace el cargador cuando el negocio está bien parametrizado. Lo único que hay que aportar desde fuera es el porcentaje correcto, y debe venir de un dato observable y creíble.

---

## 2. Principios

1. **Ningún número inventado.** Todo porcentaje aplicado proviene de (a) la condición contractual documentada del negocio o (b) su historia real contabilizada, con un volumen creíble frente al presupuesto. Si no existe ninguna de las dos, el negocio no se toca y se reporta.
2. **Conservación de totales.** Para cada negocio, cuenta contable, mes, año fiscal y firma de fila, la suma de los ramos 71 + 73 es idéntica antes y después, al centavo. El presupuesto total de la compañía y de cada línea no cambia; sólo cambia su asignación entre dos centros de beneficio.
3. **No tocar lo que no está en alcance.** Los demás ramos (Incendio 60, etc.), las LLAVEs fuera de alcance y las 44 columnas que no son el centro de beneficio y el monto quedan idénticas.
4. **Trazabilidad fila a fila y reproducibilidad.** Cada fila modificada o creada queda registrada con su fila origen, peso aplicado, fuente del peso y residuo de redondeo. El script, sus parámetros, sus insumos (con sha256) y el layout permiten regenerar el resultado.
5. **Decisiones humanas explícitas.** Toda decisión del layout (excluir, incluir, forzar un porcentaje) lleva justificación obligatoria; forzar exige además la fuente documental. El script se niega a correr si falta. Las decisiones que mueven más prima (particiones ya cargadas, reclasificaciones completas) requieren confirmación explícita.
6. **Parámetros fijados por escrito antes de ver resultados agregados** (sección 12): años base, método, tolerancia, materialidad y políticas se aprueban antes de la corrida productiva y quedan en el resumen de la corrida con responsable y fecha.
7. **La validación agregada no es un objetivo.** Comparar la participación global resultante con el 58–59 % histórico sirve para detectar que falta algo, no para calibrar pesos ni elegir método.

---

## 3. Qué se hizo en 2026 y qué se conserva

Reconstruido de la carpeta `Redist TEV HyOR` (Word *Proceso de Recalibración* y scripts 1.1, 2.1, UI, 3.1, 3.2, 4, 5). Los insumos de aquel año (`TD.xlsx`, `LAYOUT_RED.xlsx`, `Base_1.xlsx`, `Rec3.pptx`, consolidados) no vienen en el zip; el script 1.1 del zip ya estaba adaptado a 2027 (rutas `2027\5_Generacion`, `Outputs\LAYOUT_RED.xlsx`), señal de que el proceso 2026 se había empezado a correr sobre el presupuesto 2027 (ver insumo 9 de la sección 12).

| Elemento | 2026 | 2027 (esta metodología) | Motivo del cambio |
|---|---|---|---|
| Unidad de negocio | LLAVE = ZTIPOREAS-ZCEDENTE-ZCONTRATO-FUNCAREA | **Igual** | Coherencia |
| Contrato nulo / facultativos | De hecho fuera del proceso: 1.1 omitía la LLAVE si el contrato era nulo y 3.1 escribía el tramo vacío (`3-25--LN04002`) | En alcance con contrato "0" (`3-25-0-LN04002`, igual que CtaMens), pero siempre en `REVISAR` | **Decisión nueva**, no herencia; al cruzar con `LAYOUT_RED` 2026 hay que homologar ese tramo |
| Universo de decisión | FISCYEAR = año, AMOUNT ≠ 0 (igual que CtaMens) | **Igual** para decidir (parámetro `anio_decision` = 2027); el reparto se aplica a todos los años fiscales del negocio | El cociente por ramo es idéntico en 2026, 2027 y 2028+; dejar sólo 2027 crearía un salto entre años en `PptoTecnico2027_Ced.csv` |
| Ramos tocados | Todos los ramos de la LLAVE presentes en el TD, con clon hacia cualquier ramo faltante (donador = fallback o ramo más frecuente) | **Sólo 71 y 73**; los demás ramos quedan idénticos | 2027 es una corrección de asignación entre los dos ramos CAT |
| Selección de LLAVEs | Banderas objetivas de tendencia sobre el real 2020–2026 (YoY ±60/−40 %, salto 0→≥100,000, meses incompletos, outliers) y después **selección manual** cedente a cedente en un layout | Reglas objetivas (sección 6): ajuste automático sólo para negocios cargados en un solo ramo con historia creíble y estable; `REVISAR` para los demás; layout justificado. Los umbrales 2026 se reutilizan en la validación de tendencia y en la materialidad | Reproducible y auditable; conserva el juicio del negocio con justificación |
| Origen de los montos por ramo | `TD.xlsx` con **montos objetivo absolutos** por LLAVE-Ramo-Tipo, capturados en Excel "con la distribución del año anterior" (fórmula no documentada); podían cambiar el nivel del negocio (p. ej. 37,056.74 → 72,163.99) | **Pesos** por LLAVE-Ramo-Tipo calculados con fórmula explícita a partir del histórico real o de la condición contractual; el nivel del negocio **no cambia** | Corrección de asignación, no recalibración de niveles; evita capturas manuales. Con un año base, el peso del año anterior es la lectura más plausible de la "distribución del año anterior" de 2026; la fórmula exacta del TD no se conoce y sólo el back-test de la sección 11 puede confirmarla |
| Mecánica | AMOUNT_fila = TD × Pct_Distrib, Pct = \|monto\| ÷ Σ\|monto\| del grupo LLAVE-Ramo-Tipo redondeado a 6 decimales; redondeo a 2 decimales; cierre al centavo por mayor resto; el signo de la salida lo daba el TD | AMOUNT_fila,ramo = (monto 71 + monto 73 de la misma firma **y mismo signo**) × peso_ramo; redondeo a 2 decimales; residuo a la fila mayor del pool | Conserva el perfil mensual y de atributos igual que 2026 pero fila a fila, respeta el signo de cada fila (los reversos se reparten con su signo) y garantiza el total 71 + 73 por firma; reproduce al centavo las LLAVEs que el cargador sí partió bien cuando se usa su porcentaje nominal |
| Ramo faltante | Clonar las filas del ramo donador (73↔71) y poner CeBe/PROFTCTR = `A0{ramo}000000` sólo en los clones | **Igual** (clon por firma; código tomado del propio archivo y validado contra `Subramo.csv`) | Coherencia |
| Comisiones | Mismo mecanismo que primas, con su propio monto TD | Pesos propios de comisiones si el histórico los trae y son válidos; si no, los de primas; un `FORZAR` gobierna todos los tipos | Coherencia; el dato muestra razón comisión/prima igual entre ramos dentro del negocio |
| Siniestros (GL 54) | No se redistribuían; clones a cero | No existen para 71/73 en el presupuesto; si existieran, política parametrizable (recomendación: pesos de primas; alternativa: no tocar, como 2026) | Los siniestros CAT se modelan en CtaMens por centro de beneficio + región |
| Reinserción | Quitar de BD_CtaMens todas las filas de la LLAVE (3.1) y reinyectar lo redistribuido (3.2); unión manual; cesión después (4) | Un solo script sobre el csv crudo, antes de CtaMens; CtaMens calcula cesión, XL, EvCat y gastos sobre la base corregida | Elimina pasos manuales; mismo orden lógico (redistribuir → ceder) |
| Trazabilidad | Hojas Paso1/2/3, Log_Ramos, Control_TD, DIAG por LLAVE en un Excel por LLAVE | Un libro de trazabilidad global (alcance, pesos, sensibilidad, tendencia, detalle fila a fila, cuadres, participación, combinaciones nuevas y desaparecidas, verificación de insumos) y log | Mismo espíritu, consolidado |

Fragilidades de 2026 que **no** se heredan: el signo de la salida dependía de cómo se capturó el TD; las filas cuyo ramo no estaba en el TD desaparecían en silencio; el total del negocio no estaba garantizado; el reemplazo "estricto" de CeBe no funcionaba (parchado con la estandarización); la tipificación por GL dependía de un etiquetado previo; nombres de archivo y LLAVEs codificados a mano.

---

## 4. Definiciones

* **LLAVE (negocio).** `ZTIPOREAS-ZCEDENTE-ZCONTRATO-FUNCAREA`, con nulos como 0 (misma regla que CtaMens). Ejemplo: `1-40-16-LN04001`.
* **Ramo.** El `Ramo2` de `Subramo.csv` para el centro de beneficio `/ERP/PROFTCTR` (es la columna con la que CtaMens arma sus llaves de cesión y de costos XL); si no hay `Subramo.csv`, los dígitos 2 a 4 del centro de beneficio (`A071000000` → 71, `A073000000` → 73). CtaMens reescribe el centro de beneficio de LN04004 antes de derivar el ramo, por lo que esa LN queda fuera de alcance.
* **Tipo.** Dos primeros dígitos de `/ERP/GL_ACCT`: 61 Primas, 53 Comisiones, 54 Siniestros. Convención de signo del presupuesto: primas negativas, comisiones y siniestros positivos.
* **Firma de fila.** El valor de todas las columnas del archivo excepto `/ERP/PROFTCTR` y `/ERP/AMOUNT` (y `/ERP/AMOUNT_T`). Dos filas con la misma firma y distinto centro de beneficio son "la misma fila repartida en dos ramos".
* **Pool.** Suma de `/ERP/AMOUNT` de las filas 71 y 73 que comparten firma y signo. Es la cantidad que se reparte.
* **Peso.** w(LLAVE, tipo, ramo) ∈ [0, 1], con w71 + w73 = 1, redondeado a 10 decimales y renormalizado (reproducibilidad).
* **Participación.** share73 = monto 73 ÷ (monto 71 + monto 73), calculada sobre primas del año de decisión.

---

## 5. Fuente y cálculo de los pesos

Jerarquía (se usa la primera fuente disponible para cada LLAVE):

### Nivel 1. Condición contractual documentada

Si el contrato o slip, el expediente en SIREC o el insumo de presupuesto de la línea de negocio establecen la participación por ramo (p. ej. "50 % TEV / 50 % HyOR"), ese porcentaje se captura en el layout con `ACCION = FORZAR`, una fila por ramo, `FUENTE` (documento) y `JUSTIFICACION`. Es la mejor evidencia posible porque es la definición del negocio, no una estimación. Un `FORZAR` sustituye por completo los pesos de la fuente para esa LLAVE (todos los tipos): si no se capturan pesos de comisiones o siniestros, se usan los de primas forzados.

### Nivel 2. Histórico real del propio negocio

Insumo: montos reales contabilizados (prima tomada, comisiones, siniestros) por LLAVE × ramo × año **y mes**, extraídos de la misma fuente que alimenta los reportes reales (consulta real de SAP BW; `Base_1.xlsx` del análisis 2026 tiene esa estructura). Para facultativos y contratos nulos el histórico debe venir con la misma codificación que el presupuesto (contrato 0), de lo contrario no cruza.

Fórmula (método `ponderado`, recomendado):

```
w(LLAVE, tipo, ramo) = Σ_{años base válidos} |Monto_real(LLAVE, tipo, ramo, año)|
                       ─────────────────────────────────────────────────────────
                       Σ_{ramo' ∈ {71,73}} Σ_{años base válidos} |Monto_real(LLAVE, tipo, ramo', año)|
```

* **Validez año por año.** Un año cuenta sólo si (a) los montos de ambos ramos tienen el mismo signo (un reverso que domina un ramo lo invalida), (b) no suman cero y (c) si el histórico trae el mes, tiene al menos `min_meses_anio` meses registrados (8, el umbral INCOMPLETE_MONTHS de 2026). Los años excluidos quedan anotados en `MOTIVO`; la LLAVE pasa a `Sin_Peso` sólo si no queda ningún año válido.
* **Años base recomendados:** los dos últimos ejercicios con datos (2025 y 2026 al corte). Un año parcial sesga el peso si los dos ramos no se contabilizan con la misma cadencia; por eso el histórico debe traer el mes, el año parcial se descarta cuando no alcanza los meses mínimos, y los negocios cuyos pesos cambian entre métodos quedan en `REVISAR` (abajo). Con un solo año base el método es la lectura más plausible de la "distribución del año anterior" de 2026.
* **Alternativas parametrizadas:** `ultimo` (sólo el último año válido) y `promedio_simple` (promedio de las participaciones anuales). El layout permite fijar el método por negocio (`INCLUIR` + `METODO`) cuando el negocio decide, por ejemplo, usar sólo el último año tras una renovación.
* **Sensibilidad y cambio estructural.** El script calcula el peso con los tres métodos (`Sensibilidad_Metodos`) y detecta cambio estructural (un año base mono-ramo y otro bi-ramo). Si los métodos difieren más que la tolerancia o hay cambio estructural, el negocio queda en `REVISAR`: la ponderación por montos sólo "reduce ruido" cuando la mezcla es estable, y amplifica un año atípico cuando no lo es.
* **Credibilidad.** El histórico decide sólo si tiene volumen: la prima histórica base del negocio debe ser al menos el 10 % de su prima presupuestada del año de decisión (o la materialidad, si es mayor), y la razón presupuesto ÷ último año real debe estar entre 1/3 y 3. Fuera de eso el negocio queda en `REVISAR` con el dato visible. Un real diminuto o de un solo año no debe decidir un presupuesto decenas de veces mayor.
* Un ramo ausente del histórico recibe peso 0 (el negocio era mono-ramo en el real).
* Pesos por tipo: se calculan por separado para primas, comisiones y siniestros cuando el histórico los trae; comisiones sin histórico propio válido toman los pesos de primas (coherente con el patrón del cargador: misma razón comisión/prima en ambos ramos).

### Nivel 3. Sin información

El negocio **no se ajusta**. Queda listado en `LLAVEs_Sin_Peso` para que la línea de negocio aporte el dato (nivel 1) o se extraiga su real (nivel 2). No se usa un promedio de cartera, línea o territorio como sustituto: sería atribuir a un contrato específico un porcentaje que no le pertenece (equivale a forzar el agregado). Si el negocio decide aplicarlo de todos modos, debe capturarse como `FORZAR` con esa justificación explícita, de modo que quede visible en la auditoría.

---

## 6. Regla de alcance (qué negocios se ajustan)

La decisión se toma sobre el año fiscal que consume CtaMens (`anio_decision` = 2027) y filas con monto distinto de cero; el reparto, una vez decidido, se aplica a todos los años fiscales del negocio. Para cada LLAVE con prima en 71 o 73, en este orden:

1. `EXCLUIR` en el layout → `NO_AJUSTAR` (motivo registrado).
2. Sin pesos válidos de primas (nivel 1 ni 2) → `SIN_PESO`.
3. Sin filas con monto en el año de decisión → `NO_AJUSTAR`.
4. `INCLUIR` o `FORZAR` en el layout → `AJUSTAR` (con justificación obligatoria; `INCLUIR` admite `METODO`).
5. LN excluida (LN04004, cuyo centro de beneficio reescribe CtaMens) → `NO_AJUSTAR`.
6. Sin primas de referencia en 71/73 (sólo comisiones o siniestros) → `REVISAR`.
7. |share73 presupuestada − share73 de los pesos| ≤ tolerancia (5 puntos porcentuales) → `NO_AJUSTAR`.
8. Prima 71+73 del negocio en el año de decisión por debajo de la materialidad (parámetro; 0 por defecto; el precedente 2026 usó 100,000 MXN anuales) → `NO_AJUSTAR`.
9. Reclasificación total (histórico ≥ 1 − tolerancia en un ramo y presupuesto ≥ 1 − tolerancia en el otro) → `REVISAR`: es un cambio de ramo completo que debe confirmar el negocio. El umbral es la misma tolerancia de la regla 7, para que un 97/3 no se mueva automáticamente.
10. Histórico poco creíble (volumen o razón presupuesto ÷ real fuera de banda, sección 5) → `REVISAR`.
11. Pesos sensibles al método o cambio estructural entre años base → `REVISAR`.
12. Contrato nulo en negocio no facultativo (la LLAVE agrupa varios contratos) → `REVISAR`; pedir el número de contrato a la LN.
13. Facultativo (ZTIPOREAS = 3; la LLAVE agrupa todo el facultativo de la cedente en la LN) → `REVISAR`; preferir el slip (`FORZAR`).
14. El negocio **ya trae ambos ramos** (partición explícita del cargador) → `REVISAR`: el real histórico estima la mezcla pasada, no el contrato vigente; una partición cargada deliberadamente no se sobreescribe sin confirmación.
15. En otro caso (negocio cargado en un solo ramo cuya historia creíble y estable muestra ambos) → `AJUSTAR`.

Los casos `REVISAR` se resuelven con `INCLUIR` (aplicar los pesos) o `EXCLUIR` (dejar) en el layout, con justificación. Los `AJUSTAR` automáticos se revisan en el `--dry-run` junto con `Validacion_Tendencia` (banderas inspiradas en los umbrales 2026: un ramo sube ≥ +60 % y el otro cae ≤ −40 % con la suma dentro de (−40 %, +60 %); ramo que desaparece o aparece) antes de la corrida productiva. La tolerancia hace explícito el umbral; cuando el histórico trae tres o más años, el script reporta además una tolerancia sugerida por el dato (percentil 90 del rango interanual de la participación en los negocios con ambos ramos). Toda decisión queda en `Alcance_LLAVEs` con su motivo y los datos que la sustentan (participaciones, prima histórica, razón, años válidos, sensibilidad).

---

## 7. Mecánica fila a fila

Para cada LLAVE en `AJUSTAR`, cada tipo con política de redistribución, cada firma f y cada signo s de las filas de esa firma:

```
pool_f,s            = Σ_{ramo ∈ {71,73}} AMOUNT(f, ramo, s)                 (filas existentes con ese signo)
target_f,s,ramo     = pool_f,s × w(LLAVE, tipo, ramo)
AMOUNT_nuevo(f,s,r) = target_f,s,r                                            (si la fila (f, s, r) existe)
                    = clon de la fila mayor del pool con PROFTCTR = código(r) y AMOUNT = target_f,s,r   (si no existe)
```

* Separar por signo conserva la estructura contable: un reverso se reparte con su propio signo y con los mismos pesos, que es exactamente lo que haría el cargador con cada movimiento.
* Si en un pool hubiera varias filas del mismo ramo, el target del ramo se reparte entre ellas en proporción a su monto original absoluto.
* Redondeo: los montos nuevos se redondean a 2 decimales (redondeo de pandas, "half-even"; si el insumo trajera más decimales el script usa el máximo observado) y el residuo `pool − Σ AMOUNT_nuevo` se asigna a la fila de mayor monto del pool, de modo que **la suma del pool es exactamente el pool**. Es equivalente al método 2026 sin el redondeo de Pct a 6 decimales: conserva exactamente el total 71 + 73 por firma y por negocio; los totales por ramo pueden diferir en centavos por acumulación de redondeo (control 3, tolerancia 0.001 sobre la participación).
* Un clon cuyo monto redondea a cero no se crea (el residuo queda en la fila existente).
* Centro de beneficio del clon: el observado en la misma LLAVE para ese ramo; si no existe, el más frecuente del archivo; en último caso `A0{ramo}000000`. Con `Subramo.csv` el script verifica que el código exista en él (de lo contrario CtaMens convertiría `Ramo2` a decimal para toda la base) y se detiene si falta.
* Un ramo con peso 0 deja su fila en 0.00. Por defecto esas filas **se conservan** en el csv (CtaMens las ignora porque filtra `AMOUNT ≠ 0`), de modo que todas las filas originales conservan su posición y su `_ID` en CtaMens; las filas posteriores a un clon no se mueven porque los clones van al final. `PptoTecnico2027_Ced.csv` mostrará esas filas con `PRCT_CED = 0`.
* Las filas no afectadas son idénticas en valor y tipo al leerlas como lo hace CtaMens; el texto del csv se reserializa (separadores de miles, `.0`), así que la prueba de "fuera del alcance intacto" es el control 1, no un diff de texto.

**Ejemplo.** LLAVE `1-40-16-LN04001`, firma (202703, GL 61, ZSUSCYEAR 2026, R01, …), sólo ramo 71 con −30,762.00. Histórico real 2025–2026: 71 = 40 %, 73 = 60 % de una prima comparable con la presupuestada. Resultado: fila 71 recalculada a −12,304.80; fila 73 clonada con −18,457.20; suma −30,762.00.

---

## 8. Comisiones

Se redistribuyen con la misma mecánica. Peso: el propio de comisiones si el histórico lo trae y es válido (así lo hizo 2026 con la columna *Monto Comisiones* del TD); si no, el de primas, y queda documentado en `ORIGEN_PESO`. Un `FORZAR` del layout gobierna también las comisiones (con `PESO_COMISION` o, en su defecto, con los pesos de primas forzados), para que un negocio no quede con una mezcla distinta entre primas y comisiones. En el extracto la razón comisión/prima es la misma en ambos ramos dentro de cada negocio.

## 9. Siniestros y matrices que dependen de la base

* En el presupuesto no hay siniestros (GL 54) para 71/73: los siniestros catastróficos se generan en CtaMens con las matrices `xDnEvCat` y `xDnAttritional` por centro de beneficio y región, prorrateadas por la prima GL 61 de cada (mes, PROFTCTR, región). Esas matrices, igual que `xDnCostoXL` y `xDnRecup` (costos y recuperaciones XL, indexadas por la firma `ContratosXL`), **se dimensionan a partir de la propia corrida de CtaMens** (`base_ctoxl.xlsx`, `TD_CtaMens_act`, `Insumos_EvCat_Dim`). Por tanto, tras la redistribución las combinaciones nuevas (clones en un centro de beneficio y región, o en una firma XL, que antes no tenían prima) no tienen fila en las matrices y CtaMens les asigna costo XL y siniestro CAT **cero en silencio**, mientras el ramo donador conserva el costo dimensionado con la prima inflada. **El procedimiento es de dos pasadas:** CtaMens sobre la base redistribuida → regenerar las cuatro matrices con esa base → CtaMens de nuevo (sección 13).
* Mover prima entre 71 y 73 no mueve el total de siniestro CAT de cada centro de beneficio y región mientras esa clave siga poblada; si una clave se vacía (reclasificación total confirmada) su valor deja de asignarse, y si aparece una clave nueva con valor en la matriz, ese valor aparece de golpe. Por eso la trazabilidad lista tanto las combinaciones nuevas como las que desaparecen.
* Si en la base completa existieran filas GL 54 para 71/73 (siniestros atricionales cargados por la LN), la política por defecto es repartirlas con los pesos de primas (mantiene la siniestralidad por ramo que asumió la LN); alternativas: pesos propios del histórico de siniestros (ruidosos por eventos CAT) o no tocarlas (como 2026).

---

## 10. Interacciones con `CtaMens.py` y la cadena aguas abajo

El centro de beneficio es la vía por la que el ramo entra a CtaMens (tras el remapeo de LN04004). Al mover prima entre 71 y 73 cambian:

| Componente | Llave que usa | Efecto de la redistribución | Verificación previa (hoja `Verif_Insumos_CtaMens`) |
|---|---|---|---|
| `Subramo.csv` → Ramo, Ramo2, RamoN | PROFTCTR | Los clones deben usar un PROFTCTR existente en Subramo; si no, Ramo2 se vuelve decimal para **toda** la base y rompen LLAVE1 y la matriz XL | Bloqueante: el script se detiene si falta |
| Cesión tradicional (LLAVE1 = LN-Ramo2-Territorio-TipoRea) | depende del ramo | La prima movida toma la cesión del ramo receptor (correcto) | `Cesion.csv` con `Pais.csv` y `Subramo.csv`: existencia de la LLAVE1 exacta de los clones |
| Cesión histórica (LLAVE_CESION_HIST incluye Ramo2) | depende del ramo | Si no hay entrada histórica para el ramo receptor, el clon cae a la cadena de fallbacks (retro específica, binder, tabla tradicional, PI) mientras la fila donadora conserva su % histórico | `Porc_Cesión_Hist.xlsx`: existencia de la llave exacta (nulos como en CtaMens) |
| CesionPI (PRUS) por Ramo | depende del ramo | Toma el % PI del ramo receptor | `CesionPI.csv`: fila para ambos ramos |
| Retro específica / Binder (LLAVE2, LLAVE3) | no dependen del ramo | Sin cambio | — |
| Costos XL (firma `ContratosXL` con Ramo2; `FACTOR_XL` = retenida ÷ retenida total por firma y mes) | depende del ramo si 71/73 son encabezados de `xMatCostoXL` | El costo XL por (firma, mes) es exógeno mientras la firma siga poblada; cambia el reparto de **todas** las filas de las firmas afectadas (la retenida total cambia aunque la prima total no) | `xMatCostoXL` + `xDnCostoXL` / `xDnRecup`: existencia de la firma de los clones; regenerar matrices (sección 9) |
| EvCat / AttCat / SinCatCed | PROFTCTR + ZREGIONRP; RamoN | Total exógeno por ramo-región mientras la clave siga poblada; cambia el prorrateo a **todos** los negocios de esa clave, ajustados o no | `xDnEvCat` / `xDnAttritional`: existencia de PROFTCTR+región de los clones; regenerar matrices |
| ConGtosRetro | cedida total del mes | Cambia si la cesión del ramo receptor difiere | Informativo |
| `PptoTecnico2027_Ced.csv`, `PptoTecnico2027.xlsx` | todas las columnas | Tendrán más filas (clones); por eso el csv de salida no lleva columnas extra | Límite de 1,048,576 filas de Excel si la base completa es grande |
| `ConsultaP.xlsx` → reservas (RRC, reserva catastrófica por PROFTCTR/región) | PROFTCTR, región, mes | Cambian la prima retenida y el siniestro CAT por ramo y, con ellos, los saldos de reservas por ramo y el estado de resultados por LN | Comparar resúmenes de reservas por ramo antes/después (sección 11) |

---

## 11. Controles y validaciones

Automáticos, independientes del cálculo (el script se detiene sin escribir el csv si fallan; la trazabilidad se escribe de todos modos con el sufijo `_CONTROL_FALLIDO` para diagnosticar):

1. Las filas fuera del alcance son idénticas al original en todas las columnas.
2. Conservación exacta por **firma** en todo el archivo; cuadre por LLAVE × tipo × mes × año fiscal, por tipo × año y global (diferencia 0.00).
3. La participación resultante de cada negocio ajustado y tipo es igual al peso aplicado (tolerancia 0.001); los negocios no ajustados conservan su participación.
4. Conteo de filas = original − filas a cero omitidas + clones.
5. Pesos válidos y únicos; layout completo y justificado; montos numéricos y no vacíos; centros de beneficio de los clones presentes en `Subramo.csv`; salida distinta del insumo salvo con respaldo.
6. Anti doble aplicación: el script registra el sha256 de cada csv que genera y se niega a procesar un csv de entrada que coincida con una salida previa.

Diagnósticos de insumo (en el log y el resumen): cobertura (porcentaje de la prima del año de decisión que pertenece a negocios con pesos; una cobertura baja indica histórico mal codificado y se advierte por debajo del 50 %) y firmas huérfanas (firmas con un solo ramo en negocios que traen ambos; si son muchas, alguna columna de la firma difiere entre ramos y la mecánica no aplica tal cual).

De lectura obligatoria en la trazabilidad:

7. `Alcance_LLAVEs`, `LLAVEs_Revisar`, `LLAVEs_Sin_Peso`: cuántos negocios se ajustaron, cuántos esperan confirmación, cuántos no tienen dato y por qué.
8. `Sensibilidad_Metodos` y `Validacion_Tendencia`: por negocio. No se publica la participación global resultante bajo cada alternativa; aun así ese agregado es calculable con las hojas, por lo que la salvaguarda real es la gobernanza: parámetros aprobados por escrito **antes** de la corrida productiva (sección 12).
9. `Control_Participacion`: participación 73 antes/después por tipo, año fiscal, región y LN. **Validación, no objetivo.** Criterio de aceptación escrito de antemano: si la participación global 2027 queda fuera del rango 2023–2026 ampliado por la tolerancia, la acción es revisar `LLAVEs_Revisar` y `LLAVEs_Sin_Peso` y pedir datos de nivel 1, nunca cambiar parámetros para acercarse al número.
10. `Combos_Nuevos`, `Combos_Desaparecen`, `Verif_Insumos_CtaMens` (sección 10).
11. `Detalle_Filas`: muestreo de filas recalculadas y clonadas contra el archivo original.
12. Post-CtaMens, por niveles: AMOUNT, CEDIDA y RETENIDA por negocio (sólo cambian los ajustados); EvCat, AttCat y SinCatCed por (PROFTCTR, región, mes) y CostoXL/RecuXL por (firma XL, mes): los totales por clave deben ser invariantes salvo claves nuevas o desaparecidas, aunque cambie el reparto entre negocios (el derrame a negocios no ajustados es esperado y debe documentarse); ConGtosRetro por mes; reproducir la captura `Res_Rec_Ajustes_Form_f` (totales por ramo, crecimientos y participación vs 2023–2026); comparar `ConsultaP.xlsx` y los resúmenes de reservas por ramo antes/después.
13. Comparación con 2026: lista de LLAVEs ajustadas en 2026 (`LAYOUT_RED`, homologando el contrato nulo `''` → `0`) contra las de 2027 y qué hizo el TD 2026 con los ramos distintos de 71/73 de esas LLAVEs; un negocio ajustado en 2026 que vuelve a aparecer mal cargado en 2027 debe explicarse y corregirse en el insumo de la LN. Si se recuperan `TD.xlsx` y `Base_1.xlsx`, back-test: participación implícita del TD contra el real por negocio, y si Σ TD por LLAVE-tipo conservó el total mensual.

---

## 12. Insumos requeridos y gobernanza

| # | Insumo | Para qué | Quién |
|---|---|---|---|
| 1 | `PptoTecnico2027.csv` completo (todas las LN y regiones), confirmado como el extracto SAP **original** (fecha y sha256), no una versión ya intervenida | Universo real del problema; anti doble aplicación | Planeación Financiera |
| 2 | **Histórico real por LLAVE × ramo × año y mes** de primas, comisiones y siniestros, 2024–2026 al corte, con ZTIPOREAS, ZCEDENTE, ZCONTRATO (0 para facultativos), FUNCAREA, PROFTCTR o DescRamo, periodo AAAAMM, cuenta y monto (estructura de `Base_1.xlsx` o de la consulta real de SAP BW). Se arma con `0a_Actualizar_Base1.py`: Base_1 del año pasado más el real del año, validado por traslape | Pesos de nivel 2, completitud de meses, sensibilidad, tendencia | Planeación Financiera / Reporting |
| 3 | `Subramo.csv` 2027 (con Ramo2 y RamoN) y `Pais.csv` | Ramo exacto de CtaMens; verificación de LLAVE1 | Planeación Financiera |
| 4 | Participación contractual por ramo de los negocios en `REVISAR` y `SIN_PESO` (slip, SIREC, insumo de la LN) | Pesos de nivel 1 (layout `FORZAR`) y confirmaciones (`INCLUIR`/`EXCLUIR`) | Suscripción / líneas de negocio |
| 5 | Output actual de CtaMens (`CtaMens_2027.xlsx`, `ConsultaP.xlsx`) y la hoja de totales por ramo de la captura | Validación antes/después | Planeación Financiera |
| 6 | Insumos 2026: `LAYOUT_RED.xlsx`, `TD.xlsx` / `TD_RED.xlsx`, consolidados, `Base_1.xlsx` | Coherencia con 2026 y back-test | Archivo del equipo |
| 7 | `Cesion.csv`, `Porc_Cesión_Hist.xlsx`, `CesionPI.csv`, `xMatCostoXL.xlsx`, `xDnCostoXL.xlsx`, `xDnRecup.xlsx`, `xDnEvCat.xlsx`, `xDnAttritional.xlsx` | Verificación previa de la sección 10 (el script las usa si están en disco) | Planeación Financiera |
| 8 | Fuente de las matrices XL y EvCat (`Insumos_Cesión_v1_Dim_F.xlsb`, `Insumos_EvCat_Dim.xlsx`) | Regenerarlas entre las dos pasadas | Planeación Financiera |
| 9 | Artefactos 2027 del pipeline anterior, si existen: `Outputs\LAYOUT_RED.xlsx`, `Outputs\Cedentes\RecMens_consolidado.xlsx`, salidas `RedistCed` | Saber qué se corrió antes sobre el presupuesto 2027 | Planeación Financiera |
| 10 | **Parámetros aprobados** (años base, método, tolerancia, materialidad, políticas, bandas de credibilidad) con responsable y fecha, y la tabla de pesos congelada (`Pesos_Ramo_TEV_HyOR.xlsx`, hoja `Pesos`) revisada | Gobernanza: la corrida productiva se hace con `--aprobacion "responsable, fecha"` y, de preferencia, con la tabla de pesos congelada (opción B) en vez del histórico crudo | Responsable del presupuesto |

---

## 13. Procedimiento operativo

0. Actualizar la historia real: `0a_Actualizar_Base1.py` une la Base_1 del año pasado con el real del año en curso. La extracción nueva incluye 2 o 3 meses que ya están en la Base_1 previa; el script exige que esos meses cuadren (1 % por métrica y por ramo) antes de escribir, de modo que la historia nueva tenga la misma definición que la anterior. Revisar en su libro de control `Traslape`, `Meses_por_Anio` y `Particip_TEV_HyOR`.
1. Confirmar que `Inputs\PptoTecnico2027.csv` es el extracto original y colocar los insumos en `5_Generacion\Inputs\Redistribucion\`.
2. Correr `python 0_Redistribucion_TEV_HyOR.py --dry-run`. Revisar `Alcance_LLAVEs`, `LLAVEs_Revisar`, `LLAVEs_Sin_Peso`, `Sensibilidad_Metodos`, `Validacion_Tendencia`, la cobertura y la tolerancia sugerida.
3. Resolver con las líneas de negocio los casos `REVISAR` y `SIN_PESO` (nivel 1 cuando exista) y capturar en el layout con justificación; muestrear contra slip/SIREC los negocios `AJUSTAR` de mayor prima.
4. Fijar y aprobar por escrito los parámetros; congelar los pesos (`Pesos_Aplicados` → `Pesos_Ramo_TEV_HyOR.xlsx`) si se quiere una corrida reproducible sin histórico crudo.
5. Corrida productiva con `--aprobacion`. Revisar `Control_Participacion`, `Control_Share_LLAVE`, `Combos_Nuevos`, `Combos_Desaparecen` y `Verif_Insumos_CtaMens`; completar las llaves de cesión que falten para el ramo receptor.
6. Apuntar `CtaMens.py` al archivo redistribuido (o usar `--sobrescribir-input`, que respalda el original). **Pasada 1** de CtaMens → regenerar `xDnCostoXL`, `xDnRecup`, `xDnEvCat`, `xDnAttritional` con la base redistribuida → **pasada 2** de CtaMens.
7. Validación post-CtaMens por niveles (sección 11, punto 12), reservas incluidas, y comparación con 2026.
8. Archivar junto al presupuesto: csv original, csv redistribuido, libro de trazabilidad, detalle fila a fila, log, layout, histórico, parámetros aprobados, matrices regeneradas y este documento.

---

## 14. Limitaciones y supuestos

* **El histórico como estimador.** La participación real pasada de un negocio es la mejor evidencia disponible de su mezcla de ramos, pero no es una garantía: renovaciones con cambio de alcance, contratos nuevos, años con eventos CAT y años parciales la alteran. Las reglas de credibilidad, sensibilidad, cambio estructural y meses mínimos reducen el riesgo; el nivel 1 (condición contractual) y el layout lo cierran.
* **Punto ciego.** El método corrige inconsistencias entre presupuesto y real; es ciego a errores comunes a ambos. Si la contabilidad asignara el ramo con la misma parametrización por contrato que alimentó al cargador, un negocio mal parametrizado se vería mono-ramo en ambos y quedaría en `NO_AJUSTAR`. La estabilidad del 58.4–58.8 % en 2023–2026 sugiere que el real no comparte el sesgo, pero debe confirmarse con Contabilidad, y el único remedio es el nivel 1: muestreo de slips de los negocios mono-ramo de mayor prima.
* **Facultativos y contratos nulos.** La LLAVE 2026 agrupa bajo contrato 0 todo el facultativo de una cedente y LN (hasta 5 corredores en el extracto) y, en al menos un caso, varios contratos proporcionales distintos. Por eso quedan en `REVISAR`; la extensión natural es incluir el corredor o el año de suscripción en la LLAVE cuando el histórico lo permita.
* **Un solo porcentaje por negocio.** En el extracto el porcentaje por ramo es idéntico por año de suscripción, corredor, moneda y año fiscal, así que un peso por LLAVE-tipo basta. Si el real mostrara mezclas distintas por año de suscripción, habría que refinar la llave.
* **Matrices y reservas.** Las matrices XL y EvCat se dimensionan con la base; sin la segunda pasada el siniestro CAT y el costo XL del ramo receptor quedan en cero. El efecto llega a reservas por ramo.
* **Cesión.** La prima movida toma la cesión del ramo receptor según las tablas de CtaMens; si faltan llaves para el ramo receptor, la cesión cae a fallbacks. `Verif_Insumos_CtaMens` existe para completarlas antes de correr CtaMens.
* **Coherencia con 2026.** Se conserva la mecánica, no los números: los montos objetivo de 2026 se capturaron a mano con una fórmula no documentada y tocaban todos los ramos de la LLAVE, así que no es posible (ni deseable) reproducirlos.
* **Validación de tendencia.** Es una validación inspirada en los umbrales 2026 aplicada real→presupuesto; las banderas 2026 propiamente dichas (YoY sobre el real 2020–2026, outliers mensuales, CAGR) requieren el histórico mensual completo y pueden calcularse aparte.

---

## 15. Decisiones pendientes (con recomendación)

| Decisión | Opciones | Recomendación |
|---|---|---|
| Años base del histórico | 2026 solo / 2025 + 2026 al corte / 2024–2025 cerrados | **2025 + 2026 al corte con histórico mensual** y método ponderado; si 2026 no alcanza 8 meses en un negocio, el script lo excluye solo |
| Tolerancia de alcance | 5 pp / la sugerida por el dato (p90) | **5 pp** en la primera corrida; comparar con la sugerida por el dato y fijar por escrito |
| Comisiones | pesos propios con fallback a primas / siempre primas | **Propios con fallback** (coherente con 2026 y con el dato) |
| Siniestros GL 54 (si existen) | pesos de primas / propios / no tocar | **Pesos de primas**; si se prefiere coherencia estricta con 2026, "no tocar" y documentarlo |
| Años fiscales del reparto | todos / sólo 2027 | **Todos** (evita saltos entre años en el mismo negocio) |
| Matrices XL y EvCat | dos pasadas con regeneración / una pasada | **Dos pasadas** (sección 9) |
| Negocios sin información | dejar sin ajuste / promedio de cartera vía FORZAR | **Dejar sin ajuste y gestionarlos con la LN** |
| Negocios ya cargados en ambos ramos que difieren del histórico | sobreescribir automáticamente / `REVISAR` y confirmar | **`REVISAR` y confirmar** |
| Reclasificación total | automática / `REVISAR` y confirmar | **`REVISAR` y confirmar** |
| Materialidad | 0 (todo) / 100,000 MXN anuales (precedente 2026) | **0** en la primera corrida para ver el universo completo; fijar después, por escrito, antes de ver agregados |
| Facultativos y contratos nulos | `REVISAR` (defecto) / ajuste automático / LLAVE con corredor | **`REVISAR`** y pedir slip o número de contrato |
| Gobernanza | histórico crudo en cada corrida / pesos congelados aprobados | **Pesos congelados aprobados** para la corrida productiva |

---

## 16. Revisión independiente de esta metodología y del script

* La metodología se construyó a partir de tres propuestas independientes (rigor actuarial y contable; continuidad con 2026; auditabilidad y control) evaluadas por dos jueces, y después sometida a tres refutaciones adversariales (validez estadística, interacciones con CtaMens, auditoría y coherencia 2026). Las objeciones válidas incorporadas en esta versión: decisión sobre el año que consume CtaMens; credibilidad y banda presupuesto/real; umbral de reclasificación total igual a la tolerancia; sensibilidad y cambio estructural como causa de revisión; meses mínimos por año; `FORZAR` gobierna todos los tipos; justificación obligatoria también para `INCLUIR`; contratos nulos y facultativos en revisión; dos pasadas por las matrices XL y EvCat; reservas como consumidor; derrame a negocios no ajustados en el control post-CtaMens; gobernanza de parámetros y pesos congelados; punto ciego del método; precisión de las cifras y de las afirmaciones de coherencia con 2026.
* El script se sometió a tres rondas de revisión adversarial (corrección numérica, robustez en el entorno Windows/pandas 2.0 a 3.0, consistencia con lo documentado, integración con CtaMens) y a una verificación independiente que no reutiliza su código, más 24 casos límite automatizados (`pruebas/`). Los hallazgos confirmados (histórico con separador de miles leído como cero, controles autorreferentes, años con reversas, layout con filas en blanco, respaldo sobreescribible, filas en cero, montos enteros, clones de monto cero, escala de la trazabilidad, entre otros) están corregidos en la versión 1.2.

---

## Anexo A. Glosario

* **TEV**: Terremoto y Erupción Volcánica (ramo 73, centro de beneficio `A073000000`).
* **HyOR / HyORH**: Hidrometeorológicos y Otros Riesgos (ramo 71, `A071000000`).
* **CtaMens**: script que genera la cuenta mensual presupuestada (prima tomada, cedida, retenida, costos XL, siniestros CAT, gastos) a partir del presupuesto técnico, y la base `ConsultaP.xlsx` para reservas.
* **GL 61 / 53 / 54**: cuentas de primas, comisiones y siniestros (prefijo de `/ERP/GL_ACCT`).
* **FISCYEAR / CALMONTH**: año fiscal y mes calendario de la fila presupuestada.
* **ZSUSCYEAR**: año de suscripción del contrato.
* **TD**: "tabla dinámica" con la distribución del año anterior usada en 2026.
* **Firma / pool**: ver sección 4.
