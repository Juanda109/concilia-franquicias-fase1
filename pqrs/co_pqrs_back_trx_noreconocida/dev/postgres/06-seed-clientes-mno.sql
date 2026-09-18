-- Clientes M, N y O: cierran los tres huecos de cobertura del tramo de Luis.
--
-- Los cuatro desenlaces de la investigacion (2.4.0.1.19) son presencial,
-- reversado, pqr y devolucion. Hasta ahora solo DOS eran alcanzables por la UI:
-- los fixtures de "presencial" y "reversado" vivian en PAN sin entrada en
-- financial-overview ni fichero de transactions, asi que ningun cliente
-- resolvia a esas tarjetas. Solo existian para la prueba unitaria.
--
--   M (1013634970) -> ECI 0. El tablero dice que 0,1,2,3,7 son CONTRACARGABLES
--                     (responsabilidad del comercio), luego debe dar DEVOLUCION.
--                     Hoy da PQR porque el codigo usa {1,2,3,7} y omite el 0.
--                     No existia ni un fixture con eci=0: por eso era invisible.
--   N (1013634971) -> ECI 9  -> desenlace PRESENCIAL   (2.4.0.1.19.1)
--   O (1013634972) -> reversa -> desenlace REVERSADO   (2.4.0.1.19.2)

DELETE FROM public.ada_info_detail WHERE customer_id IN ('1013634970','1013634971','1013634972');

INSERT INTO public.ada_info_detail
  (key_id, contract_id, contract_status_type, contract_status_type_desc,
   card_type, card_type_desc, card_brand, card_status_type, last_four_pan_id,
   card_active_flag, card_flag, origin_flag, customer_id, personal_id,
   personal_type, personal_type_desc, customer_name, first_last_name,
   second_last_name, customer_mail, commercial_product_desc, product_desc,
   seizure_flag, audit_date)
VALUES
 ('KTRXM','00131007201300070','01','ACTIVO','M','CREDITO','VISA','1','0070',
  true,true,'TDC','1013634970','1013634970','1','Cedula Ciudadania',
  'CLIENTE M','M','ECI CERO','m@mail.com','Tarjeta de Credito','Tarjeta de Credito',false, now()),
 ('KTRXN','00131007201300067','01','ACTIVO','M','CREDITO','VISA','1','0067',
  true,true,'TDC','1013634971','1013634971','1','Cedula Ciudadania',
  'CLIENTE N','N','PRESENCIAL','n@mail.com','Tarjeta de Credito','Tarjeta de Credito',false, now()),
 ('KTRXO','00131007201300068','01','ACTIVO','M','CREDITO','VISA','1','0068',
  true,true,'TDC','1013634972','1013634972','1','Cedula Ciudadania',
  'CLIENTE O','O','REVERSADO','o@mail.com','Tarjeta de Credito','Tarjeta de Credito',false, now());
