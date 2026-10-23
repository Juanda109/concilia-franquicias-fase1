-- CONCILIA V1 - MVP1
-- Migracion 027: consolidacion tecnica de jornada.
-- BORRADOR: NO EJECUTAR SIN PRUEBAS.
-- No representa conciliacion financiera.

BEGIN;

SET LOCAL lock_timeout = '5s';

DO $$
BEGIN
    IF current_database() <> 'concilia_test' THEN
        RAISE EXCEPTION 'Base de datos no autorizada';
    END IF;
END
$$;

CREATE OR REPLACE FUNCTION public.fn_consolidar_jornada_tecnica(
    p_id_jornada BIGINT,
    p_correlation_id VARCHAR
)
RETURNS TABLE (
    id_jornada BIGINT,
    estado VARCHAR,
    total_archivos INTEGER,
    idempotente BOOLEAN
)
LANGUAGE plpgsql
AS $function$
DECLARE
    v_jornada RECORD;
    v_id_insumo BIGINT;
    v_id_archivo BIGINT;
    v_total_catalogo INTEGER;
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

    IF v_total_catalogo <> 10 THEN
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
            WHERE i.estado = 'PROCESADO'
              AND a.estado = 'PROCESADO'
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

    IF v_total_insumos <> 10
       OR v_total_archivos <> 10
       OR v_total_distintos <> 10
       OR v_procesados <> 10
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

    v_nuevo_estado := 'COMPLETADA';

    v_cambio :=
        v_jornada.estado IS DISTINCT FROM v_nuevo_estado
        OR v_jornada.total_archivos IS DISTINCT FROM 10
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
        total_archivos = 10,
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
        ': 10 insumos funcionales procesados'
    );

    RETURN QUERY
    SELECT
        p_id_jornada,
        v_nuevo_estado::VARCHAR,
        10,
        FALSE;
END;
$function$;

COMMIT;
