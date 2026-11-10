-- CONCILIA V1 - FASE 1
-- Migracion 025: detalle MEP Redeban
-- Solo base concilia_test.
-- No modifica estructuras anteriores.

BEGIN;

SET LOCAL lock_timeout = '5s';

DO $$
BEGIN
    IF current_database() <> 'concilia_test' THEN
        RAISE EXCEPTION 'Base de datos no autorizada';
    END IF;
END
$$;

CREATE TABLE public.con_mep_detalle (
    id_detalle BIGSERIAL PRIMARY KEY,

    id_archivo BIGINT NOT NULL
        REFERENCES public.con_archivo_carga(id_archivo),

    fecha_contable DATE NOT NULL,
    linea_origen BIGINT NOT NULL,
    correlation_id VARCHAR(100) NOT NULL,

    centro_de_costo TEXT,
    cuenta TEXT,
    divisa TEXT,
    contrato TEXT,
    referencia_de_cruce TEXT,

    importe NUMERIC(24,4),
    descripcion TEXT,
    fecha DATE,

    tipo_de_documento TEXT,
    numero_de_documento TEXT,
    digito_de_verificacion TEXT,

    tipo_de_perdida TEXT,
    clase_riesgo TEXT,
    tipo_de_movimiento TEXT,
    producto TEXT,
    proceso TEXT,
    linea_operativa TEXT,

    valor_base NUMERIC(24,4),

    CONSTRAINT uq_mep_archivo_linea
        UNIQUE (id_archivo, linea_origen)
);

CREATE INDEX ix_mep_detalle_archivo
    ON public.con_mep_detalle(id_archivo);

CREATE INDEX ix_mep_detalle_cuenta
    ON public.con_mep_detalle(cuenta);

COMMIT;
