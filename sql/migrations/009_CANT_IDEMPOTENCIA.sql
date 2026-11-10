-- CONCILIA V1 - FASE 1
-- Idempotencia de resultados CANT.
-- No modifica la estructura de otros insumos.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM con_franquicia_resultado
        WHERE reporte_origen = 'CANT'
        GROUP BY id_archivo, linea_origen, concepto
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'Existen resultados CANT duplicados';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM con_franquicia_resultado
        WHERE reporte_origen = 'CANT'
          AND (
              linea_origen IS NULL
              OR concepto IS NULL
          )
    ) THEN
        RAISE EXCEPTION
            'Existen resultados CANT sin identidad completa';
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_cant_archivo_linea_concepto
ON con_franquicia_resultado (
    id_archivo,
    linea_origen,
    concepto
)
WHERE reporte_origen = 'CANT';
