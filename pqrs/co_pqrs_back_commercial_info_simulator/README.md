# co_pqrs_back_commercial_info_simulator

Simulador FastAPI del endpoint de commercial information.

Implementa el mismo comportamiento actual del mock:
1. Busca coincidencia exacta por combinacion de query params.
2. Si no llega lastName, busca por documentType + documentNumber.
3. Si no existe match valido, devuelve el JSON default.

## Endpoint

- GET /health
- GET /risks/v0/commercial-information

Query params esperados:
- identityDocument.documentType
- identityDocument.documentNumber
- customer.lastName (opcional)

## Estructura de datos

Los escenarios estan en la carpeta data/.

- scenario_index.json: reglas de ruteo.
- commercial_info_default.json: fallback final.
- commercial_info_*.json: payloads por cliente.

## Ejecutar local

```bash
pip install -e .
uvicorn main:app --reload --host 0.0.0.0 --port 8050
```

## Curls de prueba

Match exacto:

```bash
curl -G "http://localhost:8050/risks/v0/commercial-information" \
  --data-urlencode "identityDocument.documentType=01" \
  --data-urlencode "identityDocument.documentNumber=000001069759414" \
  --data-urlencode "customer.lastName=gutierrez"
```

Fallback default:

```bash
curl -G "http://localhost:8050/risks/v0/commercial-information" \
  --data-urlencode "identityDocument.documentType=01" \
  --data-urlencode "identityDocument.documentNumber=111111111111111" \
  --data-urlencode "customer.lastName=desconocido"
```

## Integracion con co_pqrs_back_data

Configurar en co_pqrs_back_data:

- COMMERCIAL_INFO_SOURCE=api
- COMMERCIAL_INFO_OVERVIEW_URL=http://localhost:8050/risks/v0/commercial-information
- COMMERCIAL_INFO_API_VERIFY_SSL=false

Nota: la validacion 3270 sigue viniendo de Postgres (tabla ada_info_detail), y la validacion de buros viene por llamada HTTP/API al simulador.
