-- Cliente 1013634958: el unico del ambiente con una gestion previa de transaccion no
-- reconocida en el simulador (data/salesforce/1013634958.json, caso del 01/08/2026,
-- asunto "Usuario reporta que no reconoce la transaccion").
--
-- Sirve para la prueba T12 del informe funcional: volver a reportar un caso ya gestionado
-- y comprobar que el tramite lo detecta y deriva en vez de abrir otro.
--
-- Sin esta fila la prueba no puede salir bien: con TRX_SALESFORCE_SOURCE=aso el tramite
-- resuelve la identidad del cliente en esta tabla para preguntar al simulador por su
-- documento; si no la encuentra, vuelve al listado fijo (aso_fallback_sin_identidad),
-- que no distingue por cliente. El 15/09 se ejecuto T12 sin esta fila y sin la fuente
-- ajustada, y el tramite no encontro la gestion previa (hallazgo del informe).
--
-- personal_id tiene que ser 1013634958: el simulador nombra el fichero de Salesforce por el
-- numero de documento, no por customer_id (resolver._doc_number_from_target).
--
-- Se aplica igual que los demas seeds de esta carpeta. Es idempotente.

DELETE FROM public.ada_info_detail WHERE customer_id = '1013634958';
INSERT INTO public.ada_info_detail
  (key_id, contract_id, contract_status_type, contract_status_type_desc,
   card_type, card_type_desc, card_brand, card_status_type, last_four_pan_id,
   card_active_flag, card_flag, origin_flag, customer_id, personal_id,
   personal_type, personal_type_desc, customer_name, first_last_name,
   second_last_name, customer_mail, commercial_product_desc, product_desc,
   seizure_flag, audit_date)
VALUES
 ('KTRXREC1','4912680517940058','01','ACTIVO','M','CREDITO','VISA','1','0058',
  true,true,'TDC','1013634958','1013634958','1','Cedula Ciudadania',
  'CLIENTE RECURRENCIA','RECURRENCIA','PRUEBA','recurrencia@mail.com',
  'Tarjeta de Credito','Tarjeta de Credito',false, now());
