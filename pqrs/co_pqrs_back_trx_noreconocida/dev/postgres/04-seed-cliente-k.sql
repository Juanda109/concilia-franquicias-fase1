-- Cliente K: volumen y filtros. Un dia con 7 movimientos que ejercitan los tres
-- puntos donde se pierde informacion antes de llegar al cliente: el truncado a 3
-- de la presentacion, el filtro de importe (35.000-500.000) y la exclusion de
-- abonos (moneyFlow=EXPENSE). Ver docs/HALLAZGO_VISUALIZACION_MOVIMIENTOS.md.
DELETE FROM public.ada_info_detail WHERE customer_id = '1013634968';
INSERT INTO public.ada_info_detail
  (key_id, contract_id, contract_status_type, contract_status_type_desc,
   card_type, card_type_desc, card_brand, card_status_type, last_four_pan_id,
   card_active_flag, card_flag, origin_flag, customer_id, personal_id,
   personal_type, personal_type_desc, customer_name, first_last_name,
   second_last_name, customer_mail, commercial_product_desc, product_desc,
   seizure_flag, audit_date)
VALUES
 ('KTRXK','00131008201304444','01','ACTIVO','M','CREDITO','VISA','1','4444',
  true,true,'TDC','1013634968','1013634968','1','Cedula Ciudadania',
  'CLIENTE K','K','VOLUMEN','k@mail.com','Tarjeta de Credito','Tarjeta de Credito',false, now());
