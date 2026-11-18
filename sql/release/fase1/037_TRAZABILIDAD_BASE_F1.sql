-- CONCILIA V1 FASE 1. Ejecutar despues de crear con_archivo_carga y con_jornada.
-- Exclusivamente para base nueva; NO altera tablas existentes ni elimina columnas F2.
BEGIN;
CREATE TABLE IF NOT EXISTS public.con_trazabilidad (
  id_trazabilidad BIGSERIAL PRIMARY KEY,
  correlation_id VARCHAR(64) NOT NULL,
  id_archivo BIGINT REFERENCES public.con_archivo_carga(id_archivo),
  id_jornada BIGINT REFERENCES public.con_jornada(id_jornada),
  tipo_evento VARCHAR(50) NOT NULL,
  componente VARCHAR(80) NOT NULL,
  detalle VARCHAR(2000),
  fec_evento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_traza_corr ON public.con_trazabilidad(correlation_id);
CREATE INDEX IF NOT EXISTS ix_traza_jornada ON public.con_trazabilidad(id_jornada);
CREATE INDEX IF NOT EXISTS ix_traza_archivo ON public.con_trazabilidad(id_archivo);
COMMIT;
