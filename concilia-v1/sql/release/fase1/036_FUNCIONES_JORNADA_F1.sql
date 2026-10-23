-- CONCILIA V1 / FASE 1 - solo catalogo version 1, diez insumos.
-- Ejecutar despues del DDL base, catalogo F1 y 035_CONFIRMACION_F1.sql.
-- No ejecutar sobre concilia_test: validar previamente en base aislada.
BEGIN;

CREATE OR REPLACE FUNCTION public.fn_inicializar_insumos_jornada(
    p_id_jornada BIGINT, p_version_catalogo INTEGER
) RETURNS INTEGER LANGUAGE plpgsql AS $func$
DECLARE
    v_fecha DATE;
    v_version INTEGER;
    v_existentes INTEGER;
    v_total INTEGER;
    v_insertados INTEGER;
BEGIN
    IF p_version_catalogo IS DISTINCT FROM 1 THEN
        RAISE EXCEPTION 'Fase 1 solo admite version_catalogo=1';
    END IF;
    SELECT fecha_contable, version_catalogo INTO v_fecha, v_version
      FROM public.con_jornada WHERE id_jornada=p_id_jornada FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Jornada inexistente: %',p_id_jornada; END IF;
    IF v_version IS NOT NULL AND v_version <> 1 THEN
        RAISE EXCEPTION 'Jornada ya asociada a otra version';
    END IF;
    SELECT COUNT(*) INTO v_existentes FROM public.con_insumo_esperado
      WHERE id_jornada=p_id_jornada;
    IF v_version IS NULL AND v_existentes > 0 THEN
        RAISE EXCEPTION 'Jornada con insumos sin version';
    END IF;
    SELECT COUNT(*) INTO v_total FROM public.con_catalogo_insumo
      WHERE version_catalogo=1 AND activo=TRUE AND obligatorio=TRUE
        AND fec_desde<=v_fecha AND (fec_hasta IS NULL OR fec_hasta>=v_fecha);
    IF v_total <> 10 THEN RAISE EXCEPTION 'Catalogo F1 requiere 10 obligatorios: %',v_total; END IF;
    IF EXISTS (
        SELECT 1 FROM public.con_catalogo_insumo
        WHERE version_catalogo=1 AND activo=TRUE AND obligatorio=TRUE
          AND fec_desde<=v_fecha AND (fec_hasta IS NULL OR fec_hasta>=v_fecha)
          AND tipo_insumo NOT IN ('HA22','HA26','HA32','CAET','CANT','DEPO',
                                  'CARTA_COMPENSACION','PMD','MEP','VSS')
    ) THEN RAISE EXCEPTION 'Catalogo F1 contiene insumos no autorizados'; END IF;
    INSERT INTO public.con_insumo_esperado
       (id_jornada,tipo_insumo,fuente,obligatorio,estado)
    SELECT p_id_jornada,tipo_insumo,fuente,obligatorio,'PENDIENTE'
      FROM public.con_catalogo_insumo
     WHERE version_catalogo=1 AND activo=TRUE AND obligatorio=TRUE
       AND fec_desde<=v_fecha AND (fec_hasta IS NULL OR fec_hasta>=v_fecha)
    ON CONFLICT (id_jornada,tipo_insumo) DO NOTHING;
    GET DIAGNOSTICS v_insertados=ROW_COUNT;
    UPDATE public.con_jornada SET version_catalogo=1
      WHERE id_jornada=p_id_jornada AND version_catalogo IS NULL;
    RETURN v_insertados;
END;
$func$;

CREATE OR REPLACE FUNCTION public.fn_consolidar_jornada_tecnica(
    p_id_jornada BIGINT, p_correlation_id VARCHAR
) RETURNS TABLE (id_jornada BIGINT, estado VARCHAR, total_archivos INTEGER, idempotente BOOLEAN)
LANGUAGE plpgsql AS $func$
DECLARE
    v_jornada RECORD;
    v_id BIGINT;
    v_total INTEGER;
    v_catalogo INTEGER;
    v_ha22 BOOLEAN;
    v_ha26 BOOLEAN;
    v_ha32 BOOLEAN;
    v_cambio BOOLEAN;
BEGIN
    IF p_correlation_id IS NULL OR btrim(p_correlation_id)='' THEN
        RAISE EXCEPTION 'Correlation ID obligatorio';
    END IF;
    SELECT * INTO v_jornada FROM public.con_jornada j
     WHERE j.id_jornada=p_id_jornada FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Jornada inexistente'; END IF;
    IF v_jornada.version_catalogo IS DISTINCT FROM 1 THEN
        RAISE EXCEPTION 'Consolidacion F1 solo admite catalogo version 1';
    END IF;
    LOCK TABLE public.con_catalogo_insumo IN SHARE MODE;
    FOR v_id IN SELECT i.id_insumo_esperado FROM public.con_insumo_esperado i
                 WHERE i.id_jornada=p_id_jornada ORDER BY i.id_insumo_esperado LOOP
        PERFORM 1 FROM public.con_insumo_esperado i
          WHERE i.id_insumo_esperado=v_id FOR UPDATE;
    END LOOP;
    FOR v_id IN SELECT DISTINCT i.id_archivo FROM public.con_insumo_esperado i
                 WHERE i.id_jornada=p_id_jornada AND i.id_archivo IS NOT NULL
                 ORDER BY i.id_archivo LOOP
        PERFORM 1 FROM public.con_archivo_carga a WHERE a.id_archivo=v_id FOR UPDATE;
    END LOOP;
    SELECT COUNT(*) INTO v_catalogo FROM public.con_catalogo_insumo c
      WHERE c.version_catalogo=1 AND c.activo=TRUE AND c.obligatorio=TRUE
        AND c.fec_desde<=v_jornada.fecha_contable
        AND (c.fec_hasta IS NULL OR c.fec_hasta>=v_jornada.fecha_contable);
    IF v_catalogo <> 10 THEN RAISE EXCEPTION 'Catalogo F1 incompleto'; END IF;
    IF EXISTS (
       (SELECT i.tipo_insumo,i.fuente,i.obligatorio FROM public.con_insumo_esperado i
          WHERE i.id_jornada=p_id_jornada
        EXCEPT
        SELECT c.tipo_insumo,c.fuente,c.obligatorio FROM public.con_catalogo_insumo c
         WHERE c.version_catalogo=1 AND c.activo=TRUE AND c.obligatorio=TRUE
           AND c.fec_desde<=v_jornada.fecha_contable
           AND (c.fec_hasta IS NULL OR c.fec_hasta>=v_jornada.fecha_contable))
       UNION ALL
       (SELECT c.tipo_insumo,c.fuente,c.obligatorio FROM public.con_catalogo_insumo c
         WHERE c.version_catalogo=1 AND c.activo=TRUE AND c.obligatorio=TRUE
           AND c.fec_desde<=v_jornada.fecha_contable
           AND (c.fec_hasta IS NULL OR c.fec_hasta>=v_jornada.fecha_contable)
        EXCEPT
        SELECT i.tipo_insumo,i.fuente,i.obligatorio FROM public.con_insumo_esperado i
         WHERE i.id_jornada=p_id_jornada)
    ) THEN RAISE EXCEPTION 'Insumos no coinciden con catalogo F1'; END IF;
    SELECT COUNT(*) INTO v_total
      FROM public.con_insumo_esperado i
      JOIN public.con_archivo_carga a ON a.id_archivo=i.id_archivo
     WHERE i.id_jornada=p_id_jornada AND i.obligatorio=TRUE
       AND a.tipo_archivo=i.tipo_insumo AND a.fecha_contable=v_jornada.fecha_contable
       AND ((i.estado='PROCESADO' AND a.estado='PROCESADO')
            OR (i.estado='RECIBIDO' AND a.estado='RECIBIDO' AND a.total_registros=0
                AND EXISTS(SELECT 1 FROM public.con_confirmacion_sin_movimientos c
                           WHERE c.id_archivo=a.id_archivo AND c.id_jornada=p_id_jornada
                             AND c.id_insumo_esperado=i.id_insumo_esperado)));
    IF v_total<>10 OR (SELECT COUNT(*) FROM public.con_insumo_esperado
                        WHERE id_jornada=p_id_jornada)<>10
       OR (SELECT COUNT(DISTINCT id_archivo) FROM public.con_insumo_esperado
            WHERE id_jornada=p_id_jornada)<>10 THEN
        RAISE EXCEPTION 'Jornada % no cumple completitud tecnica',p_id_jornada;
    END IF;
    SELECT COALESCE(bool_or(tipo_insumo='HA22'),FALSE),
           COALESCE(bool_or(tipo_insumo='HA26'),FALSE),
           COALESCE(bool_or(tipo_insumo='HA32'),FALSE)
      INTO v_ha22,v_ha26,v_ha32
      FROM public.con_insumo_esperado
     WHERE id_jornada=p_id_jornada AND estado='PROCESADO' AND id_archivo IS NOT NULL;
    v_cambio := v_jornada.estado IS DISTINCT FROM 'COMPLETADA'
      OR v_jornada.total_archivos IS DISTINCT FROM 10
      OR v_jornada.ha22_recibido IS DISTINCT FROM v_ha22
      OR v_jornada.ha26_recibido IS DISTINCT FROM v_ha26
      OR v_jornada.ha32_recibido IS DISTINCT FROM v_ha32
      OR v_jornada.fec_completitud IS NULL;
    IF NOT v_cambio THEN
        RETURN QUERY SELECT p_id_jornada,v_jornada.estado::VARCHAR,
                            v_jornada.total_archivos,TRUE;
        RETURN;
    END IF;
    UPDATE public.con_jornada j SET estado='COMPLETADA',total_archivos=10,
       ha22_recibido=v_ha22,ha26_recibido=v_ha26,ha32_recibido=v_ha32,
       fec_completitud=COALESCE(j.fec_completitud,CURRENT_TIMESTAMP)
     WHERE j.id_jornada=p_id_jornada;
    INSERT INTO public.con_trazabilidad
       (correlation_id,id_jornada,id_archivo,tipo_evento,componente,detalle)
    VALUES (p_correlation_id,p_id_jornada,NULL,'JORNADA_TECNICA_COMPLETADA',
            'CONSOLIDACION_JORNADA','Jornada F1: 10 insumos procesados o confirmados');
    RETURN QUERY SELECT p_id_jornada,'COMPLETADA'::VARCHAR,10,FALSE;
END;
$func$;
COMMIT;
