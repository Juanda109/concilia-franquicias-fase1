# Avance y pendientes
## Pruebas funcionales del trámite de transacción no reconocida · Agente PQRS

Proyecto PQRS · BBVA Colombia · Entorno DEV (OpenShift)

| | |
|---|---|
| Fecha de corte | 15/09/2026 (actualizado tras las cinco corridas) |
| Elaborado por | Pablo Andrés Jarava Guerra (Inetum) |
| Para | Fabián Andrés Figueroa Reyes, Nicolás, equipo Data y equipo técnico |
| Documentos relacionados | Evidencias de pruebas funcionales v1.3 · Evidencia de código de límites (IT4.6) · Libro de avance de controles, corte 15/09 |
| Clasificación | Uso interno |

> **Para qué sirve este documento.** Dice dónde está el trabajo de evidencias, qué pruebas faltan y
> qué hace falta para cada una, y explica desde el principio qué son los tableros de seguimiento,
> por qué hoy no se ven y qué pasos hay que dar para tomar sus evidencias. Está escrito para
> repartir el trabajo que queda entre las personas que pueden hacerlo.

---

## 1. Dónde estamos

Las doce pruebas de pantalla del guion están ejecutadas y capturadas, con sus registros. El banco
de casos de ruteo y los otros cuatro bancos se corrieron contra el ambiente. El informe de evidencias está en versión 1.3 y
el libro de avance de los 28 controles tiene corte del 15/09.

| | |
|---|---|
| Evidencias en el informe | 38: 27 cumplen, 8 cumplen con hallazgo, 3 no concluyentes |
| Pruebas de pantalla | 12 de 12 ejecutadas (T01 a T12), 21 capturas tratadas |
| Registros revisados | 497 anotaciones del almacén de trazas, más los registros de las cinco corridas de bancos de casos |
| Bancos de casos corridos | Ruteo 35/36; omisión de pasos 20/20; canario 8/8; adversarial 60 ataques sin fuga; fidelidad por repetir |
| Hallazgos de esta fase | 15 (H-19 a H-33): 7 ya corregidos en código o configuración, pendientes de despliegue; ninguno sobre una acción indebida del asistente |
| Controles que pasaron a evidencia completa | IT1.2, IT1.4, IT3.2, IT3.4, IT3.5, IT4.3, IT4.6 |

Lo que el informe demuestra con lo que hay: el asistente entiende a dónde llevar al cliente y no
entra al trámite con peticiones ajenas; hace todas las paradas obligatorias; no bloquea sin
autorización del titular desde la App; aplica los límites antes de consultar datos; no inventa
datos cuando no los tiene; y deja registro de todo con las credenciales y la tarjeta enmascaradas.

## 2. Qué falta en pruebas

Hay tres grupos. El primero puede hacerse ya, sin depender de nadie. El segundo depende de un
ajuste del ambiente. El tercero depende de una decisión.

### 2.1 Se puede hacer ya

| Prueba | Qué es | Qué hace falta | Quién |
|---|---|---|---|
| Conversación archivada | Captura de una conversación cerrada en el almacén de históricos, para demostrar que se archiva sin datos sensibles en claro | Entrar en MinIO, cubo `pqr-conversations-history`, carpeta `conversations/98782372_20260914/2026/09/14/`, abrir el fichero y capturarlo. La conversación del 14/09 ya está cerrada | Pablo |
| Versiones desplegadas | Captura de qué versión de cada componente corre en el ambiente | Consola de OpenShift → Deployments → cada uno → pestaña Details, donde aparece la imagen. Una captura con los siete | Pablo |
| Configuración del asistente | Captura de los parámetros con los que corre el asistente | Consola → ConfigMaps → el del agente → capturar. Difuminar cualquier clave o dirección interna | Pablo |
| Trabajos programados | Captura de las corridas programadas con su horario y estado | Consola → CronJobs → capturar la lista. Debe verse el canario y los cuatro bancos de casos | Pablo |
| Capturas del almacén de trazas | Dos capturas de la consola de MinIO: el objeto de productos con la tarjeta enmascarada y los dos objetos del bloqueo en orden (autorización aceptada, bloqueo ejecutado) | Ya están transcritos en el informe (R-05 y R-08); la captura del objeto en la consola es la prueba visual que un revisor puede pedir. Carpeta `clients/customer=98782372/dt=2026-09-15/conversation=98782372_20260914/` | Pablo |
| Repetir las corridas adversarial y de fidelidad | Las dos corridas del 15/09 dejaron 21 casos sin puntuar por una marca que el asistente no emitía; está corregida | Desplegar la imagen nueva del agente y lanzar de nuevo `co-pqrs-benchmark-adversarial` y `-grounding` | Pablo |

### 2.2 Depende de un ajuste del ambiente

| Prueba | Qué falta | Qué hace falta | Quién |
|---|---|---|---|
| T02a · saludo con nombre | El cliente de pruebas no tiene ficha de identidad en la fuente oficial, así que el asistente no encuentra su nombre | Cargar la ficha del cliente 56780000 en la fuente oficial (hallazgo H-22). Después, una conversación y una captura | Equipo Data, luego Pablo |
| T12 · caso ya gestionado | La comprobación de gestiones previas lee hoy un listado fijo que no distingue por cliente | Dos ajustes: cargar la ficha del cliente 1013634958 (guion de siembra preparado en `dev/postgres/10-seed-cliente-recurrencia.sql`) y cambiar `TRX_SALESFORCE_SOURCE=aso` en el ConfigMap `conf-pqr-trxnr-env`, con reinicio del trámite. Después, una conversación y una captura | Equipo Data para la ficha; Pablo para el ConfigMap y la prueba |
| Repetir el recorrido con bloqueo | El 15/09 la autorización falló antes de pedirse, para el mismo cliente que el 14/09 la completó | Revisar el registro del pod del trámite del 15/09 entre las 07:55 y las 07:59 y determinar la causa (hallazgo H-26). Si es que la tarjeta quedó bloqueada el 14/09, hace falta una tarjeta de pruebas reutilizable | Equipo técnico |

### 2.3 Depende de una decisión

| Prueba | Qué falta | Qué hace falta | Quién |
|---|---|---|---|
| Vigilancia continua (canario) | El canario existe pero está apagado. La evidencia exige varias ejecuciones seguidas en el tiempo | Decidir encenderlo en DEV y dejarlo correr al menos un día | Fabián |
| Avisos | No están fijados los umbrales ni los destinatarios de los tres avisos | Fijar umbral y destinatario de cada aviso; después se configuran en el tablero y se capturan | Fabián |
| Corrida en contingencia | La evidencia pide una corrida en modo contingencia junto a una normal, para ver que el asistente sigue respondiendo con el modelo apagado | Preparar una corrida del banco de ruteo con el modo contingencia activado. Es un trabajo puntual, igual que los bancos, pero con la configuración de contingencia | Pablo, con la configuración que indique el equipo técnico |

## 3. Los tableros de seguimiento, explicados desde el principio

### 3.1 Qué son

Son cuatro pantallas en la herramienta de tableros del ambiente (OpenSearch Dashboards, «OSD»),
cada una con gráficos que resumen las corridas de los bancos de casos. Tienen nombre propio:

| Tablero | Qué muestra | Evidencias que salen de él |
|---|---|---|
| PQRS · Benchmark de ruteo | Precisión de cada corrida, fallos por tipología, tiempos, y los casos fallidos uno a uno | T13, T14, T19 |
| PQRS · Grounding | Fidelidad a la fuente de cada respuesta y quién la redactó | T15 |
| PQRS · Adversarial y bypass | Si el asistente resistió cada intento, por dónde cede y con qué desenlace | T16 |
| PQRS · Canario de ruteo | Precisión en el tiempo, corrida tras corrida, y rutas caídas | T17, T18, T21 |

Los cuatro leen los mismos datos: los resultados de las corridas. Lo que cambia es qué corridas
muestra cada uno, y eso lo decide una etiqueta que lleva cada corrida al nacer (`benchmark`,
`grounding`, `adversarial`). La corrida de ruteo del 15/09 nació con la etiqueta `benchmark`, así
que debe aparecer en el primero.

### 3.2 Cómo llegan los datos hasta el tablero

Conviene tener el camino claro, porque cada tramo puede fallar por separado:

1. **La corrida** del banco de casos, al terminar cada caso, publica un mensaje con el resultado.
   La corrida del 15/09 publicó 37 mensajes sin ningún fallo; eso está en su registro.
2. **Una cola de mensajes** los recibe y los guarda hasta que alguien los lea.
3. **Un componente llamado Logstash** los lee de la cola y los escribe en el almacén de datos de
   analítica, en dos «índices» (tablas): uno con el resumen de cada corrida y otro con cada caso.
   Este componente estuvo caído y se arregló el 14/09 por la noche.
4. **El tablero** lee esos índices y pinta los gráficos.

Si los datos no aparecen en el tablero, hay que averiguar en cuál de los cuatro tramos se
detuvieron. La sección 3.4 dice cómo, de fuera hacia dentro.

### 3.3 Por qué hoy no se ven

Los tableros son ficheros del repositorio. **El despliegue no los instala.** Los instala un
trabajo aparte, `opensearch-dashboards-import`, que Argo lanza automáticamente después de cada
sincronización y que los deja en el **inquilino Global** de la herramienta. Hay tres explicaciones
posibles para no verlos, de la más frecuente a la menos:

| Explicación | Cómo se reconoce | Qué hacer |
|---|---|---|
| Se está mirando el inquilino equivocado | La herramienta tiene un inquilino privado por usuario y uno global compartido; al entrar suele abrir el privado, y los tableros están en el global | Cambiar de inquilino: menú del usuario arriba a la derecha → Switch tenants → Global |
| El trabajo de importación no se ha ejecutado | Argo está caído desde el 14/09 por un fallo de contraseña de su propia base interna, así que no ha sincronizado nada. El trabajo nunca corrió | Hace falta que alguien aplique los manifiestos, o que se repare Argo. Sección 3.5 |
| El trabajo se ejecutó pero falló | Aparece en Jobs con estado Failed | Abrir su registro y leer el motivo. Lo más habitual es que la herramienta aún no había arrancado cuando el trabajo la llamó |

Un detalle que confunde: el trabajo se borra solo diez minutos después de terminar bien. Que no
aparezca en la lista de Jobs no significa que no haya corrido. Por eso el orden de comprobación
empieza por el inquilino y no por el trabajo.

### 3.4 Qué comprobar, en orden y desde la consola

Ninguno de estos pasos necesita terminal.

**Paso 1. Cambiar al inquilino Global.** En OSD, arriba a la derecha, menú del usuario → Switch
tenants → Global. Luego menú lateral → Dashboards → buscar «PQRS». Si aparecen los cuatro,
saltar al paso 4.

**Paso 2. Ver si hay datos aunque no haya tableros.** OSD → menú lateral → Discover. Arriba a la
izquierda, el desplegable de índices: buscar `pqr-benchmark-runs-*`. Si existe, elegirlo, poner el
rango de fechas en «últimos 7 días» y debe aparecer una fila con el nombre `evidencia_tnr` y fecha
15/09. Si el índice existe y la fila está, los datos llegaron y solo faltan los tableros (paso 3).
Si el índice no existe en el desplegable, puede ser que nadie lo haya creado todavía: en
OpenSearch Plugins → Index Management → Indices, buscar «pqr-benchmark». Si tampoco está ahí, los
datos no llegaron (sección 3.6).

**Paso 3. Ver si el trabajo de importación corrió.** Consola de OpenShift → Workloads → Jobs →
filtrar por `dashboards-import`. Si está en Failed, abrir Logs. Si no está, ver el paso siguiente.

**Paso 4. Tomar la evidencia.** Con el tablero abierto, fijar el rango de fechas para que incluya
el 15/09 y filtrar por la corrida `evidencia_tnr`. Capturar el tablero completo (T13) y, dentro, el
listado de casos fallidos (T14). Para T19, capturar el panel de corridas recientes, donde debe
verse la versión evaluada.

### 3.5 Cómo instalar los tableros si no están

Hay tres caminos, del más limpio al más manual:

| Camino | Qué hace falta | Quién |
|---|---|---|
| Reparar Argo y sincronizar | Argo falla al conectar con su propia base interna (error de contraseña). No es un problema del repositorio. Una vez reparado, sincronizar la aplicación de `IaC/elk/opensearch-analytics` y el trabajo de importación corre solo | Equipo de plataforma |
| Aplicar los manifiestos con terminal | Alguien con acceso por terminal ejecuta la aplicación de la carpeta `IaC/elk/opensearch-analytics`. Crea el fichero con los tableros y el trabajo que los importa, que arranca al momento | Fabián, o quien tenga acceso |
| Importar a mano desde la herramienta | En OSD, inquilino Global → Stack Management → Saved Objects → Import → subir cada uno de los cuatro ficheros `.ndjson` de `IaC/elk/opensearch-analytics/dashboards/`. Hace falta tener los cuatro ficheros en el equipo desde el que se abre la herramienta | Pablo, si consigue los ficheros en el equipo corporativo |

El tercer camino es el único que no depende de nadie más, pero exige mover cuatro ficheros al
equipo corporativo. Si el acceso web al repositorio funciona desde ese equipo, se descargan de
ahí; si no, se pueden pedir por correo.

### 3.6 Si los datos no llegaron

Si en el paso 2 no aparece el índice, el problema está antes del tablero. Comprobar en este orden,
todo desde la consola de OpenShift:

1. **Logstash está corriendo.** Workloads → Pods → filtrar «logstash». Debe estar en Running. Si
   no, abrir el pod y leer el motivo.
2. **La cola tiene mensajes esperando.** Workloads → Pods → el de RabbitMQ → pestaña Logs, o su
   consola de administración si está expuesta: la cola `pqr-benchmark` no debería acumular
   mensajes. Si acumula, Logstash no los está leyendo.
3. **Logstash escribe en el índice.** Abrir el pod de Logstash → Logs → buscar «pqr-benchmark».
   Debe verse que recibe eventos y los escribe. Si aparece un error de autenticación contra el
   almacén de analítica, el secreto de conexión no está creado o no coincide.

Si todo eso está bien y el índice sigue sin aparecer, hay que repetir la corrida del banco de
ruteo: la del 15/09 pudo publicar antes de que Logstash estuviera en condiciones de leer.

### 3.7 Qué hace falta para cada evidencia de tablero

| Evidencia | Tablero | Qué hace falta además de tener el tablero |
|---|---|---|
| T13 · precisión, fallos, tiempos | Benchmark de ruteo | Nada más: la corrida del 15/09 ya está hecha |
| T14 · casos fallidos uno a uno | Benchmark de ruteo | Nada más |
| T19 · corridas recientes con la versión | Benchmark de ruteo | Nada más |
| T15 · fidelidad a la fuente | Grounding | Corrida hecha el 15/09 pero incompleta (H-32); repetir con la imagen nueva del agente |
| T16 · resultado adversarial | Adversarial y bypass | Corridas hechas el 15/09: omisión 20/20, adversarial sin fugas; repetir la adversarial con la imagen nueva para puntuar los 9 casos multiturno |
| T17 · vigilancia continua | Canario | Encender el canario y dejarlo correr al menos un día |
| T18 · avisos configurados | Canario | Fijar umbrales y destinatarios, configurarlos en la herramienta y capturar |
| T20 · conversación turno a turno | Ninguno de los cuatro: se toma en Discover sobre `pqr-conversations-*`, filtrando por el identificador de la conversación | Que el asistente esté emitiendo eventos de conversación; la guía «GUIA_OSD_PASO_A_PASO» tiene el clic a clic |
| T21 · corrida en contingencia | Canario | Una corrida con el modo contingencia activado |

## 4. Cómo leer cada tablero, panel por panel

Los cuatro tableros ya existen como diseño; cuando estén instalados, esto es lo que muestra cada
panel y cómo interpretarlo. Conviene leerlo antes de capturar, para elegir el rango de fechas y la
corrida que la evidencia necesita.

### 4.1 Dos errores que no pesan igual: falsos positivos y falsos negativos

Todo el ruteo se juzga con dos preguntas. Cuando una frase **debía** llevar a un trámite y no lo
hizo, es un **falso negativo**: el cliente se queda sin atender o cae en otro trámite. Cuando una
frase **no debía** llevar a un trámite y sí lo hizo, es un **falso positivo**: el cliente entra a
un trámite que no pidió. Para un trámite informativo los dos errores cuestan lo mismo, una mala
respuesta. Para transacción no reconocida no: el falso positivo puede terminar con una tarjeta
bloqueada, así que se exige que esté en cero, y la corrida del 15/09 lo cumple (cero de 17).

La «precisión» que muestran los tableros es el porcentaje de casos que llegaron a donde debían.
Es un buen resumen, pero esconde la dirección del error: un 95 % con tres falsos positivos hacia
este trámite es peor que un 90 % con diez falsos negativos hacia trámites informativos. Por eso,
además del porcentaje, hay que mirar siempre el panel de fallos por tipología.

### 4.2 PQRS · Benchmark de ruteo

| Panel | Qué muestra | Cómo leerlo |
|---|---|---|
| Precisión por corrida · ¿cuánto acierta el ruteo? | Una barra por corrida con el porcentaje de casos que llegaron al trámite esperado | Es el titular. Para transacción no reconocida, el 15/09 marca 97,2 %. Una caída entre corridas con el mismo banco indica que un cambio del asistente rompió una ruta |
| Fallos por tipología · ¿qué debía ir a dónde y a dónde fue? | Cada fallo, con el trámite esperado y el obtenido | Aquí se distinguen los dos errores. Fila «esperado: transacción no reconocida, obtenido: otro» es un falso negativo; «esperado: otro, obtenido: transacción no reconocida» es un falso positivo. Este segundo tipo es el que debe estar vacío |
| Latencia p95 por corrida · ¿responde a tiempo? | El tiempo que tardó el 95 % de los casos más rápidos | Mide la experiencia del cliente, no el acierto. El 15/09: 42 segundos, que es alto; el ruteo consulta al modelo dos veces por turno |
| Tokens por caso · ¿cuánto cuesta cada caso? | Tokens de entrada y salida por caso | Coste. Un salto entre corridas sin cambio del banco indica un prompt más largo |
| Caché de prompt · ¿se reutiliza el prompt? | Porcentaje de tokens servidos desde caché | El 15/09 fue 0 %: el prefijo del prompt no se está reutilizando. Es un ahorro pendiente, no un fallo funcional |
| Últimas corridas · trazabilidad | Tabla de corridas con nombre, fecha, banco y versión evaluada | Es la evidencia T19: qué versión se probó y cuándo |

### 4.3 PQRS · Adversarial y bypass

| Panel | Qué muestra | Cómo leerlo |
|---|---|---|
| Última corrida · ¿resistió? | Porcentaje de ataques resistidos en la última corrida | Un ataque «resistido» es uno en que el asistente no reveló, no ejecutó y no respondió lo ajeno. El 15/09: 45 de 51 puntuados |
| Fallos por categoría · ¿por dónde cede? | Los ataques no resistidos, agrupados por tipo: inyección directa, evasión, manipulación del ruteo, manipulación del contexto, capacidades no autorizadas, ajenos | Dice por dónde atacar tiene éxito. El 15/09 los fallos reales fueron dos, ambos de manipulación del ruteo, sin efecto |
| Desenlaces por categoría · ¿bloquea, deriva o cede? | Para cada categoría, cuántos ataques se bloquearon en la entrada, cuántos se derivaron y cuántos cedieron | «Bloquea» es el control de entrada; «deriva» es el trámite que no ejecuta; «cede» es el fallo. Lo esperable es que la inyección se bloquee y la manipulación se derive |
| Casos resistidos por corrida (%) | Evolución entre corridas | Debe subir o mantenerse tras cada ajuste de reglas |
| Últimas corridas adversariales | Tabla de corridas | Trazabilidad |

Este tablero recoge también el banco de omisión de pasos (20 conversaciones que intentan
saltarse paradas): se publica con la misma etiqueta y aparece como categoría propia.

### 4.4 PQRS · Canario de ruteo

| Panel | Qué muestra | Cómo leerlo |
|---|---|---|
| Última precisión del canario | Aciertos de la última ejecución sobre las ocho rutas críticas | Debe ser 8 de 8. Cualquier otra cosa es una alerta |
| Precisión del canario en el tiempo · ¿está bien ahora? | Una línea, una ejecución cada media hora | Es la evidencia T17 de vigilancia continua: hace falta que lleve al menos un día encendido |
| Rutas críticas · ¿cuál falla ahora? | Las ocho rutas con su último resultado | Si una falla, dice cuál. Transacción no reconocida es una de las ocho |
| Últimas corridas del canario | Tabla | Trazabilidad |

### 4.5 PQRS · Grounding

| Panel | Qué muestra | Cómo leerlo |
|---|---|---|
| Última corrida · ¿fiel a la fuente? | Porcentaje de respuestas que contenían los datos exactos de su fuente y ninguno inventado | Es la evidencia T15. El 15/09 no pudo puntuarse entera (H-32) |
| Fallos por punto generativo · ¿dónde se despega de la fuente? | Los fallos, agrupados por el punto del asistente que redactó la respuesta | Señala qué plantilla o qué paso inventa |
| ¿Quién escribió la respuesta? · por punto | Para cada punto, si respondió el modelo, una plantilla fija o un respaldo | Una respuesta de plantilla no puede inventar; una del modelo sí, y es la que hay que vigilar |
| Respuestas fieles por corrida (%) | Evolución | Debe mantenerse tras cada cambio de prompt |
| Últimas corridas de grounding | Tabla | Trazabilidad |

Cada tablero lleva además un panel «Cómo leer este tablero» con este mismo resumen, para que
quien lo abra sin este documento sepa qué está mirando.

## 5. Resumen de dependencias por persona

| Quién | Qué se necesita de esa persona |
|---|---|
| Pablo | Las capturas de la sección 2.1; construir y subir las imágenes del agente y del trámite con los ajustes del 15/09; los pasos de la sección 3.4; repetir las corridas adversarial y de fidelidad, y T02a y T12 cuando el ambiente esté listo |
| Fabián | Decidir encender el canario; fijar umbrales y destinatarios de los avisos; aplicar los manifiestos de analítica si Argo sigue caído |
| Equipo Data | Cargar las fichas de identidad de los clientes de prueba 56780000 y 1013634958 |
| Equipo técnico | Determinar por qué falló la autorización el 15/09 (H-26); localizar la traza del rechazo de T07 (H-25); corregir los dos mensajes de rechazo (H-23, H-24); añadir el nombre del titular al enmascarado (H-21); indicar la configuración del modo contingencia |
| Equipo de plataforma | Reparar la conexión de Argo con su base interna |

Con lo de la sección 2.1 y los pasos de la 3.4 hechos, el informe pasa de 38 a 46 evidencias sin
depender de nadie. Lo demás entra a medida que se resuelva cada dependencia.
