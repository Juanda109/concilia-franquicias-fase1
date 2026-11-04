-- Revocacion server-side de sesiones (logout real, no solo borrar la cookie).
-- Un JTI aqui significa "este token ya no es valido", sin importar que su
-- EXP original todavia no haya pasado. EXPIRA_EN se guarda para poder
-- limpiar filas que ya no hacen falta (el JWT se rechaza por su propio EXP
-- de todas formas una vez pasa esa fecha).
CREATE TABLE IF NOT EXISTS CON_SESION_REVOCADA (
 JTI VARCHAR(64) PRIMARY KEY,
 EXPIRA_EN TIMESTAMPTZ NOT NULL,
 FECHA_REVOCACION TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
