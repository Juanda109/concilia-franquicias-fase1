# Gobierno y operación del agente IA

> Controles KYNS IT 2.1, 2.2, 2.4, 2.5 y 2.6. Versión del 2026-09-10. Describe cómo se
> gobierna lo que ya existe; los nombres de los responsables los confirma Fabián.

## 1. Roles

| Activo | Responsable | Decide | Ejecuta |
|---|---|---|---|
| Modelo (deployment de Azure OpenAI, versión, proveedor) | líder técnico | cambio de modelo, rotación de claves | infraestructura |
| Prompts (`routing_prompt.yml`, prompts de validación, clasificación y cierre) | LLMOps | cambios y su evaluación | LLMOps |
| Catálogo de ruteo (`general.yml`) y flujos YAML | dueño del flujo (Diego para TXNR y doble cobro) con negocio | qué caminos existen y qué texto ve el cliente | dueño del flujo |
| Guardrails (`src/guardrail/`) | LLMOps con seguridad | patrones, juez de alcance, mensajes de bloqueo | LLMOps |
| Monitoreo (tableros, alertas, canario) | LLMOps | umbrales, destinatarios, cadencia | LLMOps; encendido en OKD por el líder técnico |
| Datos y trazas (MinIO, OpenSearch) | líder técnico | retención, depuración de histórico | infraestructura |

## 2. Inventario de configuración

La **ficha de versión** (`scripts/build_release_card.py`) es el inventario: para un commit
reúne las imágenes del IaC, el modelo y los embeddings, los portones (`TRX_FLOW_ENABLED`,
`LLM_CLOSURE_ENABLED`, juez de guardrail, topes diarios), la huella y el último cambio del
catálogo, los prompts, los flujos y el guardrail, los datasets y los umbrales de alerta. Se
genera con cada corrida completa (`run_all_local.sh`) y con cada promoción, y se guarda junto a
la evidencia. Finalidad del modelo: enrutar y validar texto de PQRS bancarias; no redacta al
cliente salvo el cierre de guía rápida, apagado por defecto.

## 3. Gestión de cambios

Un cambio se clasifica por lo que toca y eso fija la evaluación que exige (tabla completa en
`PLAN_DE_PRUEBAS_IA.md` §5):

1. **Flujo YAML o servicio**: golden paths y suite del servicio en el mismo cambio, benchmark
   del flujo y bypass. El catálogo de capacidades se regenera; si aparece una acción nueva sin
   clasificar, o un camino que se salta una puerta, el test lo bloquea.
2. **Catálogo o prompt del router**: benchmark de todos los flujos y adversarial, comparación
   caso a caso contra la corrida anterior, mayoría de tres en los casos frontera.
3. **Guardrail**: corpus de falsos positivos (quejas reales) y adversarial.
4. **Modelo o proveedor**: evaluación completa con firma (todas las capas, incluido grounding),
   y piso de contingencia remedido.
5. **Configuración**: golden paths; si cambia un límite financiero, aprobación de negocio.

Ningún cambio se promueve con una suite roja, un `fallos_leak` o `fallos_step` distinto de cero,
o un hallazgo crítico abierto sin fecha. El PR lleva el enlace a la corrida.

## 4. Gobierno del catálogo (base de conocimiento)

- **Fuente de verdad**: `general.yml` y los YAML de flujo en git; el Excel de ruteo es
  referencia externa y nunca se lee en tiempo de ejecución.
- **Aprobación**: un cambio de texto al cliente o de rutas lo aprueba negocio en el PR; un
  cambio de ejemplos o contraejemplos del router lo aprueba LLMOps con el benchmark.
- **Versionamiento**: el commit del catálogo viaja en cada corrida (`catalog_version`) y en
  cada evento de conversación; la ficha de versión guarda su huella.
- **Vigencia y retiro**: una ruta se retira quitándola del catálogo y dejando el caso en el
  benchmark como contraejemplo (así se comprueba que ya no se enruta). Las rutas "aún no
  disponibles" se declaran como contraejemplo, nunca como opción vacía.
- **Contenido sensible**: el catálogo no contiene datos de clientes; los fixtures con datos
  reales se retiran (caso del CSV con cliente real del 8/09).

## 5. Contingencia

| Situación | Señal | Quién decide | Acción |
|---|---|---|---|
| Proveedor del LLM caído o lento | alertas del canario (precisión < umbral, ruta caída), p95 de ruteo | LLMOps avisa, líder técnico decide | el agente ya cae solo a contingencia (ruteo por palabras clave); se comunica el piso medido y se vigila `fallos_leak = 0` |
| Una tipología rutea mal tras un cambio | benchmark del flujo o canario en rojo | dueño del flujo | revertir el commit del catálogo o prompt (está versionado) y recorrer el benchmark |
| Un flujo con acción financiera se comporta mal | golden paths, hallazgo alto | líder técnico | cerrar el portón del flujo (`TRX_FLOW_ENABLED=false` deja TXNR en formulario PQR sin desplegar) o suspender la opción en el catálogo; los casos van al proceso tradicional (formulario PQR y línea de atención) |
| Fuga de datos en trazas | barrido `scan_sensitive_traces.py` con hallazgos | líder técnico | apagar el volcado E2E, depurar objetos, rotar credenciales |
| Retorno | corrida completa en verde con la ficha de versión | líder técnico | reabrir el portón o la opción del catálogo |

La derivación al proceso tradicional no requiere despliegue: el formulario PQR es el último
recurso de todo flujo y la línea de atención aparece en cada cierre.

## 6. Monitoreo y revisión periódica

| Reloj | Cadencia | Indicador | Umbral | Responsable de revisar |
|---|---|---|---|---|
| Canario | cada 30 min en horario hábil | `precision_pct`, rutas caídas | 90 % provisional, 2 corridas seguidas | LLMOps (alerta por correo) |
| Benchmark completo | 03:00 diario y a demanda antes de desplegar | precisión por flujo, fallos por tipología, p95 | plan de pruebas §3 | LLMOps |
| Adversarial y grounding | con cada cambio de catálogo, prompt, guardrail o modelo | `fallos_leak`, `fallos_step`, `fallos_invented` | 0 | LLMOps |
| Tráfico real | continuo | desenlaces, latencia, topes alcanzados | tableros `pqr-metrics-*` | dueño del flujo, semanal |
| Trazas | con cada despliegue | barrido de datos sensibles | 0 hallazgos | LLMOps |

Revisión semanal de LLMOps: hallazgos abiertos, corridas de la semana, umbrales provisionales
pendientes de aprobación. Hoy el canario y el benchmark diario están suspendidos en el IaC a la
espera de la aprobación de costo; encenderlos cierra IT 2.7 con lo ya construido.
