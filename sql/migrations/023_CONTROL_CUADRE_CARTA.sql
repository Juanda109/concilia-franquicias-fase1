-- CONCILIA V1 - FASE 1
-- Migracion 023: evidencia auditable de controles
-- Solo concilia_test.
-- Conserva datos, claves y restricciones existentes.

BEGIN;

SET LOCAL lock_timeout = '5s';

DO $$
BEGIN
    IF current_database() <> 'concilia_test' THEN
        RAISE EXCEPTION 'Base de datos no autorizada';
    END IF;
END
$$;

ALTER TABLE public.con_detalle_control
    ADD COLUMN valor_esperado NUMERIC(24,4),
    ADD COLUMN valor_obtenido_numerico NUMERIC(24,4),
    ADD COLUMN estado_validacion VARCHAR(20);

ALTER TABLE public.con_detalle_control
    ADD CONSTRAINT ck_detalle_control_estado
    CHECK (
        estado_validacion IS NULL
        OR estado_validacion IN (
            'OK',
            'ERROR',
            'PENDIENTE'
        )
    );

COMMIT;
