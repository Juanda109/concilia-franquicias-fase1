-- CONCILIA V1 - MVP1
-- BORRADOR: NO EJECUTAR.
-- Trazabilidad explicita de jornada.
-- Conserva los eventos existentes.

BEGIN;

SET LOCAL lock_timeout = '5s';

DO $$
BEGIN
    IF current_database() <> 'concilia_test' THEN
        RAISE EXCEPTION 'Base de datos no autorizada';
    END IF;
END
$$;

ALTER TABLE public.con_trazabilidad
    ADD COLUMN id_jornada BIGINT;

ALTER TABLE public.con_trazabilidad
    ADD CONSTRAINT fk_trazabilidad_jornada
    FOREIGN KEY (id_jornada)
    REFERENCES public.con_jornada(id_jornada);

CREATE INDEX ix_trazabilidad_jornada
    ON public.con_trazabilidad(
        id_jornada,
        fec_evento
    );

COMMIT;
