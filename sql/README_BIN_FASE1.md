# CONCILIA V1 - Catalogo BIN Fase 1

## Orden de despliegue

1. Aplicar las migraciones estructurales existentes,
   incluyendo 005_CATALOGO_BIN_RED.sql.

2. Ejecutar:
   sql/seeds/001_BINES_CANJE_FASE1.sql

3. Ejecutar:
   sql/migrations/034_PARAMETRIA_BIN_FASE1.sql

## Validaciones

- 42 BIN del catalogo BINES_CANJE.
- Version de catalogo BIN: 1.
- Sin BIN duplicados.
- BIN 417704 conservado.
- Tipos de tarjeta existentes sin modificaciones.
- Nombre y franquicia enriquecidos.
- Sin modificaciones a tablas transaccionales.

## Alcance

Fase 1: consulta y clasificacion BIN.
Fase 4: administracion parametrica, vigencias y auditoria.

## Restricciones

No modificar jornadas existentes.
No ejecutar migraciones sin respaldo.
No realizar commit ni push automaticamente.
