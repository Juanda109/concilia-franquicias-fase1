
-- CONCILIA V1 - FASE 1
-- Migracion 037: clasificacion de jornadas y control de persistencia Host.
-- Requiere migraciones 019, 020, 027-034 y 035.
-- Conserva la definicion instalada de fn_consolidar_jornada_tecnica.
-- Objetivo de aplicacion: concilia_test.

BEGIN;

SET LOCAL lock_timeout = '5s';

DO $$
BEGIN
    IF current_database() <> 'concilia_test' THEN
        RAISE EXCEPTION 'Base de datos no autorizada';
    END IF;
END
$$;

-- 1. Clasificacion explicita de jornadas.
ALTER TABLE public.con_jornada
    ADD COLUMN tipo_jornada VARCHAR(15)
    NOT NULL DEFAULT 'OPERATIVA';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'public.con_jornada'::regclass
          AND conname = 'ck_con_jornada_tipo_jornada'
    ) THEN
        ALTER TABLE public.con_jornada
            ADD CONSTRAINT ck_con_jornada_tipo_jornada
            CHECK (tipo_jornada IN ('OPERATIVA', 'PRUEBA'));
    END IF;
END
$$;

-- 2. Clasificar unicamente las tres jornadas de prueba identificadas.
UPDATE public.con_jornada
SET tipo_jornada = 'PRUEBA'
WHERE id_jornada IN (3976, 4184, 4186)
  AND tipo_jornada = 'OPERATIVA';

DO $$
DECLARE
    v_pruebas INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_pruebas
    FROM public.con_jornada
    WHERE id_jornada IN (3976, 4184, 4186)
      AND tipo_jornada = 'PRUEBA';

    IF v_pruebas <> 3 THEN
        RAISE EXCEPTION
            'Clasificacion de jornadas de prueba incompleta: %',
            v_pruebas;
    END IF;
END
$$;

-- 3. Evidencia auditable de la clasificacion.
INSERT INTO public.con_trazabilidad (
    correlation_id,
    id_jornada,
    id_archivo,
    tipo_evento,
    componente,
    detalle
)
SELECT
    'MIGRACION_037_CLASIFICACION_' || j.id_jornada,
    j.id_jornada,
    NULL,
    'JORNADA_CLASIFICADA_PRUEBA',
    'MIGRACION_037',
    'Jornada clasificada explicitamente como PRUEBA'
FROM public.con_jornada j
WHERE j.id_jornada IN (3976, 4184, 4186)
  AND j.tipo_jornada = 'PRUEBA'
  AND NOT EXISTS (
      SELECT 1
      FROM public.con_trazabilidad t
      WHERE t.id_jornada = j.id_jornada
        AND t.tipo_evento = 'JORNADA_CLASIFICADA_PRUEBA'
        AND t.componente = 'MIGRACION_037'
  );

-- 4. Reemplazar la funcion instalada conservando su cuerpo original
-- y agregando el control antes de completar la jornada.


CREATE OR REPLACE FUNCTION public.fn_consolidar_jornada_tecnica(p_id_jornada bigint, p_correlation_id character varying)
 RETURNS TABLE(id_jornada bigint, estado character varying, total_archivos integer, idempotente boolean)
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_jornada RECORD;
    v_id_insumo BIGINT;
    v_id_archivo BIGINT;
    v_total_catalogo INTEGER;
    v_esperados INTEGER;
    v_total_insumos INTEGER;
    v_total_archivos INTEGER;
    v_total_distintos INTEGER;
    v_procesados INTEGER;
    v_inconsistentes INTEGER;
    v_ha22 BOOLEAN;
    v_ha26 BOOLEAN;
    v_ha32 BOOLEAN;
    v_nuevo_estado VARCHAR;
    v_cambio BOOLEAN;
BEGIN
    IF current_database() <> 'concilia_test' THEN
        RAISE EXCEPTION 'Base no autorizada';
    END IF;

    IF p_correlation_id IS NULL
       OR btrim(p_correlation_id) = '' THEN
        RAISE EXCEPTION 'Correlation ID obligatorio';
    END IF;

    SELECT *
    INTO v_jornada
    FROM public.con_jornada j
    WHERE j.id_jornada = p_id_jornada
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Jornada inexistente: %', p_id_jornada;
    END IF;

    IF v_jornada.version_catalogo IS NULL THEN
        RAISE EXCEPTION 'Jornada sin version de catalogo';
    END IF;

    -- Proteger el catalogo durante toda la consolidacion.
    -- SHARE permite lecturas y bloquea escrituras incompatibles.
    LOCK TABLE public.con_catalogo_insumo IN SHARE MODE;


    -- Bloquear insumos en orden deterministico.
    FOR v_id_insumo IN
        SELECT i.id_insumo_esperado
        FROM public.con_insumo_esperado i
        WHERE i.id_jornada = p_id_jornada
        ORDER BY i.id_insumo_esperado
    LOOP
        PERFORM 1
        FROM public.con_insumo_esperado i
        WHERE i.id_insumo_esperado = v_id_insumo
        FOR UPDATE;
    END LOOP;

    -- Bloquear archivos asociados en orden deterministico.
    FOR v_id_archivo IN
        SELECT DISTINCT i.id_archivo
        FROM public.con_insumo_esperado i
        WHERE i.id_jornada = p_id_jornada
          AND i.id_archivo IS NOT NULL
        ORDER BY i.id_archivo
    LOOP
        PERFORM 1
        FROM public.con_archivo_carga a
        WHERE a.id_archivo = v_id_archivo
        FOR UPDATE;
    END LOOP;

    SELECT COUNT(*)
    INTO v_total_catalogo
    FROM public.con_catalogo_insumo c
    WHERE c.version_catalogo = v_jornada.version_catalogo
      AND c.activo = TRUE
      AND c.obligatorio = TRUE
      AND c.fec_desde <= v_jornada.fecha_contable
      AND (
          c.fec_hasta IS NULL
          OR c.fec_hasta >= v_jornada.fecha_contable
      );

    v_esperados := CASE v_jornada.version_catalogo WHEN 1 THEN 10 WHEN 2 THEN 10 ELSE NULL END;
    IF v_esperados IS NULL THEN
        RAISE EXCEPTION 'Version de catalogo no soportada';
    END IF;
    IF v_total_catalogo <> v_esperados THEN
        RAISE EXCEPTION
            'Catalogo funcional incompleto: %',
            v_total_catalogo;
    END IF;

    -- Validar identidad exacta de los insumos frente al catalogo.
    IF EXISTS (
        SELECT
            i.tipo_insumo,
            i.fuente,
            i.obligatorio
        FROM public.con_insumo_esperado i
        WHERE i.id_jornada = p_id_jornada
          AND i.obligatorio = TRUE

        EXCEPT

        SELECT
            c.tipo_insumo,
            c.fuente,
            c.obligatorio
        FROM public.con_catalogo_insumo c
        WHERE c.version_catalogo = v_jornada.version_catalogo
          AND c.activo = TRUE
          AND c.obligatorio = TRUE
          AND c.fec_desde <= v_jornada.fecha_contable
          AND (
              c.fec_hasta IS NULL
              OR c.fec_hasta >= v_jornada.fecha_contable
          )
    ) OR EXISTS (
        SELECT
            c.tipo_insumo,
            c.fuente,
            c.obligatorio
        FROM public.con_catalogo_insumo c
        WHERE c.version_catalogo = v_jornada.version_catalogo
          AND c.activo = TRUE
          AND c.obligatorio = TRUE
          AND c.fec_desde <= v_jornada.fecha_contable
          AND (
              c.fec_hasta IS NULL
              OR c.fec_hasta >= v_jornada.fecha_contable
          )

        EXCEPT

        SELECT
            i.tipo_insumo,
            i.fuente,
            i.obligatorio
        FROM public.con_insumo_esperado i
        WHERE i.id_jornada = p_id_jornada
          AND i.obligatorio = TRUE
    ) THEN
        RAISE EXCEPTION
            'Insumos no coinciden con catalogo de jornada %',
            p_id_jornada;
    END IF;

    -- Verificar tipo de archivo y fecha contable.
    IF EXISTS (
        SELECT 1
        FROM public.con_insumo_esperado i
        JOIN public.con_archivo_carga a
          ON a.id_archivo = i.id_archivo
        WHERE i.id_jornada = p_id_jornada
          AND (
              a.tipo_archivo IS DISTINCT FROM i.tipo_insumo
              OR a.fecha_contable IS DISTINCT FROM
                 v_jornada.fecha_contable
          )
    ) THEN
        RAISE EXCEPTION
            'Archivo incompatible con insumo de jornada %',
            p_id_jornada;
    END IF;

    SELECT
        COUNT(*),
        COUNT(i.id_archivo),
        COUNT(DISTINCT i.id_archivo),
        COUNT(*) FILTER (
            WHERE (i.estado = 'PROCESADO' AND a.estado = 'PROCESADO')
               OR EXISTS (SELECT 1 FROM public.con_confirmacion_sin_movimientos c
                          WHERE c.id_archivo = i.id_archivo)
        ),
        COUNT(*) FILTER (
            WHERE i.id_archivo IS NOT NULL
              AND (
                  a.id_archivo IS NULL
                  OR a.fecha_contable IS DISTINCT FROM
                     v_jornada.fecha_contable
              )
        )
    INTO
        v_total_insumos,
        v_total_archivos,
        v_total_distintos,
        v_procesados,
        v_inconsistentes
    FROM public.con_insumo_esperado i
    LEFT JOIN public.con_archivo_carga a
      ON a.id_archivo = i.id_archivo
    WHERE i.id_jornada = p_id_jornada
      AND i.obligatorio = TRUE;

    IF v_total_insumos <> v_esperados
       OR v_total_archivos <> v_esperados
       OR v_total_distintos <> v_esperados
       OR v_procesados <> v_esperados
       OR v_inconsistentes <> 0 THEN
        RAISE EXCEPTION
            'Jornada % no cumple completitud tecnica',
            p_id_jornada;
    END IF;

    SELECT
        COALESCE(bool_or(i.tipo_insumo = 'HA22'), FALSE),
        COALESCE(bool_or(i.tipo_insumo = 'HA26'), FALSE),
        COALESCE(bool_or(i.tipo_insumo = 'HA32'), FALSE)
    INTO v_ha22, v_ha26, v_ha32
    FROM public.con_insumo_esperado i
    WHERE i.id_jornada = p_id_jornada
      AND i.estado = 'PROCESADO'
      AND i.id_archivo IS NOT NULL;


    -- MIGRACION 037: integridad de persistencia Host.
    -- Aplica a jornadas OPERATIVAS.
    -- Las confirmaciones auditadas sin movimientos conservan
    -- el tratamiento establecido por las reglas existentes.

    IF v_jornada.tipo_jornada = 'OPERATIVA' THEN

        IF EXISTS (
            SELECT 1
            FROM public.con_insumo_esperado i
            JOIN public.con_archivo_carga a
              ON a.id_archivo = i.id_archivo
            WHERE i.id_jornada = p_id_jornada
              AND i.obligatorio = TRUE
              AND i.tipo_insumo IN ('HA22', 'HA26', 'HA32')
              AND i.id_archivo IS NOT NULL
              AND i.estado = 'PROCESADO'
              AND a.estado = 'PROCESADO'
              AND NOT EXISTS (
                  SELECT 1
                  FROM public.con_confirmacion_sin_movimientos c
                  WHERE c.id_archivo = i.id_archivo
              )
              AND (
                  -- Resultado normalizado completo.
                  (
                      SELECT COUNT(*)
                      FROM public.con_host_resultado h
                      WHERE h.id_archivo = a.id_archivo
                  ) IS DISTINCT FROM a.total_registros

                  OR

                  -- Detalle original completo, HA22.
                  CASE i.tipo_insumo
                      WHEN 'HA22' THEN (
                          SELECT COUNT(*)
                          FROM public.con_ha22_detalle d
                          WHERE d.id_archivo = a.id_archivo
                      ) <> a.total_registros
                      OR (
                          SELECT COUNT(DISTINCT d.linea_origen)
                          FROM public.con_ha22_detalle d
                          WHERE d.id_archivo = a.id_archivo
                      ) <> a.total_registros

                      -- Detalle original completo, HA26.
                      WHEN 'HA26' THEN (
                          SELECT COUNT(*)
                          FROM public.con_ha26_detalle d
                          WHERE d.id_archivo = a.id_archivo
                      ) <> a.total_registros
                      OR (
                          SELECT COUNT(DISTINCT d.linea_origen)
                          FROM public.con_ha26_detalle d
                          WHERE d.id_archivo = a.id_archivo
                      ) <> a.total_registros

                      -- Detalle original completo, HA32.
                      WHEN 'HA32' THEN (
                          SELECT COUNT(*)
                          FROM public.con_ha32_detalle d
                          WHERE d.id_archivo = a.id_archivo
                      ) <> a.total_registros
                      OR (
                          SELECT COUNT(DISTINCT d.linea_origen)
                          FROM public.con_ha32_detalle d
                          WHERE d.id_archivo = a.id_archivo
                      ) <> a.total_registros

                      ELSE FALSE
                  END

                  OR

                  -- Exactamente un evento vinculado al archivo
                  -- y a la jornada correspondiente.
                  (
                      SELECT COUNT(*)
                      FROM public.con_trazabilidad t
                      WHERE t.id_archivo = a.id_archivo
                        AND t.id_jornada = p_id_jornada
                        AND t.tipo_evento = 'DETALLE_PERSISTIDO'
                        AND t.componente = 'PROCESAMIENTO_DETALLE'
                  ) <> 1
              )
        ) THEN
            RAISE EXCEPTION
                'Jornada % tiene persistencia Host incompleta',
                p_id_jornada;
        END IF;

    END IF;

    v_nuevo_estado := 'COMPLETADA';


    v_cambio :=
        v_jornada.estado IS DISTINCT FROM v_nuevo_estado
        OR v_jornada.total_archivos IS DISTINCT FROM v_esperados
        OR v_jornada.ha22_recibido IS DISTINCT FROM v_ha22
        OR v_jornada.ha26_recibido IS DISTINCT FROM v_ha26
        OR v_jornada.ha32_recibido IS DISTINCT FROM v_ha32
        OR v_jornada.fec_completitud IS NULL;

    IF NOT v_cambio THEN
        RETURN QUERY
        SELECT
            p_id_jornada,
            v_jornada.estado::VARCHAR,
            v_jornada.total_archivos,
            TRUE;
        RETURN;
    END IF;

    UPDATE public.con_jornada j
    SET estado = v_nuevo_estado,
        total_archivos = v_esperados,
        ha22_recibido = v_ha22,
        ha26_recibido = v_ha26,
        ha32_recibido = v_ha32,
        fec_completitud = COALESCE(
            j.fec_completitud,
            CURRENT_TIMESTAMP
        )
    WHERE j.id_jornada = p_id_jornada;

    INSERT INTO public.con_trazabilidad (
        correlation_id,
        id_jornada,
        id_archivo,
        tipo_evento,
        componente,
        detalle
    )
    VALUES (
        p_correlation_id,
        p_id_jornada,
        NULL,
        'JORNADA_TECNICA_COMPLETADA',
        'CONSOLIDACION_JORNADA',
        'Jornada ' || p_id_jornada ||
        ': ' || v_esperados || ' insumos funcionales procesados'
    );

    RETURN QUERY
    SELECT
        p_id_jornada,
        v_nuevo_estado::VARCHAR,
        v_esperados,
        FALSE;
END;
$function$;

COMMIT;
