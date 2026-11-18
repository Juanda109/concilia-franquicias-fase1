-- CONCILIA V1 - FASE 1
-- Migracion 020: detalle Host tipado
-- Requiere migracion 019 aplicada.
-- Conserva campos_origen JSONB y CON_HOST_RESULTADO.

BEGIN;

SET LOCAL lock_timeout = '5s';

DO $$
BEGIN
    IF current_database() <> 'concilia_test' THEN
        RAISE EXCEPTION 'Base de datos no autorizada';
    END IF;
END
$$;

-- HA22
ALTER TABLE public.con_ha22_detalle
    ADD COLUMN tx_origen VARCHAR(10),
    ADD COLUMN tabla_origen VARCHAR(30),
    ADD COLUMN empresa VARCHAR(20),
    ADD COLUMN nucta VARCHAR(30),
    ADD COLUMN ceorigen VARCHAR(20),
    ADD COLUMN cedestin VARCHAR(20),
    ADD COLUMN fecon DATE,
    ADD COLUMN feproc DATE,
    ADD COLUMN numas VARCHAR(30),
    ADD COLUMN numap VARCHAR(30),
    ADD COLUMN debe NUMERIC(24,4),
    ADD COLUMN haber NUMERIC(24,4),
    ADD COLUMN clacon VARCHAR(30),
    ADD COLUMN descon TEXT,
    ADD COLUMN tipapun VARCHAR(30),
    ADD COLUMN numdo VARCHAR(40),
    ADD COLUMN observ TEXT,
    ADD COLUMN observ2 TEXT,
    ADD COLUMN codusu VARCHAR(40),
    ADD COLUMN horatr TEXT;

-- HA26
ALTER TABLE public.con_ha26_detalle
    ADD COLUMN tx_origen VARCHAR(10),
    ADD COLUMN tabla_origen VARCHAR(30),
    ADD COLUMN empresa VARCHAR(20),
    ADD COLUMN nucta VARCHAR(30),
    ADD COLUMN ceorigen VARCHAR(20),
    ADD COLUMN cedestin VARCHAR(20),
    ADD COLUMN fecon DATE,
    ADD COLUMN feproc DATE,
    ADD COLUMN numas VARCHAR(30),
    ADD COLUMN numap VARCHAR(30),
    ADD COLUMN debe NUMERIC(24,4),
    ADD COLUMN haber NUMERIC(24,4),
    ADD COLUMN clacon VARCHAR(30),
    ADD COLUMN descon TEXT,
    ADD COLUMN tipapun VARCHAR(30),
    ADD COLUMN haynumdo VARCHAR(10),
    ADD COLUMN numdo VARCHAR(40),
    ADD COLUMN observ TEXT,
    ADD COLUMN observ2 TEXT,
    ADD COLUMN codusu VARCHAR(40),
    ADD COLUMN horatr TEXT;

-- HA32
ALTER TABLE public.con_ha32_detalle
    ADD COLUMN tx_origen VARCHAR(10),
    ADD COLUMN tabla_origen VARCHAR(30),
    ADD COLUMN tabla_origen1 VARCHAR(30),
    ADD COLUMN empresa VARCHAR(20),
    ADD COLUMN nucta VARCHAR(30),
    ADD COLUMN cedestin VARCHAR(20),
    ADD COLUMN fecont DATE,
    ADD COLUMN debe NUMERIC(24,4),
    ADD COLUMN haber NUMERIC(24,4),
    ADD COLUMN saldo_inicial NUMERIC(24,4);

COMMIT;
