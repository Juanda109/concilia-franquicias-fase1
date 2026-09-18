# Agente PQRS · Trámite de transacción no reconocida

## Informe de controles para RCS · capítulos de control · 12/09/2026

> Edición funcional generada a partir de los documentos de control del equipo técnico.
> Las referencias tipo T01 remiten al índice de evidencias.

## 3. Cómo se evalúa el trámite

El banco de casos de este trámite tiene 126 casos que se ejecutan contra el asistente
desplegado y publican su resultado en los tableros de analítica.

| Banco de casos | Casos | Qué comprueba |
|---|---|---|
| Ruteo del trámite | 36 | Que la intención llegue aquí y que los trámites vecinos no caigan aquí |
| Adversariales | 51 | Inyección, manipulación del ruteo, evasión, manipulación del contexto, fuga de información y capacidades no autorizadas |
| Bypass del trámite | 10 | Intentos de saltarse paradas, forzar acciones y usar productos de otra persona |
| Respuestas ancladas a la fuente | 22 | Que el asistente no invente |
| Vigilancia continua | 7 | Las rutas críticas, cada 30 minutos, en operación |

### IT1.1 · Plan y alcance de las pruebas

**Qué pide el control.** Plan y alcance de pruebas IA aprobado.

El plan cubre el asistente y los servicios que ejecutan sus acciones. Estos son los componentes evaluados, del más interpretativo al más determinista:

| Componente | Qué aporta el modelo | Cómo se comprueba |
|---|---|---|
| Entendimiento de la intención | Propone el trámite y con qué seguridad | Banco de casos de ruteo y vigilancia continua |
| Lectura de fecha e importe escritos a mano | Extrae y normaliza | Casos de fidelidad a la fuente y pruebas del trámite completo |
| Elección de una opción de una lista | Asocia el texto a una opción | Pruebas del trámite completo |
| Cierre de las guías | Redacta, solo si está encendido | Casos de fidelidad a la fuente |
| Paradas obligatorias del trámite | Nada: las decide código determinista | Pruebas del trámite completo y catálogo de capacidades |
| Controles de entrada y salida | Juez de alcance | Casos adversariales |

Quedan fuera del alcance de estas pruebas el proceso automatizado de reintegro, los servicios
del banco y la aplicación del cliente, que se prueban en sus propios equipos.

Umbrales de aceptación:

| Qué se mide | Umbral de aceptación | Estado del umbral |
|---|---|---|
| Precisión del ruteo hacia este trámite | 90 % o más | Propuesto |
| Casos de frontera absorbidos por trámites vecinos | 10 % como máximo | Propuesto |
| Fugas de información | 0, sin excepción | Fijo |
| Intentos que alcanzan un paso con efecto | 0, sin excepción | Fijo |
| Intentos adversariales bloqueados o derivados | 95 % o más | Propuesto |
| Afirmaciones inventadas en saludo y cierres | 0 | Fijo |
| Respuestas sin respaldo en la fuente al leer la fecha | 0 | Fijo |
| Tiempo de respuesta | 10 segundos o menos | Medido en 9,8 segundos |
| Pruebas automáticas | 100 % en verde | Fijo |

Un cambio se acepta comparando caso a caso contra la ejecución anterior, no solo por el porcentaje global. En los casos de frontera que oscilan entre ejecuciones se toma la mayoría de tres.

**Evidencia.** T13 para la precisión alcanzada; el plan firmado es la evidencia documental.

**Estado.** Parcial. Falta: firmar el plan de pruebas y fijar los umbrales de aceptación, a cargo de: responsable del servicio y negocio.

### IT1.2 · Evaluación funcional del trámite

**Qué pide el control.** Evaluación funcional por intención: precisión, falsos positivos y negativos, ambiguos, este trámite.

El banco de ruteo contrasta la intención del cliente contra este trámite y contra sus vecinos, con frases literales, paráfrasis y casos de frontera. Cada ejecución publica un resultado por caso, y el tablero muestra la precisión, los fallos por tipología y el tiempo de respuesta.

**Evidencia.** T13 y T14.

**Estado.** Cubierto.

### IT1.3 · Evaluación de las respuestas generadas

**Qué pide el control.** Evaluación generativa: fidelidad a la fuente, fuente inexistente o contradictoria, fallback.

Se comprueban los cuatro puntos donde el asistente redacta o interpreta: el saludo con el nombre del cliente, el cierre de las guías, la aclaración cuando la intención es ambigua y la lectura de la fecha. Cada caso declara lo que la respuesta debe contener y lo que no puede afirmar sin respaldo, y el asistente registra quién redactó cada texto. La redacción libre de cierre está apagada.

**Evidencia.** T02, T03 y T15.

**Estado.** Cubierto.

### IT1.4 · Pruebas adversariales

**Qué pide el control.** Pruebas adversariales sobre la configuración final: inyección, ruteo, guardrails, contexto, fuga, capacidades.

Las seis categorías exigidas se cubren con casos propios, más conversaciones de varios turnos que intentan forzar el trámite. La evaluación distingue tres fallos graves: revelar contenido prohibido, terminar en un paso que no correspondía y entrar en un trámite vedado.

**Evidencia.** T07, T08 y T16.

**Estado.** Cubierto.

### IT1.5 · Cierre de las pruebas

**Qué pide el control.** Cierre: remediación y retest de críticos y altos; umbrales cumplidos.

Los hallazgos de la evaluación se registran con severidad, dueño, estado y la prueba de cierre. El único hallazgo crítico, que era la presencia de datos sensibles en los registros, está corregido y verificado.

**Evidencia.** T22 y el registro de hallazgos.

**Estado.** Parcial. Falta: cerrar los hallazgos de severidad alta cuyo dueño es otro equipo, a cargo de: responsable del servicio y equipo systems.

### IT1.6 · Trazabilidad de la versión evaluada

**Qué pide el control.** Trazabilidad productiva: modelo, prompts, guardrails, KB y configuración evaluada = versión promovida.

Cada ejecución del banco de casos queda marcada con la versión evaluada, y de cada versión existe una ficha con el modelo, los portones, el catálogo de rutas y los bancos de casos. La correspondencia con lo desplegado se comprueba cruzando esa ficha con las versiones en ejecución.

**Evidencia.** T19 y T25.

**Estado.** Cubierto.

## 4. Cómo se vigila en operación

### IT2.1 · Gobierno y operación

**Qué pide el control.** Procedimiento de gobierno y operación IA con roles.

Cada pieza que influye en el comportamiento del asistente tiene un dueño que propone y un responsable que aprueba:

| Activo | Quién propone el cambio | Quién lo aprueba |
|---|---|---|
| Catálogo de rutas y definición del trámite | Dueño del trámite, con negocio | Responsable del servicio |
| Instrucciones del modelo | Equipo técnico | Responsable del servicio |
| Controles de entrada y salida | Equipo técnico | Responsable del servicio |
| Modelo y su configuración | Equipo técnico | Responsable del servicio |
| Bancos de casos y umbrales | Equipo técnico | Responsable del servicio y negocio |
| Límites del trámite | Negocio | Negocio y el equipo de riesgo |

**Evidencia.** El procedimiento de gobierno firmado es la evidencia documental.

**Estado.** Parcial. Falta: unificar el procedimiento de gobierno en el formato del banco, con nombres y acuerdos de nivel de servicio, a cargo de: responsable del servicio y equipo técnico.

### IT2.2 · Inventario y configuración

**Qué pide el control.** Inventario: modelo, versión, proveedor, finalidad, personalizaciones, componentes.

La ficha de versión es el inventario de cada versión evaluada. Reúne las versiones desplegadas de cada componente, el modelo y su proveedor, los portones activos, la huella y la fecha del último cambio del catálogo de rutas, las instrucciones del modelo, la definición del trámite, los controles de entrada y salida, y los bancos de casos con sus umbrales. Se genera con cada ejecución completa y con cada promoción, y se archiva junto a la evidencia.

Finalidad del modelo en esta solución: entender la intención del cliente y validar el texto que escribe. No redacta mensajes al cliente, salvo el cierre de las guías, que está apagado.

**Evidencia.** T25 y T26.

**Estado.** Cubierto.

### IT2.3 · Esquema de monitoreo

**Qué pide el control.** Esquema de monitoreo: KPM/KRI, responsables, periodicidad, umbrales.

La vigilancia tiene cinco relojes, con responsable y umbral:

| Vigilancia | Cadencia | Qué mira | Umbral | Quién revisa |
|---|---|---|---|---|
| Vigilancia continua | Cada 30 minutos en horario hábil | Precisión y rutas caídas | 90 %, dos ejecuciones seguidas | Equipo técnico, con aviso por correo |
| Banco de casos completo | Diaria y antes de cada despliegue | Precisión, fallos por tipología y tiempo de respuesta | Los de la tabla de umbrales | Equipo técnico |
| Casos adversariales y de fidelidad | Con cada cambio de catálogo, instrucciones, controles o modelo | Fugas, pasos prohibidos e invenciones | 0 | Equipo técnico |
| Tráfico real | Continua | Desenlaces, tiempos y topes alcanzados | Tableros de operación | Dueño del trámite, semanal |
| Registros guardados | Con cada despliegue | Barrido de datos sensibles | 0 hallazgos | Equipo técnico |

La revisión semanal del equipo técnico cubre los hallazgos abiertos, las ejecuciones de la
semana y los umbrales todavía sin aprobar. La vigilancia continua y el banco diario están
construidos y en pausa, a la espera de la aprobación de costo.

**Evidencia.** T18 y T27.

**Estado.** Parcial. Falta: aprobar los umbrales de alerta y sus destinatarios, a cargo de: responsable del servicio.

### IT2.4 · Gestión de cambios

**Qué pide el control.** Gestión de cambios: cuándo un cambio exige regresión o evaluación.

Un cambio se clasifica por lo que toca, y esa clasificación fija la evaluación que exige:

| Qué cambia | Qué evaluación exige |
|---|---|
| La definición del trámite o el servicio que lo ejecuta | Pruebas del trámite completo y del servicio, más el banco de casos del trámite y los de bypass |
| El catálogo de rutas o las instrucciones del modelo | Banco de casos de todos los trámites y casos adversariales, comparando caso a caso contra la ejecución anterior |
| Los controles de entrada y salida | Corpus de quejas reales, para medir falsos positivos, y casos adversariales |
| El modelo o su proveedor | Evaluación completa con firma, incluida la fidelidad a la fuente, y nueva medición del piso en contingencia |
| Un parámetro de configuración | Pruebas del trámite completo; si cambia un límite económico, aprobación de negocio |

Ningún cambio se promueve con pruebas en rojo, con una fuga de información o un paso prohibido
distinto de cero, ni con un hallazgo crítico abierto sin fecha de cierre. Además, al regenerar el
catálogo de capacidades, una acción nueva sin clasificar o un camino que se salte una parada
obligatoria bloquean la promoción.

**Evidencia.** La matriz de cambios del procedimiento de gobierno.

**Estado.** Cubierto.

### IT2.5 · Gobierno del catálogo de conocimiento

**Qué pide el control.** Gobierno de KB/RAG: aprobación, versionamiento, vigencia, retiro.

- **Fuente de verdad.** El catálogo de rutas y la definición de cada trámite viven versionados. La hoja de cálculo de ruteo es material de referencia y nunca se lee durante la operación.
- **Aprobación.** Un cambio de texto al cliente o de rutas lo aprueba negocio; un cambio de ejemplos del enrutador lo aprueba el equipo técnico con el banco de casos.
- **Versionamiento.** La versión del catálogo viaja en cada ejecución del banco de casos y en cada conversación, y la ficha de versión guarda su huella.
- **Vigencia y retiro.** Una ruta se retira quitándola del catálogo y dejando su caso en el banco como contraejemplo, de modo que se comprueba que ya no se enruta. Las rutas que todavía no están disponibles se declaran como contraejemplo, nunca como una opción vacía.
- **Contenido sensible.** El catálogo no contiene datos de clientes, y los datos de prueba con información real se retiran.

**Evidencia.** El historial de versiones del catálogo de rutas.

**Estado.** Cubierto.

### IT2.6 · Contingencia

**Qué pide el control.** Contingencia: escalamiento, suspensión de tipología, retorno, derivación.

| Situación | Señal | Quién decide | Qué se hace |
|---|---|---|---|
| El proveedor del modelo se cae o responde lento | Alertas de la vigilancia continua y del tiempo de respuesta | Avisa el equipo técnico, decide el líder técnico | El asistente pasa solo a modo contingencia, con entendimiento por palabras clave; se comunica el piso medido y se vigila que no haya fugas |
| Un trámite empieza a enrutar mal tras un cambio | Banco de casos o vigilancia continua en rojo | Dueño del trámite | Se vuelve a la versión anterior del catálogo y se repasa el banco de casos |
| Un trámite con acción económica se comporta mal | Pruebas del trámite completo y hallazgo de severidad alta | Líder técnico | Se cierra el portón del trámite, que queda derivando al formulario sin necesidad de desplegar, o se suspende la opción en el catálogo |
| Aparecen datos sensibles en los registros | Barrido con hallazgos | Líder técnico | Se apagan los volcados de diagnóstico, se depuran los registros y se rotan las credenciales |
| Retorno a la normalidad | Ejecución completa en verde con su ficha de versión | Líder técnico | Se reabre el portón o la opción del catálogo |

Derivar al proceso tradicional no exige desplegar nada: el formulario es el último recurso de
todo trámite y la línea de atención aparece en cada cierre.

**Evidencia.** T21.

**Estado.** Parcial. Falta: cerrar el documento de contingencia, a cargo de: responsable del servicio.

### IT2.7 · Revisión periódica

**Qué pide el control.** Revisión periódica una vez en operación.

La revisión periódica automática es la vigilancia continua cada 30 minutos y el resumen de cada ejecución, con sus alertas. Hoy están construidas y en pausa, a la espera de la aprobación de costo.

**Evidencia.** T17.

**Estado.** Pendiente. Falta: encender la vigilancia continua en el ambiente evaluado y registrar ejecuciones consecutivas, a cargo de: responsable del servicio.

## 5. Cómo se protegen los datos

### IT3.1 · Mapa de datos del trámite

**Qué pide el control.** Mapa E2E de datos IA: entrada, proceso, almacenamiento, retención.

El trámite recibe del cliente lo que escribe en la conversación, y del banco los productos, los movimientos y los datos de contacto del cliente. Lo que se guarda son la conversación, la ficha del caso y los registros técnicos, todos con los datos sensibles enmascarados.

**Evidencia.** T22 y T24.

**Estado.** Parcial. Falta: publicar la tabla de retención por almacén de datos, a cargo de: equipo técnico y responsable del servicio.

### IT3.2 · Minimización y enmascarado

**Qué pide el control.** Minimización: dato original, enmascarado, payload al modelo.

La protección tiene tres capas, y ninguna depende de que alguien recuerde apagar algo:

1. **En el origen no existe la opción de volcar una credencial.** La contraseña de conexión con los servicios del banco sale siempre oculta, con su longitud pero sin su contenido. El certificado de sesión nunca sale completo: se registra su longitud, su principio, su final y una huella, que basta para comprobar que el servicio recibió el mismo que se le entregó.
2. **En el ambiente evaluado los volcados de diagnóstico están apagados.** Encenderlos sigue siendo legítimo para depurar, porque lo que se guarda ya va enmascarado.
3. **Última barrera antes de guardar.** Todo registro pasa por un saneamiento que actúa por nombre del campo y por contenido, sin ningún interruptor que lo desactive. Se ocultan contraseñas, certificados, credenciales y volcados completos; el número de tarjeta se reduce a sus últimos cuatro dígitos; los correos se ocultan y los nombres de personas se reducen a iniciales.

Lo que **no** se oculta es el número de documento ni el número de contrato, porque son la
evidencia del caso y no identifican un medio de pago.

**Evidencia.** T22.

**Estado.** Cubierto.

### IT3.3 · Aislamiento entre clientes

**Qué pide el control.** Aislamiento entre clientes, sesiones y contextos.

El identificador de la conversación se deriva del propio cliente, y el cliente se vuelve a extraer de él. No existe ningún parámetro que el llamador pueda manipular para apuntar a la ficha de otra persona.

Queda un punto abierto que conviene decir con claridad: la interfaz del asistente no autentica hoy a quien la llama. La barrera actual es el canal, que sí autentica al cliente, y la red interna. El servicio de autorización en construcción es el que cierra este punto. Es un hallazgo de arquitectura, no del trámite.

**Evidencia.** T11.

**Estado.** Parcial. Falta: autenticar a quien llama a la interfaz del asistente, a cargo de: responsable del servicio.

### IT3.4 · Exposición de datos por manipulación conversacional

**Qué pide el control.** Exposición o reconstrucción de datos sensibles por manipulación conversacional.

La categoría de fuga de información del banco adversarial reúne los intentos de reconstruir datos del cliente o del sistema mediante la conversación.

**Evidencia.** T16.

**Estado.** Cubierto.

### IT3.5 · Controles de entrada y salida

**Qué pide el control.** Guardrails de entrada y salida, con casos de evasión.

El control tiene dos capas: un filtro de patrones que no usa el modelo y un juez de alcance que sí lo usa, activo en el ambiente evaluado. La categoría de evasión del banco adversarial intenta sortearlas.

**Evidencia.** T07 y T08.

**Estado.** Cubierto.

### IT3.6 · Persistencia sin datos sensibles

**Qué pide el control.** Persistencia sin información sensible en claro.

Dieciocho pruebas automáticas fijan el comportamiento del enmascarado y se ejecutan con cada cambio:

| Qué se comprueba | Dónde | Resultado |
|---|---|---|
| El número de tarjeta se enmascara con separadores y sin ellos, dentro de direcciones y de contenidos; el documento y el contrato se conservan; las claves se ocultan; el titular queda en iniciales | Manejador de errores | En verde |
| Ni la contraseña, ni el certificado de sesión, ni el número de tarjeta salen del origen, aun con los volcados de diagnóstico encendidos | Servicio del trámite | En verde |
| El cuerpo de la respuesta se guarda enmascarado y las cabeceras solo conservan lo técnico | Servicio de datos del cliente | En verde |

**Evidencia.** T22 y T24.

**Estado.** Parcial. Falta: depurar los registros anteriores a la versión evaluada, a cargo de: responsable del servicio.

### IT3.7 · Remediación y verificación

**Qué pide el control.** Remediación y retest de hallazgos de exposición.

Una herramienta recorre el almacén de registros y cuenta cuántos números de tarjeta, correos, certificados completos, contraseñas en claro y volcados completos aparecen. Termina con error si encuentra algo, de modo que sirve como parada obligatoria antes de promover una versión.

Está verificada contra un registro sucio de prueba, donde detecta los cinco tipos de dato, y contra uno limpio, donde no encuentra ninguno. La verificación definitiva se hace sobre el almacén del ambiente evaluado, una vez desplegada la versión.

**Evidencia.** T22.

**Estado.** Parcial. Falta: depurar el histórico de registros y rotar las credenciales, a cargo de: responsable del servicio.

## 6. Qué no puede hacer el asistente por su cuenta

### IT4.1 · Arquitectura del trámite

**Qué pide el control.** Arquitectura E2E actualizada.

La arquitectura está en el diseño técnico del servicio y en el documento de arquitectura del equipo.

**Evidencia.** Documentos de arquitectura enlazados en la tabla de control.

**Estado.** De otro equipo. Falta: actualizar la arquitectura con la analítica y el servicio de autorización, a cargo de: responsable del servicio.

### IT4.2 · Restricción de capacidades

**Qué pide el control.** lista de acciones permitidas de rutas, acciones, estados y parámetros; validación independiente antes de acciones sensibles.

La frontera del diseño es que el modelo entiende e interpreta, pero nunca ejecuta:

| Momento | Qué hace el modelo | Qué hace la regla |
|---|---|---|
| Entender lo que pide el cliente | Interpreta y propone el trámite | Si la seguridad es baja, se pide confirmación |
| Leer una fecha o un importe escritos a mano | Extrae y normaliza | Se vuelve a validar; lo imposible o futuro se repregunta |
| Elegir una opción de una lista | Asocia el texto a una de las opciones | El paso siguiente está fijado de antemano |
| Redactar el cierre de una guía | Solo si está encendido; hoy está apagado | El texto aprobado |
| Ejecutar una acción con efecto | Nunca | Código determinista, con las paradas obligatorias y cierre seguro ante fallo |

La lista de acciones permitidas del asistente está generada de la definición del trámite y verificada por prueba automática. De todas ellas, 3 tienen efecto sobre el cliente o sus productos, y cada una exige que el cliente haya pasado por todas sus paradas obligatorias. No existe ningún atajo hacia esas acciones.

**Evidencia.** T01.

**Estado.** Cubierto.

### IT4.3 · Pruebas de bypass

**Qué pide el control.** Bypass: modificar producto, saltar estados, forzar bloqueo, reexpedición o abono.

Las conversaciones de bypass intentan saltarse paradas, forzar un bloqueo o una devolución, cambiar de producto y usar el producto de otra persona. La evaluación marca como fallo grave que la conversación termine en un paso que no correspondía.

**Evidencia.** T09, T10, T11 y T16.

**Estado.** Cubierto.

### IT4.4 · Idempotencia

**Qué pide el control.** Idempotencia: llave única, doble envío, concurrencia, reintento, reingreso.

| Riesgo | Protección |
|---|---|
| Que una devolución se registre dos veces, por un reintento o por recargar la página | Cada transacción se identifica por su extracto y su movimiento: la segunda pasada no añade una fila nueva |
| Que se creen dos fichas para el mismo caso | Hay una sola ficha por cliente y trámite, y un hito repetido no se duplica |
| Que el turno falle después de ejecutar el bloqueo y el cliente reintente | El hito del bloqueo queda en un registro duradero que no se revierte con la conversación: al reintentar se lee y no se vuelve a bloquear |
| Que el cliente envíe dos mensajes a la vez | Se atiende un turno por conversación; el segundo no arranca nada mientras el primero sigue en curso, y un turno huérfano se recupera solo |

**Evidencia.** T12 y T28.

**Estado.** Cubierto.

### IT4.5 · Fallos parciales

**Qué pide el control.** Fallos parciales: timeout, acción exitosa con fallo posterior, sin reejecución.

Ante un tiempo de espera agotado o una respuesta perdida, el trámite se detiene y deriva, en lugar de reintentar la acción. Un candado impide que una acción ya ejecutada se repita.

**Evidencia.** T10 y T28.

**Estado.** Cubierto.

### IT4.6 · Límites antifraude

**Qué pide el control.** Límites antifraude aprobados: monto, acumulado, frecuencia; pruebas de superación.

| Límite | Valor previsto |
|---|---|
| Transacciones por trámite | 3 |
| Valor por transacción | $35.000 a $500.000 |
| Plazo para reportar, franquicia Visa | 180 días |
| Plazo para reportar, franquicia Mastercard | 120 días |
| Plazo informado de respuesta de la devolución | 10 días hábiles |
| Plazo informado de entrega de la tarjeta nueva | 5 días hábiles |
| Sesiones por cliente y día | 3 |
| Interacciones por caso y día | 3 |

En el ambiente de pruebas los dos últimos están abiertos a propósito para poder ejecutar el
banco de casos. Los valores de la tabla son los previstos para la operación. Falta que negocio
los apruebe por escrito y que existan pruebas de superación por suma acumulada, porque hoy el
tope es por transacción.

**Evidencia.** T05 y T06.

**Estado.** De otro equipo. Falta: aprobar por escrito la parametrización de límites y probar la superación por suma acumulada, a cargo de: equipo systems y negocio.

### IT4.7 · Trazabilidad de un caso

**Qué pide el control.** Trazabilidad: reconstruir cliente, transacción, reglas, decisión, acción, resultado.

Un caso se reconstruye de punta a punta: quién lo abrió, qué pidió en cada turno, qué reglas se aplicaron, qué acción se ejecutó y con qué resultado.

**Evidencia.** T20 y T23.

**Estado.** Cubierto.

### IT4.8 · Reconciliación

**Qué pide el control.** Reconciliación: elegibles, enviadas, ejecutadas, rechazadas, contabilizadas.

Las solicitudes registradas se entregan al proceso de reintegro con una huella única por transacción, que evita duplicados. El cruce entre solicitudes elegibles, enviadas, ejecutadas y contabilizadas está pendiente de diseño.

**Evidencia.** T28.

**Estado.** De otro equipo. Falta: diseñar la reconciliación entre solicitudes elegibles, enviadas, ejecutadas y contabilizadas, a cargo de: equipo systems.

## 7. Pendientes y decisiones

| Control | Qué falta | Quién lo cierra | Estado |
|---|---|---|---|
| IT1.1 | Firmar el plan de pruebas y fijar los umbrales de aceptación | Responsable del servicio y negocio | Parcial |
| IT1.5 | Cerrar los hallazgos de severidad alta cuyo dueño es otro equipo | Responsable del servicio y equipo Systems | Parcial |
| IT2.1 | Unificar el procedimiento de gobierno en el formato del banco, con nombres y acuerdos de nivel de servicio | Responsable del servicio y equipo técnico | Parcial |
| IT2.3 | Aprobar los umbrales de alerta y sus destinatarios | Responsable del servicio | Parcial |
| IT2.6 | Cerrar el documento de contingencia | Responsable del servicio | Parcial |
| IT2.7 | Encender la vigilancia continua en el ambiente evaluado y registrar ejecuciones consecutivas | Responsable del servicio | Pendiente |
| IT3.1 | Publicar la tabla de retención por almacén de datos | Equipo técnico y responsable del servicio | Parcial |
| IT3.3 | Autenticar a quien llama a la interfaz del asistente | Responsable del servicio | Parcial |
| IT3.6 | Depurar los registros anteriores a la versión evaluada | Responsable del servicio | Parcial |
| IT3.7 | Depurar el histórico de registros y rotar las credenciales | Responsable del servicio | Parcial |
| IT4.1 | Actualizar la arquitectura con la analítica y el servicio de autorización | Responsable del servicio | De otro equipo |
| IT4.6 | Aprobar por escrito la parametrización de límites y probar la superación por suma acumulada | Equipo Systems y negocio | De otro equipo |
| IT4.8 | Diseñar la reconciliación entre solicitudes elegibles, enviadas, ejecutadas y contabilizadas | Equipo Systems | De otro equipo |
