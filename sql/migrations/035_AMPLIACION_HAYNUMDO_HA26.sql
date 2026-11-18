-- CONCILIA V1 - FASE 1
-- Migracion 035: ampliacion HAYNUMDO HA26.
-- Motivo: identificadores originales de 12 caracteres.
-- No modifica parser, datos originales ni resultados normalizados.

BEGIN;

SET LOCAL lock_timeout = '5s';

DO $$
DECLARE
    v_tipo TEXT;
    v_longitud INTEGER;
BEGIN
    IF current_database() <> 'concilia_test' THEN
        RAISE EXCEPTION 'Base de datos no autorizada';
    END IF;

    SELECT
        data_type,
        character_maximum_length
    INTO
        v_tipo,
        v_longitud
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'con_ha26_detalle'
      AND column_name = 'haynumdo';

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'No existe public.con_ha26_detalle.haynumdo';
    END IF;

    IF v_tipo <> 'character varying' THEN
        RAISE EXCEPTION
            'Tipo inesperado para HAYNUMDO: %', v_tipo;
    END IF;

    IF v_longitud = 10 THEN
        ALTER TABLE public.con_ha26_detalle
            ALTER COLUMN haynumdo TYPE VARCHAR(12);
    ELSIF v_longitud = 12 THEN
        RAISE NOTICE 'HAYNUMDO ya tiene longitud 12.';
    ELSE
        RAISE EXCEPTION
            'Longitud inesperada para HAYNUMDO: %',
            v_longitud;
    END IF;
END
$$;

DO $$
DECLARE
    v_longitud INTEGER;
BEGIN
    SELECT character_maximum_length
    INTO v_longitud
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'con_ha26_detalle'
      AND column_name = 'haynumdo';

    IF v_longitud <> 12 THEN
        RAISE EXCEPTION
            'Verificacion HAYNUMDO fallida. Longitud: %',
            v_longitud;
    END IF;
END
$$;

COMMIT;