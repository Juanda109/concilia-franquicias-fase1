-- CONCILIA V1 - FASE 1
-- Migracion 026: detalle VSS Visa.
-- Solo concilia_test.
-- Conserva los reportes VSS-110, VSS-115 y VSS-120.
-- No modifica las estructuras anteriores.

BEGIN;

SET LOCAL lock_timeout = '5s';

DO $$
BEGIN
    IF current_database() <> 'concilia_test' THEN
        RAISE EXCEPTION 'Base de datos no autorizada';
    END IF;
END
$$;

CREATE TABLE public.con_vss_detalle (
    id_detalle BIGSERIAL PRIMARY KEY,

    id_archivo BIGINT NOT NULL
        REFERENCES public.con_archivo_carga(id_archivo),

    fecha_contable DATE NOT NULL,
    linea_origen BIGINT NOT NULL,
    correlation_id VARCHAR(100) NOT NULL,

    reporte TEXT NOT NULL,
    pagina INTEGER NOT NULL,

    moneda_liquidacion TEXT,
    moneda_compensacion TEXT,
    fecha_reporte TEXT,

    concepto TEXT NOT NULL,

    valores JSONB NOT NULL,
    signos JSONB NOT NULL,

    texto_original TEXT,
    es_control BOOLEAN NOT NULL,

    CONSTRAINT uq_vss_archivo_linea
        UNIQUE (id_archivo, linea_origen),

    CONSTRAINT ck_vss_valores_array
        CHECK (jsonb_typeof(valores) = 'array'),

    CONSTRAINT ck_vss_signos_array
        CHECK (jsonb_typeof(signos) = 'array'),

    CONSTRAINT ck_vss_longitudes
        CHECK (
            jsonb_array_length(valores) =
            jsonb_array_length(signos)
        ),

    CONSTRAINT ck_vss_pagina
        CHECK (pagina > 0)
);

CREATE INDEX ix_vss_detalle_archivo
    ON public.con_vss_detalle(id_archivo);

CREATE INDEX ix_vss_detalle_reporte
    ON public.con_vss_detalle(id_archivo, reporte);

COMMIT;
