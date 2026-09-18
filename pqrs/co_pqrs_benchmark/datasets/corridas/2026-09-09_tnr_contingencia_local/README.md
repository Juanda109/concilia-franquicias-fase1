# Corrida: trx_no_reconocida_routing en contingencia (local, 9-sep-2026)

- Agente local con `LOCAL_CONTINGENCY_MODE=true` (sin LLM: ruteo por palabras clave).
- Dataset `datasets/trx_no_reconocida_routing.json` (36 casos), `BENCHMARK_SOURCE=benchmark`,
  `RUN_NAME=tnr-contingencia-local`, eventos publicados al pipeline local (37 ok, 0 fallidos).
- Resultado: **20/36 = 55,6 %**, 16 fallos de workflow, 0 de fuga, 0 de paso, 0 sin resolver.
  p95 e2e 1,95 s.

## Lectura

Es el **piso** del flujo, no la medida del LLM. El fallback por palabras clave manda a
trx_no_reconocida todo lo que suena a cobro o movimiento: los 14 vecinos (centrales de
riesgo, consulta de movimientos, extractos, GMF, límites, formulario) caen ahí. Dos frases de
jerga se pierden por otra razón: "me sacaron plata de la cuenta" → certificado_de_cuenta y
"no se q es ese cobro q me aparece de 45.900" → doble_cobro. Los 19 casos que sí apuntan a
trx_no_reconocida aciertan 17.

La corrida con el LLM real (gpt54mini) la hace Pablo con `scripts/run_all_local.sh`.
