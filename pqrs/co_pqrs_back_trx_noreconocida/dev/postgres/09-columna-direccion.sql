-- Direccion del cliente para el mensaje de reexpedicion de tarjeta.
--
-- El paso 2.4.0.1.17.2 promete: "Te la enviaremos a la direccion {direccion} en
-- un lapso de X dias habiles". El codigo ya busca la direccion entre varias
-- columnas candidatas (aso_rules.filtrar_productos._ADDRESS_COLUMNS), pero
-- ada_info_detail NO TIENE ninguna de ellas en el esquema de desarrollo, asi que
-- siempre caia al texto de respaldo ("registrada en nuestros sistemas") y la
-- promesa quedaba sin dato.
--
-- Se anade la columna y se siembra para los clientes que llegan al bloqueo, de
-- modo que el mensaje se pueda comprobar de verdad. En produccion la columna
-- debe venir del parquet de ADA: confirmar con Nicolas cual es su nombre real
-- (customer_address, address_description, cust_address_desc o street_address:
-- el codigo acepta las cuatro).

ALTER TABLE public.ada_info_detail
  ADD COLUMN IF NOT EXISTS customer_address VARCHAR(200);

UPDATE public.ada_info_detail SET customer_address = 'CALLE 93 # 11-27 APTO 502, BOGOTA'
 WHERE customer_id = '1013634971';
UPDATE public.ada_info_detail SET customer_address = 'CARRERA 15 # 88-64 OFICINA 301, BOGOTA'
 WHERE customer_id = '1013634970';
UPDATE public.ada_info_detail SET customer_address = 'AVENIDA 6N # 23-50 CASA 12, CALI'
 WHERE customer_id = '1013634972';
UPDATE public.ada_info_detail SET customer_address = 'CALLE 10 # 43-20 TORRE B, MEDELLIN'
 WHERE customer_id = '1013634960';
