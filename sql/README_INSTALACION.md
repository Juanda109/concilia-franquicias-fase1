# Esquema PostgreSQL - Concilia V1 MVP1

Las migraciones de `sql/migrations/` son la fuente versionada de DDL:
creacion/evolucion de tablas, restricciones, indices, funciones y catalogo.

1. Utilizar una base de desarrollo **nueva y vacia**, no una base con datos.
2. Revisar y ejecutar los archivos `.sql` en orden numerico (001 a 028), con
   `psql -v ON_ERROR_STOP=1 -f <archivo>` y credenciales autorizadas.
3. Algunos archivos, especialmente 027/028, tienen protecciones de nombre
   de base `concilia_test`; no deben desactivarse ni copiarse sin revision.
4. Verificar despues las tablas, relaciones, indices, funciones y diez insumos
   de `CON_CATALOGO_INSUMO`. CAIT queda excluido del MVP1.
5. No ejecutar los scripts sobre `concilia_test` existente ni sobre produccion.

**Limitacion:** la reconstruccion desde una base vacia todavia no esta
certificada por una ejecucion automatizada en este paquete. La presencia de
migraciones y pruebas existentes no demuestra por si sola esa restaurabilidad.
