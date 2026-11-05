-- Sesion administrada desde base, no un JWT autocontenido: ID_SESION guarda
-- el hash del token opaco de la cookie (nunca el token en claro). El UNIQUE
-- en USUARIO_SUB fuerza una sola sesion activa por usuario - un login nuevo
-- hace upsert y reemplaza/invalida cualquier sesion previa del mismo
-- usuario (ver create_session en session.py). ID_TOKEN es el id_token del
-- IdP, se conserva para poder armar el RP-Initiated Logout contra Nauthilus.
CREATE TABLE IF NOT EXISTS CON_SESION_ACTIVA (
 ID_SESION VARCHAR(64) PRIMARY KEY,
 USUARIO_SUB VARCHAR(100) NOT NULL,
 EMAIL VARCHAR(200),
 NOMBRE VARCHAR(200),
 ROLES TEXT[] NOT NULL,
 ID_TOKEN TEXT,
 FECHA_CREACION TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FECHA_EXPIRA TIMESTAMPTZ NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS UX_CON_SESION_ACTIVA_USUARIO ON CON_SESION_ACTIVA (USUARIO_SUB);
