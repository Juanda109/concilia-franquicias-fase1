-- DDL independiente; no cambia jornadas ni catalogos existentes.
-- Ejecutar solamente tras revision de integracion y respaldo en concilia_test.
BEGIN;
DO $$ BEGIN
  IF current_database() <> 'concilia_test' THEN
    RAISE EXCEPTION 'Base no autorizada: %', current_database();
  END IF;
END $$;
CREATE TABLE IF NOT EXISTS public.con_visa_ss_international_detalle (
  id_detalle BIGSERIAL PRIMARY KEY,
  id_archivo BIGINT NOT NULL REFERENCES public.con_archivo_carga(id_archivo),
  fecha_contable DATE NOT NULL,
  linea_origen INTEGER NOT NULL CHECK (linea_origen > 0),
  correlation_id VARCHAR(100) NOT NULL,
  pagina INTEGER NOT NULL CHECK (pagina > 0),
  ftsre VARCHAR(20) NOT NULL,
  nombre_entidad VARCHAR(250) NOT NULL,
  moneda CHAR(3) NOT NULL CHECK (moneda = 'USD'),
  importe_neto NUMERIC(20,2) NOT NULL CHECK (importe_neto > 0),
  tipo_movimiento VARCHAR(2) NOT NULL CHECK (tipo_movimiento IN ('CR','DB')),
  fecha_valor DATE NOT NULL,
  fecha_procesamiento DATE NOT NULL,
  fec_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_visa_ss_international_archivo_linea UNIQUE(id_archivo,linea_origen)
);
CREATE INDEX IF NOT EXISTS ix_visa_ss_international_fecha
  ON public.con_visa_ss_international_detalle(fecha_contable);
COMMIT;
