-- Cliente J: divergencia deliberada entre ADA y financial-overview.
-- ADA dice que la tarjeta termina en 9999 (y el contrato tambien); el PAN real
-- que devuelve financial-overview termina en 4321. Sirve para distinguir de
-- que fuente salen los ultimos 4 que ve el cliente: con el codigo correcto
-- muestra *4321; si mostrara *9999, estaria leyendo de ADA o del contrato.
DELETE FROM public.ada_info_detail WHERE customer_id = '1013634967';
INSERT INTO public.ada_info_detail
  (key_id, contract_id, contract_status_type, contract_status_type_desc,
   card_type, card_type_desc, card_brand, card_status_type, last_four_pan_id,
   card_active_flag, card_flag, origin_flag, customer_id, personal_id,
   personal_type, personal_type_desc, customer_name, first_last_name,
   second_last_name, customer_mail, commercial_product_desc, product_desc,
   seizure_flag, audit_date)
VALUES
 ('KTRXJ','00131007201309999','01','ACTIVO','M','CREDITO','VISA','1','9999',
  true,true,'TDC','1013634967','1013634967','1','Cedula Ciudadania',
  'CLIENTE J','J','DIVERGENCIA','j@mail.com','Tarjeta de Credito','Tarjeta de Credito',false, now());
