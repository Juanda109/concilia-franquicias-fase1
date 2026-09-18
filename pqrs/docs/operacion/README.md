# Operación

Procedimientos y postmortems. La idea es que quien llegue a un problema ya visto
no tenga que reconstruir el diagnóstico desde cero.

## Documentos

### [`TABLA_DE_CONTROL_LIMITE_DE_CAMPOS.md`](TABLA_DE_CONTROL_LIMITE_DE_CAMPOS.md)

El cliente recibe *"En este momento no puedo validar el estado de tus productos
en las centrales de riesgo"* tras esperar unos 15 segundos, y el servicio de
fondo sí funcionó.

Causa: el índice `client-control-table` agota su límite de 1000 campos porque la
tabla usa **fechas como nombre de campo**, así que cada día y cada mes añaden
rutas nuevas al esquema. A partir de ahí OpenSearch rechaza toda escritura con
un `400`, incluida la del agente, que la capturaba en silencio.

Incluye qué trazas mirar, el desplegable que lo sanea sin borrar datos, y los
tres errores de diagnóstico que se cometieron antes de acertar.

### [`ALINEAR_DEV_A_PRODUCCION.md`](ALINEAR_DEV_A_PRODUCCION.md)

Cómo llevar código de una rama de desarrollo a una de producción sin arrastrar
configuración del ambiente de origen: endpoints, namespaces, imágenes,
credenciales y límites de abuso.

Escrito para aplicarse en cualquier repositorio con el patrón «una rama por
ambiente», no solo en este. La trampa principal está explicada con el caso real
que la destapó: comparar **nombres** de variable en lugar de **valores**.

## Dos reglas que salieron de estos casos

**Un cambio de esquema o de script painless no se valida con tests en memoria.**
Una imitación de la base de datos siempre responde lo que se espera. Hay que
probarlo contra un OpenSearch de la misma versión que producción, o no se ha
probado.

**Dev no siempre va por delante.** Producción ha tenido arreglos que desarrollo
no tenía, y alinear a ciegas los ha revertido más de una vez. Compara en las dos
direcciones antes de copiar.
