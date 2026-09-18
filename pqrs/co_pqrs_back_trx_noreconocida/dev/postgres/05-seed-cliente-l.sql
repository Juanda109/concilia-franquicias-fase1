-- Cliente L: todos sus movimientos del dia quedan FUERA del rango
-- 35.000-500.000 (18.000 y 890.000). Sirve para ver el aviso que distingue
-- "no tienes movimientos" de "los tienes, pero fuera de lo que gestiona este
-- canal". Ver docs/HALLAZGO_VISUALIZACION_MOVIMIENTOS.md, propuesta 2.
DELETE FROM public.ada_info_detail WHERE customer_id = '1013634969';
INSERT INTO public.ada_info_detail
  (key_id, contract_id, contract_status_type, contract_status_type_desc,
   card_type, card_type_desc, card_brand, card_status_type, last_four_pan_id,
   card_active_flag, card_flag, origin_flag, customer_id, personal_id,
   personal_type, personal_type_desc, customer_name, first_last_name,
   second_last_name, customer_mail, commercial_product_desc, product_desc,
   seizure_flag, audit_date)
VALUES
 ('KTRXL','00131009201305555','01','ACTIVO','M','CREDITO','VISA','1','5555',
  true,true,'TDC','1013634969','1013634969','1','Cedula Ciudadania',
  'CLIENTE L','L','RANGO','l@mail.com','Tarjeta de Credito','Tarjeta de Credito',false, now());
