-- CONCILIA V1 - DEPURACION CONTROLADA FASE 1
-- SOLO concilia_test
-- Requiere respaldo y revision previa.
-- No utilizar CASCADE.

BEGIN;

SET LOCAL lock_timeout = '5s';

DO $$
DECLARE
    nombre TEXT;
    cantidad BIGINT;
BEGIN
    IF current_database() <> 'concilia_test' THEN
        RAISE EXCEPTION 'Base de datos no autorizada';
    END IF;

    FOREACH nombre IN ARRAY ARRAY[
        'con_conciliacion',
        'con_cruce',
        'con_decision_excepcion',
        'con_excepcion',
        'con_regla_conciliacion',
        'con_reproceso',
        'con_salida_generada'
    ]
    LOOP
        EXECUTE format(
            'SELECT COUNT(*) FROM public.%I',
            nombre
        ) INTO cantidad;

        IF cantidad <> 0 THEN
            RAISE EXCEPTION
                'Tabla % contiene % registros',
                nombre, cantidad;
        END IF;
    END LOOP;

    IF EXISTS (
        SELECT 1
        FROM con_trazabilidad
        WHERE id_conciliacion IS NOT NULL
           OR id_cruce IS NOT NULL
    ) THEN
        RAISE EXCEPTION
            'Existen referencias activas de trazabilidad';
    END IF;
END
$$;

ALTER TABLE con_trazabilidad
    DROP CONSTRAINT con_trazabilidad_id_conciliacion_fkey;

ALTER TABLE con_trazabilidad
    DROP CONSTRAINT con_trazabilidad_id_cruce_fkey;

DROP TABLE con_decision_excepcion;
DROP TABLE con_excepcion;
DROP TABLE con_reproceso;
DROP TABLE con_salida_generada;
DROP TABLE con_cruce;
DROP TABLE con_regla_conciliacion;
DROP TABLE con_conciliacion;

COMMIT;
