-- CONCILIA V1 - FASE 1
-- Idempotencia de resultados Host.
-- Aplica a HA22, HA26 y HA32.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM con_host_resultado
        WHERE linea_origen IS NOT NULL
        GROUP BY id_archivo, linea_origen
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'Existen resultados Host duplicados por archivo y linea';
    END IF;
END
$$;

-- Impedir registros sin linea de origen.
-- Requiere que todos los normalizadores proporcionen linea_origen.
ALTER TABLE con_host_resultado
    ALTER COLUMN linea_origen SET NOT NULL;

-- Evitar duplicidad en reintentos.
CREATE UNIQUE INDEX IF NOT EXISTS uq_host_archivo_linea
ON con_host_resultado (
    id_archivo,
    linea_origen
);
