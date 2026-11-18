BEGIN;

-- Retiro definitivo del insumo operativo. Los seis archivos y sus 28 detalles
-- historicos se conservan. Esta migracion no borra archivos ni detalles MEP.

DO $$
DECLARE
    v_catalogo INTEGER;
    v_esperados INTEGER;
    v_pendientes INTEGER;
    v_procesados INTEGER;
    v_archivos INTEGER;
    v_detalles INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_catalogo
      FROM public.con_catalogo_insumo
     WHERE tipo_insumo = 'MEP';

    SELECT COUNT(*) INTO v_esperados
      FROM public.con_insumo_esperado
     WHERE tipo_insumo = 'MEP';

    SELECT COUNT(*) INTO v_pendientes
      FROM public.con_insumo_esperado
     WHERE tipo_insumo = 'MEP'
       AND estado = 'PENDIENTE'
       AND id_archivo IS NULL;

    SELECT COUNT(*) INTO v_procesados
      FROM public.con_insumo_esperado
     WHERE tipo_insumo = 'MEP'
       AND estado = 'PROCESADO'
       AND id_archivo IS NOT NULL;

    SELECT COUNT(*) INTO v_archivos
      FROM public.con_archivo_carga
     WHERE tipo_archivo = 'MEP'
       AND estado = 'PROCESADO';

    SELECT COUNT(*) INTO v_detalles
      FROM public.con_mep_detalle;

    IF v_catalogo <> 2 OR v_esperados <> 18 OR v_pendientes <> 12
       OR v_procesados <> 6 OR v_archivos <> 6 OR v_detalles <> 28 THEN
        RAISE EXCEPTION
          'Prevalidacion MEP no coincide. catalogo=%, esperados=%, pendientes_sin_archivo=%, procesados=%, archivos=%, detalles=%',
          v_catalogo, v_esperados, v_pendientes, v_procesados, v_archivos, v_detalles;
    END IF;

    IF EXISTS (
        SELECT 1
          FROM public.con_insumo_esperado
         WHERE tipo_insumo = 'MEP'
           AND estado = 'PENDIENTE'
           AND id_archivo IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'Existe expectativa MEP pendiente con archivo asociado; requiere revision manual';
    END IF;

    IF to_regclass('public.con_mep_retiro_catalogo_backup_033') IS NOT NULL
       OR to_regclass('public.con_mep_retiro_insumos_backup_033') IS NOT NULL THEN
        RAISE EXCEPTION 'Ya existen tablas de respaldo 033; no se repite la migracion';
    END IF;
END $$;

-- Respaldos permanentes de las filas que se van a desactivar/eliminar.
CREATE TABLE public.con_mep_retiro_catalogo_backup_033 AS
SELECT c.*, CURRENT_TIMESTAMP AS respaldado_en
  FROM public.con_catalogo_insumo c
 WHERE FALSE;

INSERT INTO public.con_mep_retiro_catalogo_backup_033
SELECT c.*, CURRENT_TIMESTAMP
  FROM public.con_catalogo_insumo c
 WHERE c.tipo_insumo = 'MEP';

CREATE TABLE public.con_mep_retiro_insumos_backup_033 AS
SELECT i.*, j.fecha_contable, j.estado AS estado_jornada,
       CURRENT_TIMESTAMP AS respaldado_en
  FROM public.con_insumo_esperado i
  JOIN public.con_jornada j ON j.id_jornada = i.id_jornada
 WHERE FALSE;

INSERT INTO public.con_mep_retiro_insumos_backup_033
SELECT i.*, j.fecha_contable, j.estado,
       CURRENT_TIMESTAMP
  FROM public.con_insumo_esperado i
  JOIN public.con_jornada j ON j.id_jornada = i.id_jornada
 WHERE i.tipo_insumo = 'MEP'
   AND i.estado = 'PENDIENTE'
   AND i.id_archivo IS NULL;

-- Evidencia de la retirada de cada expectativa pendiente antes de retirarla.
INSERT INTO public.con_trazabilidad (
    correlation_id, id_archivo, id_jornada,
    tipo_evento, componente, detalle
)
SELECT
    md5(random()::text || clock_timestamp()::text || i.id_insumo_esperado::text),
    NULL,
    i.id_jornada,
    'INSUMO_RETIRADO',
    'MIGRACION_033',
    'Retiro del insumo MEP pendiente sin archivo; id_insumo_esperado='
        || i.id_insumo_esperado::text
        || '; fecha_contable=' || j.fecha_contable::text
FROM public.con_insumo_esperado i
JOIN public.con_jornada j ON j.id_jornada = i.id_jornada
WHERE i.tipo_insumo = 'MEP'
  AND i.estado = 'PENDIENTE'
  AND i.id_archivo IS NULL;

DELETE FROM public.con_insumo_esperado
 WHERE tipo_insumo = 'MEP'
   AND estado = 'PENDIENTE'
   AND id_archivo IS NULL;

-- Desactivar versiones V1 y V2 del catalogo. No se modifican expectativas
-- procesadas historicas ni se elimina el detalle fuente historico.
UPDATE public.con_catalogo_insumo
   SET activo = FALSE
 WHERE tipo_insumo = 'MEP'
   AND activo = TRUE;

-- Bloquear altas/reactivaciones del tipo retirado en catalogo.
CREATE OR REPLACE FUNCTION public.fn_bloquear_mep_catalogo_033()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.tipo_insumo = 'MEP'
       AND (TG_OP = 'INSERT' OR COALESCE(NEW.activo, FALSE)) THEN
        RAISE EXCEPTION 'El tipo de insumo retirado no puede incorporarse ni activarse';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_bloquear_mep_catalogo_033
    ON public.con_catalogo_insumo;
CREATE TRIGGER trg_bloquear_mep_catalogo_033
BEFORE INSERT OR UPDATE OF tipo_insumo, activo
ON public.con_catalogo_insumo
FOR EACH ROW EXECUTE FUNCTION public.fn_bloquear_mep_catalogo_033();

-- Mantener las filas procesadas historicas, pero impedir nuevas expectativas.
CREATE OR REPLACE FUNCTION public.fn_bloquear_mep_insumo_033()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.tipo_insumo = 'MEP' THEN
        IF TG_OP = 'INSERT' THEN
            RAISE EXCEPTION 'El tipo de insumo retirado no admite nuevas expectativas';
        ELSIF OLD.tipo_insumo IS DISTINCT FROM NEW.tipo_insumo THEN
            RAISE EXCEPTION 'El tipo de insumo retirado no admite nuevas expectativas';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_bloquear_mep_insumo_033
    ON public.con_insumo_esperado;
CREATE TRIGGER trg_bloquear_mep_insumo_033
BEFORE INSERT OR UPDATE OF tipo_insumo
ON public.con_insumo_esperado
FOR EACH ROW EXECUTE FUNCTION public.fn_bloquear_mep_insumo_033();

-- Impedir nuevos archivos del tipo retirado sin alterar las seis cargas antiguas.
CREATE OR REPLACE FUNCTION public.fn_bloquear_mep_archivo_033()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.tipo_archivo = 'MEP' THEN
        IF TG_OP = 'INSERT' THEN
            RAISE EXCEPTION 'El tipo de archivo retirado no admite nuevas cargas';
        ELSIF OLD.tipo_archivo IS DISTINCT FROM NEW.tipo_archivo THEN
            RAISE EXCEPTION 'El tipo de archivo retirado no admite nuevas cargas';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_bloquear_mep_archivo_033
    ON public.con_archivo_carga;
CREATE TRIGGER trg_bloquear_mep_archivo_033
BEFORE INSERT OR UPDATE OF tipo_archivo
ON public.con_archivo_carga
FOR EACH ROW EXECUTE FUNCTION public.fn_bloquear_mep_archivo_033();

-- La tabla de detalle conserva su historia en modo de solo lectura.
CREATE OR REPLACE FUNCTION public.fn_mep_detalle_historico_solo_lectura_033()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'El detalle historico del tipo retirado es de solo lectura';
END;
$$;

DROP TRIGGER IF EXISTS trg_mep_detalle_historico_solo_lectura_033
    ON public.con_mep_detalle;
CREATE TRIGGER trg_mep_detalle_historico_solo_lectura_033
BEFORE INSERT OR UPDATE OR DELETE
ON public.con_mep_detalle
FOR EACH ROW EXECUTE FUNCTION public.fn_mep_detalle_historico_solo_lectura_033();

-- Ajustar el conteo del catalogo de inicializacion: V1 pasa de 10 a 9
-- (catalogo historico sin el tipo retirado); V2 pasa de 11 a 10 y coincide
-- con la linea base funcional vigente que incluye el PDF Visa.
CREATE OR REPLACE FUNCTION public.fn_inicializar_insumos_jornada(
    p_id_jornada BIGINT,
    p_version_catalogo INTEGER
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_fecha DATE;
    v_version INTEGER;
    v_total INTEGER;
    v_existentes INTEGER;
    v_insertados INTEGER;
BEGIN
    IF p_version_catalogo IS NULL OR p_version_catalogo <= 0 THEN
        RAISE EXCEPTION 'Version de catalogo invalida';
    END IF;

    SELECT fecha_contable, version_catalogo
      INTO v_fecha, v_version
      FROM public.con_jornada
     WHERE id_jornada = p_id_jornada
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Jornada inexistente: %', p_id_jornada;
    END IF;

    IF v_version IS NOT NULL AND v_version <> p_version_catalogo THEN
        RAISE EXCEPTION
          'Cambio de version no permitido: jornada %, actual %, solicitada %',
          p_id_jornada, v_version, p_version_catalogo;
    END IF;

    SELECT COUNT(*) INTO v_existentes
      FROM public.con_insumo_esperado
     WHERE id_jornada = p_id_jornada;

    IF v_version IS NULL AND v_existentes > 0 THEN
        RAISE EXCEPTION
          'Jornada % tiene insumos sin version de catalogo', p_id_jornada;
    END IF;

    SELECT COUNT(*) INTO v_total
      FROM public.con_catalogo_insumo
     WHERE version_catalogo = p_version_catalogo
       AND activo = TRUE
       AND fec_desde <= v_fecha
       AND (fec_hasta IS NULL OR fec_hasta >= v_fecha);

    IF v_total <> (CASE p_version_catalogo WHEN 1 THEN 9 WHEN 2 THEN 10 ELSE -1 END) THEN
        RAISE EXCEPTION
          'Catalogo incompleto para jornada %, version %: %',
          p_id_jornada, p_version_catalogo, v_total;
    END IF;

    INSERT INTO public.con_insumo_esperado (
        id_jornada, tipo_insumo, fuente, obligatorio, estado
    )
    SELECT
        p_id_jornada, tipo_insumo, fuente, obligatorio, 'PENDIENTE'
      FROM public.con_catalogo_insumo
     WHERE version_catalogo = p_version_catalogo
       AND activo = TRUE
       AND fec_desde <= v_fecha
       AND (fec_hasta IS NULL OR fec_hasta >= v_fecha)
    ON CONFLICT (id_jornada, tipo_insumo) DO NOTHING;

    GET DIAGNOSTICS v_insertados = ROW_COUNT;

    UPDATE public.con_jornada
       SET version_catalogo = p_version_catalogo
     WHERE id_jornada = p_id_jornada
       AND version_catalogo IS NULL;

    RETURN v_insertados;
END;
$$;

-- Comprobacion de salida: exactamente diez registros funcionales en catalogo V2.
DO $$
DECLARE
    v_v2 INTEGER;
    v_mep_activo INTEGER;
    v_mep_pendiente INTEGER;
    v_historicos INTEGER;
    v_detalles INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_v2
      FROM public.con_catalogo_insumo
     WHERE version_catalogo = 2 AND activo = TRUE;
    SELECT COUNT(*) INTO v_mep_activo
      FROM public.con_catalogo_insumo
     WHERE tipo_insumo = 'MEP' AND activo = TRUE;
    SELECT COUNT(*) INTO v_mep_pendiente
      FROM public.con_insumo_esperado
     WHERE tipo_insumo = 'MEP' AND estado = 'PENDIENTE';
    SELECT COUNT(*) INTO v_historicos
      FROM public.con_archivo_carga
     WHERE tipo_archivo = 'MEP' AND estado = 'PROCESADO';
    SELECT COUNT(*) INTO v_detalles FROM public.con_mep_detalle;

    IF v_v2 <> 10 OR v_mep_activo <> 0 OR v_mep_pendiente <> 0
       OR v_historicos <> 6 OR v_detalles <> 28 THEN
        RAISE EXCEPTION
          'Postvalidacion MEP fallida. catalogo_v2=%, catalogo_mep_activo=%, pendientes=%, archivos_historicos=%, detalles=%',
          v_v2, v_mep_activo, v_mep_pendiente, v_historicos, v_detalles;
    END IF;
END $$;

COMMIT;
