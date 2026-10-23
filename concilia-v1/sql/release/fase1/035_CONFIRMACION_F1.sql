-- CONCILIA V1 - FASE 1
-- Confirmacion sin movimientos
-- Independiente del catalogo V2.

BEGIN;

CREATE TABLE IF NOT EXISTS public.con_confirmacion_sin_movimientos (
    id_archivo BIGINT PRIMARY KEY
        REFERENCES public.con_archivo_carga(id_archivo),
    id_jornada BIGINT NOT NULL
        REFERENCES public.con_jornada(id_jornada),
    id_insumo_esperado BIGINT NOT NULL
        REFERENCES public.con_insumo_esperado(id_insumo_esperado),
    usuario VARCHAR(100) NOT NULL,
    motivo VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(100),
    fec_confirmacion TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);

COMMIT;