-- Cliente 1010223694: el que Luis creo para probar bloqueos (commit "test bloqueos").
--
-- Tenia fixture de financial-overview pero NINGUNA fila en ada_info_detail, asi
-- que sus productos salian del "mock fallback" del servicio: un rescate que se
-- dispara cuando Postgres no devuelve nada. Ese rescate hacia que CUALQUIER
-- customer_id -incluido uno inventado como 'abcdef'- recibiera estos mismos dos
-- productos, con sus ultimos 4 en pantalla. Es decir, datos de otra persona.
--
-- Sembrandolo aqui el cliente deja de depender del rescate, y el rescate puede
-- exigirse explicito (ver analysis_service.consultar_productos_activos).
-- Los valores son los mismos que traia el mock, para no cambiar lo que Luis
-- venia probando.

DELETE FROM public.ada_info_detail WHERE customer_id = '1010223694';
INSERT INTO public.ada_info_detail
  (key_id, contract_id, contract_status_type, contract_status_type_desc,
   card_type, card_type_desc, card_brand, card_status_type, last_four_pan_id,
   card_active_flag, card_flag, origin_flag, customer_id, personal_id,
   personal_type, personal_type_desc, customer_name, first_last_name,
   second_last_name, customer_mail, commercial_product_desc, product_desc,
   seizure_flag, audit_date)
VALUES
 ('KTRXBLQ1','4912680517944979','01','ACTIVO','M','CREDITO','VISA','1','4979',
  true,true,'TDC','1010223694','1010223694','1','Cedula Ciudadania',
  'CLIENTE BLOQUEOS','BLOQUEOS','PRUEBA','bloqueos@mail.com',
  'Tarjeta de Credito','Tarjeta de Credito',false, now()),
 ('KTRXBLQ2','00320011234567','01','ACTIVO','A','AHORROS','MASTERCARD','1','4567',
  true,true,'PASIVO','1010223694','1010223694','1','Cedula Ciudadania',
  'CLIENTE BLOQUEOS','BLOQUEOS','PRUEBA','bloqueos@mail.com',
  'Cuenta de Ahorros','Cuenta de Ahorros',false, now());
