-- Catalogo version 2: once insumos; version 1 y jornadas historicas intactas.
-- NO ejecutar hasta integrar funciones de inicializacion y consolidacion versionadas.
BEGIN;
DO $$ BEGIN
 IF current_database() <> 'concilia_test' THEN
  RAISE EXCEPTION 'Base no autorizada: %',current_database();
 END IF;
END $$;
ALTER TABLE public.con_insumo_esperado DROP CONSTRAINT IF EXISTS ck_tipo_insumo_f1;
ALTER TABLE public.con_insumo_esperado ADD CONSTRAINT ck_tipo_insumo_f1
 CHECK (tipo_insumo IN ('HA22','HA26','HA32','CAET','CANT','DEPO',
 'CARTA_COMPENSACION','PMD','MEP','VSS','VISA_SS_INTERNATIONAL'));
ALTER TABLE public.con_catalogo_insumo DROP CONSTRAINT IF EXISTS ck_catalogo_tipo_f1;
ALTER TABLE public.con_catalogo_insumo ADD CONSTRAINT ck_catalogo_tipo_f1
 CHECK (tipo_insumo IN ('HA22','HA26','HA32','CAET','CANT','DEPO','CARTA_COMPENSACION','PMD','MEP','VSS','VISA_SS_INTERNATIONAL'));
ALTER TABLE public.con_catalogo_insumo DROP CONSTRAINT IF EXISTS ck_catalogo_fuente_f1;
ALTER TABLE public.con_catalogo_insumo ADD CONSTRAINT ck_catalogo_fuente_f1
 CHECK ((fuente='HOST' AND tipo_insumo IN ('HA22','HA26','HA32'))
 OR (fuente='CREDIBANCO' AND tipo_insumo IN ('CAET','CANT','DEPO','CARTA_COMPENSACION'))
 OR (fuente='REDEBAN' AND tipo_insumo IN ('PMD','MEP'))
 OR (fuente='VISA' AND tipo_insumo IN ('VSS','VISA_SS_INTERNATIONAL')));
DO $$ BEGIN
 IF (SELECT COUNT(*) FROM public.con_catalogo_insumo WHERE version_catalogo=1 AND activo AND obligatorio)=10 THEN
  INSERT INTO public.con_catalogo_insumo(tipo_insumo,fuente,version_catalogo,obligatorio,activo,fec_desde,fec_hasta)
  SELECT tipo_insumo,fuente,2,obligatorio,activo,fec_desde,fec_hasta
  FROM public.con_catalogo_insumo WHERE version_catalogo=1
  ON CONFLICT (tipo_insumo,version_catalogo) DO NOTHING;
 ELSE RAISE EXCEPTION 'Version 1 no tiene exactamente 10 insumos'; END IF;
END $$;
INSERT INTO public.con_catalogo_insumo(tipo_insumo,fuente,version_catalogo,obligatorio,activo,fec_desde,fec_hasta)
VALUES ('VISA_SS_INTERNATIONAL','VISA',2,TRUE,TRUE,'2026-01-01',NULL)
ON CONFLICT (tipo_insumo,version_catalogo) DO NOTHING;
DO $$ BEGIN
 IF (SELECT COUNT(*) FROM public.con_catalogo_insumo WHERE version_catalogo=2 AND activo AND obligatorio)<>11 THEN
  RAISE EXCEPTION 'Version 2 no tiene exactamente 11 insumos';
 END IF;
END $$;
COMMIT;
