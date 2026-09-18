# Plan — revisar todos los casos y robustecer los documentos de prueba de UI

**Fecha:** 17/08/2026 · **Objetivo:** que puedas sentarte a probar en la UI sin fricción,
con documentos que digan **exactamente** qué teclear y qué debe aparecer, y que ningún
caso falle por el documento en vez de por el flujo.

---

## 1 · Estado real hoy (inventariado, no estimado)

| Documento | Tamaño | Para qué sirve | Fiabilidad |
|---|---|---|---|
| `PLAN_PRUEBAS_UI.md` | 673 líneas · **25 casos U** | tu guion de pasada manual | ⚠️ **pasos nunca ejecutados** |
| `PROTOCOLO_ESQUELETO.md` | 86 líneas · 17 casos E | resultados y hallazgos | ✅ ejecutado |
| `CASOS_PRUEBA_TRX_ESQUELETO.xlsx` | 51 filas | documento corporativo | ✅ 26 ejecutadas · 25 pendientes |
| `Merged_Flux.xlsx` | 77 casos | documento único con Luis | ✅ estructura, ⚠️ mis 25 U sin ejecutar |
| `BITACORA_F0.md` | 61 líneas | stack local | ✅ |

### Los tres problemas concretos que hay que resolver

1. **Los pasos de los 25 casos U los escribió un agente y nunca se ejecutaron.** Están
   razonados sobre el código, pero *"pulsar X"* puede no coincidir con la etiqueta real.
   Dos casos citan un *"pulsar Continuar"* que **ya no existe** desde la validación
   silenciosa. Si te sientas a probar con esto, perderás tiempo diagnosticando el
   documento en vez del flujo.
2. **Colisión de clientes**: `1013634960` aparece en **6 casos**, `1013634962` en 3, y
   hay una conversación por cliente y día. El documento no dice cuándo resetear, así que
   del caso 2 en adelante el bot retomaría y parecería un fallo.
3. **El "esperado" es descriptivo, no literal.** Dice *"muestra el copy de derivación"* en
   vez del texto exacto. Con copys que rotan (el feedback tiene 3 variantes), no puedes
   decidir si lo que ves está bien.

---

## 2 · Qué haremos, por fases

### F1 · Ejecutar los 25 casos U y corregir el documento (½ día) — el grueso

Recorrer **cada caso** contra el stack, por HTTP, y capturar lo que el bot responde de
verdad. Con eso se corrige el documento en tres sitios por caso:

- **Pasos** → la etiqueta literal del botón (o el texto exacto a teclear).
- **Esperado** → el **texto real** que aparece, recortado a lo identificable, en vez de
  una descripción.
- **Preparación** → el comando de reset exacto cuando el cliente ya se usó.

Los **7 casos [STACK]** (parar el simulador, back_trx caído, variables vacías) se ejecutan
también, uno a uno, restaurando el stack después de cada uno.

**Resultado:** cada caso del documento está *probado que se puede ejecutar*. Si luego
falla en tu pasada, el fallo es del flujo — que es lo que queremos medir.

**Y lo que aparezca en el camino es hallazgo**: la ejecución de estos 25 casos cubre ramas
que la suite no toca (por eso se diseñaron), así que espero encontrar defectos nuevos.

### F2 · Robustecer cada caso con lo que hoy falta (2 h)

Añadir a cada uno de los 25:

| Campo nuevo | Por qué |
|---|---|
| **Duración estimada** | para que puedas planificar la sesión y parar donde toque |
| **Texto literal esperado** | capturado en F1; lo que compares no admite interpretación |
| **Si falla, mira aquí** | el `grep` de logs concreto para ese caso |
| **Depende de / bloquea** | qué casos comparten cliente y en qué orden hacerlos |
| **Qué anotar** (ya existe) | se mantiene |

### F3 · Guía de sesión — el documento que abres primero (1 h)

Un `GUIA_SESION_PRUEBAS.md` corto que hoy no existe y es lo que más falta:

- **Arranque en 3 comandos** (levantar, comprobar salud, resetear todo).
- **Los 25 casos agrupados en 4 bloques de ~45 min**, cada bloque con clientes que no
  colisionan entre sí — para que puedas hacer un bloque y parar.
- **Mapa cliente → casos**, para saber cuándo resetear.
- **Qué hacer cuando algo falla**: los 3 comandos de diagnóstico y qué información
  copiarme para que yo lo analice.
- **Los 6 destinos esperados por cliente** en una tabla, para no dudar de si "sin
  productos" es un fallo.

### F4 · Sincronizar Excel y documento único (1 h)

- Las filas 200-225 del Excel se actualizan con los **pasos corregidos** y el **literal
  esperado** de F1.
- Igual en `Merged_Flux.xlsx`.
- Los hallazgos nuevos de F1 entran como filas propias y en el protocolo.

### F5 · Cierre y push (30 min)

Regresión de los tres verificadores, commit por fase y push al PR #75.

---

## 3 · Lo que NO vamos a hacer (y por qué)

- **No convertiré los 25 casos U en automáticos.** Su valor es justo lo que un script no
  ve: cómo se pinta, si un texto se corta, si la espera se hace larga. Los que sí merecen
  automatizarse (fronteras de vigencia, mensajes) ya lo están.
- **No tocaré el tramo de Luis.** Los casos que rozan la frontera se quedan verificando
  la entrega, como hasta ahora.
- **No fusionaré `PLAN_PRUEBAS_UI.md` con el protocolo.** Son cosas distintas: el
  protocolo registra lo ejecutado (con hallazgos), el plan es tu guion. Mezclarlos hace
  que ninguno sirva.

---

## 4 · Riesgos

| Riesgo | Mitigación |
|---|---|
| F1 descubre que muchos casos U no son ejecutables tal cual | es el objetivo; se corrigen y se anota cuántos hubo que tocar |
| Los casos [STACK] dejan el entorno inconsistente | cada uno restaura y se comprueba salud antes del siguiente |
| Un caso resulta no provocable por UI | se marca como tal en el documento y pasa a unitario, sin fingir que se puede |
| Las fechas de fixtures caducan a mitad | ya avisado; `06/08/2026` sigue vigente y el protocolo lo recuerda |

**Estimación total: ~1 jornada.** El grueso es F1, que es también lo que más valor te
ahorra después: cada caso que arreglo ahí es media hora que no pierdes tú.
