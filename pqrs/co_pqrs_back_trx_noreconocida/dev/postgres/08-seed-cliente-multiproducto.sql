-- Cliente P (1013634973): CINCO productos vigentes.
--
-- El selector 2.4.0.1.5 declara cinco posiciones, pero ningun cliente tenia mas
-- de dos, asi que las aristas [Producto 3], [Producto 4] y [Producto 5] eran
-- inalcanzables: no por un defecto, sino porque no existia el dato. Con este
-- cliente se cierran las tres y, de paso, se ejercita el selector en su tope.
DELETE FROM public.ada_info_detail WHERE customer_id = '1013634973';
INSERT INTO public.ada_info_detail
  (key_id, contract_id, contract_status_type, contract_status_type_desc,
   card_type, card_type_desc, card_brand, card_status_type, last_four_pan_id,
   card_active_flag, card_flag, origin_flag, customer_id, personal_id,
   personal_type, personal_type_desc, customer_name, first_last_name,
   second_last_name, customer_mail, commercial_product_desc, product_desc,
   seizure_flag, audit_date)
VALUES
 ('KTRXP1','00131007201300081','01','ACTIVO','M','CREDITO','VISA','1','0081',
  true,true,'TDC','1013634973','1013634973','1','Cedula Ciudadania','CLIENTE P','P','MULTI',
  'p@mail.com','Tarjeta de Credito','Tarjeta de Credito',false, now()),
 ('KTRXP2','00131007201300082','01','ACTIVO','M','CREDITO','VISA','1','0082',
  true,true,'TDC','1013634973','1013634973','1','Cedula Ciudadania','CLIENTE P','P','MULTI',
  'p@mail.com','Tarjeta de Credito Oro','Tarjeta de Credito',false, now()),
 ('KTRXP3','00131007201300083','01','ACTIVO','M','CREDITO','MASTERCARD','1','0083',
  true,true,'TDC','1013634973','1013634973','1','Cedula Ciudadania','CLIENTE P','P','MULTI',
  'p@mail.com','Tarjeta de Credito Platinum','Tarjeta de Credito',false, now()),
 ('KTRXP4','00320011234584','01','ACTIVO','A','AHORROS','VISA','1','0084',
  true,true,'PASIVO','1013634973','1013634973','1','Cedula Ciudadania','CLIENTE P','P','MULTI',
  'p@mail.com','Cuenta de Ahorros','Cuenta de Ahorros',false, now()),
 ('KTRXP5','00320011234585','01','ACTIVO','A','AHORROS','VISA','1','0085',
  true,true,'PASIVO','1013634973','1013634973','1','Cedula Ciudadania','CLIENTE P','P','MULTI',
  'p@mail.com','Cuenta Nomina','Cuenta de Ahorros',false, now());
