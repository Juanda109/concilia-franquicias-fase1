-- CONCILIA V1 - FASE 1
-- Ampliacion de longitud de cuenta funcional.
-- Compatible con CAET, CANT y otros insumos de franquicia.
-- No modifica registros existentes.

ALTER TABLE con_franquicia_resultado
    ALTER COLUMN cuenta TYPE VARCHAR(120);
