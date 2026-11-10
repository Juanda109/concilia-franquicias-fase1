-- CONCILIA V1 - FASE 1
-- Migracion 024: detalle agregado PMD Redeban
-- Requiere migraciones anteriores aplicadas.
-- Solo base concilia_test.

BEGIN;

SET LOCAL lock_timeout = '5s';

DO $$
BEGIN
    IF current_database() <> 'concilia_test' THEN
        RAISE EXCEPTION 'Base de datos no autorizada';
    END IF;
END
$$;

CREATE TABLE public.con_pmd_detalle (
    id_detalle BIGSERIAL PRIMARY KEY,

    id_archivo BIGINT NOT NULL
        REFERENCES public.con_archivo_carga(id_archivo),

    fecha_contable DATE NOT NULL,
    linea_origen BIGINT NOT NULL,
    correlation_id VARCHAR(100) NOT NULL,

    producto_servicio TEXT NOT NULL,
    nivel TEXT NOT NULL,
    es_control BOOLEAN NOT NULL,
    fecha_archivo VARCHAR(8) NOT NULL,

    debito_cantidad NUMERIC(24,4),
    debito_valor NUMERIC(24,4),
    debito_comision_intercambio NUMERIC(24,4),
    debito_comision_administrativa NUMERIC(24,4),
    debito_neto NUMERIC(24,4),

    credito_cantidad NUMERIC(24,4),
    credito_valor NUMERIC(24,4),
    credito_comision_intercambio NUMERIC(24,4),
    credito_comision_administrativa NUMERIC(24,4),
    credito_neto NUMERIC(24,4),

    total NUMERIC(24,4),

    CONSTRAINT uq_pmd_archivo_linea
        UNIQUE (id_archivo, linea_origen),

    CONSTRAINT ck_pmd_debito_cantidad
        CHECK (
            debito_cantidad IS NULL OR
            (
                debito_cantidad >= 0 AND
                debito_cantidad = TRUNC(debito_cantidad)
            )
        ),

    CONSTRAINT ck_pmd_credito_cantidad
        CHECK (
            credito_cantidad IS NULL OR
            (
                credito_cantidad >= 0 AND
                credito_cantidad = TRUNC(credito_cantidad)
            )
        )
);

CREATE INDEX ix_pmd_detalle_archivo
    ON public.con_pmd_detalle(id_archivo);

CREATE INDEX ix_pmd_detalle_producto_nivel
    ON public.con_pmd_detalle(
        producto_servicio,
        nivel
    );

COMMIT;
