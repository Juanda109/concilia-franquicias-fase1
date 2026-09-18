# Motor de Workflows

Esta carpeta contiene el motor de arbol de decisiones que guia las conversaciones del asistente.

## Que vive aqui

- `general.yml`
  Define el saludo inicial, los grupos de `general_workflow` y los workflows disponibles dentro de cada grupo.
- `guia_rapida/`
  Guarda un archivo `.yml` por cada workflow de guia rapida.
- `hazlo_tu_mismo/`
  Guarda un archivo `.yml` por cada workflow de autoservicio.
- `models.py`
  Contiene los esquemas Pydantic usados para validar el catalogo y cada paso del flujo.
- `workflow_engine.py`
  Carga los YAML, interpreta la entrada del usuario, mueve la conversacion al siguiente paso y renderiza la respuesta del asistente.

## Idea principal

Los archivos YAML definen la estructura del flujo.

El motor decide:

- que workflow fue seleccionado
- cual es el paso actual
- que opcion coincide con la respuesta del usuario
- que `next_step` debe usarse

La capa de aplicacion puede complementar el YAML con logica dinamica por medio de `action`, pero la navegacion sigue tomando el YAML como fuente de verdad.

## Estructura de un workflow

Cada archivo de workflow sigue esta forma:

```yaml
version: 1
start_step: "1"
steps:
  "1":
    question: "Que necesitas?"
    input_type: "choice"
    save_as: "request_type"
    options:
      - key: "consulta"
        label: "Consulta"
        next_step: "1.1"
      - key: "estado"
        label: "Estado"
        next_step: "1.2"
```

Campos importantes:

- `question`
  Texto base que envia el asistente.
- `input_type`
  Define como debe comportarse el paso.
- `save_as`
  Clave usada para guardar la respuesta del usuario en `conversation.flow_answers`.
- `options`
  Opciones disponibles para los pasos de tipo `choice`.
- `next_step`
  Siguiente paso por defecto en pasos `text` o pasos sin ramificacion por opciones.
- `action`
  Accion tecnica opcional que se ejecuta cuando el paso lo requiere.
- `terminal`
  Marca que el paso cierra el flujo.

## Como decide el motor el siguiente paso

La logica principal vive en `workflow_engine.py`.

### 1. El motor carga el catalogo

Cuando se crea `WorkflowEngine()`:

- lee `general.yml`
- valida ese archivo con `WorkflowGeneralCatalog`
- resuelve la ruta de cada workflow
- valida cada workflow con `WorkflowDefinition`

Eso ocurre en `WorkflowEngine._load_catalog()`.

### 2. La conversacion selecciona grupo y workflow

Antes de que exista un workflow concreto:

- el usuario primero selecciona un `general_workflow`
- luego selecciona un `workflow` especifico

Ejemplos:

- `Guia rapida` es el `general_workflow`
- `cuenta_embargada` es el `workflow`

Eso se resuelve en:

- `WorkflowEngine._handle_general_workflow_selection()`
- `WorkflowEngine._handle_specific_workflow_selection()`

Una vez elegido el workflow, el motor asigna:

- `conversation.workflow`
- `conversation.flow_version`
- `conversation.current_step = start_step`

### 3. El motor lee el paso actual

Cuando ya existe un workflow activo, el motor hace algo como:

```python
current_step = workflow_definition.steps[conversation.current_step]
```

Y despues decide el comportamiento segun `input_type`.

### 4. Pasos `choice`

En los pasos `choice`, el motor compara la entrada del usuario contra las opciones del paso.

La comparacion acepta:

- la posicion numerica: `1`, `2`, `3`
- el `key` de la opcion
- el `label` de la opcion

Eso ocurre en `WorkflowEngine._match_step_option()`.

Si el usuario selecciona una opcion valida:

1. el motor guarda el `key` de la opcion en `conversation.flow_answers`
2. lee el `next_step` configurado para esa opcion
3. mueve la conversacion a ese paso

Ejemplo:

```yaml
"1.4.1.1":
  question: "Selecciona el producto que deseas consultar."
  input_type: "choice"
  save_as: "producto_centrales_de_riesgo"
  options:
    - key: "producto_1"
      label: "Producto 1"
      next_step: "1.4.1.1.1"
    - key: "producto_2"
      label: "Producto 2"
      next_step: "9"
```

Si el usuario responde `1`, el motor guarda:

```python
conversation.flow_answers["producto_centrales_de_riesgo"] = "producto_1"
```

Y luego avanza al paso `1.4.1.1.1`.

### 5. Pasos `text`

En los pasos `text`, el motor:

1. guarda el texto del usuario en `save_as`
2. usa el `next_step` definido a nivel del paso

Ejemplo:

```yaml
"1":
  question: "Describe tu solicitud."
  input_type: "text"
  save_as: "detalle"
  next_step: "2"
```

### 6. Pasos `terminal`

Si un paso tiene `terminal: true` o `input_type: "terminal"`:

- la conversacion pasa a `Closed`
- el texto del paso se usa como respuesta del asistente

No se espera mas entrada del usuario dentro de ese workflow.

## Como funcionan las acciones

Las acciones son el puente entre el YAML estatico y la logica dinamica del negocio.

El motor por si solo no ejecuta acciones.

La secuencia real es:

1. `WorkflowEngine.generate_response()` mueve la conversacion al siguiente paso usando solo YAML.
2. La capa de aplicacion revisa el nuevo paso actual.
3. Si ese paso tiene `action`, la aplicacion ejecuta la accion.
4. La accion enriquece `conversation.captured_data`.
5. El motor vuelve a renderizar el paso, ahora con datos dinamicos si existen.

Esta orquestacion ocurre en:

- `src/application/chat/chat_service.py`
- `src/application/chat/workflow_actions.py`

### Regla importante

Una accion normalmente no decide el siguiente paso.

La accion suele:

- cargar datos de negocio
- construir un prompt dinamico
- guardar contexto tecnico
- preparar informacion para el cierre del LLM

Pero el cambio de paso sigue viniendo del YAML y de `next_step`.

## Como un prompt dinamico reemplaza el texto del YAML

El motor soporta reemplazar la pregunta por defecto de un paso con un prompt generado en runtime.

Busca esta clave:

```python
conversation.captured_data[f"dynamic_prompt_{step_id}"]
```

Si existe, el motor usa ese texto en lugar de `step.question`.

Eso pasa en `WorkflowEngine._render_step_prompt()`.

Asi un paso puede estar definido con una pregunta generica en el YAML, pero la aplicacion puede reemplazarla con informacion especifica del usuario.

## Ejemplo del paso de productos

El mejor ejemplo es `guia_rapida/cuenta_embargada.yml`.

### Definicion en YAML

El paso de productos esta definido asi:

```yaml
"1.4.1.1":
  question: "Selecciona el producto que deseas consultar."
  action: "consultar_productos_cliente"
  input_type: "choice"
  save_as: "producto_centrales_de_riesgo"
  options:
    - key: "producto_1"
      label: "Producto 1"
      next_step: "1.4.1.1.1"
    - key: "producto_2"
      label: "Producto 2"
      next_step: "1.4.1.1.1"
    - key: "producto_3"
      label: "Producto 3"
      next_step: "1.4.1.1.1"
```

A simple vista, el YAML solo conoce `producto_1`, `producto_2` y `producto_3`.

### Que hace la accion

La accion `consultar_productos_cliente` esta implementada en:

- `src/application/chat/workflow_actions.py`

Esa funcion:

1. lee el archivo `guia_rapida/Muestra_tabla_embargos.csv`
2. filtra los registros segun `conversation.user_id`
3. transforma cada fila en un producto runtime compatible con el flujo
4. construye un prompt dinamico con nombres reales y ids enmascarados
5. guarda ese prompt en:

```python
conversation.captured_data["dynamic_prompt_1.4.1.1"]
```

Por eso el usuario ve algo como:

```text
Selecciona el producto que deseas consultar

1. Cuenta de Ahorros
   **** 2312
2. Tarjeta de Credito
   **** 2345
3. Credito
   **** 8900
4. Ver todos los productos
```

### Como se sigue determinando el siguiente paso

Aunque el usuario vea productos reales, el motor sigue resolviendo la respuesta contra las opciones del YAML:

- `1` significa la primera opcion
- la primera opcion del YAML es `producto_1`
- `producto_1` tiene `next_step: "1.4.1.1.1"`

Asi que la navegacion sigue viniendo del YAML.

La accion solo cambia el mensaje visible.

### Como despues se recupera el producto real

Mas adelante, cuando el flujo necesita el producto real, el codigo lee:

```python
conversation.flow_answers["producto_centrales_de_riesgo"]
```

Eso contiene `producto_1`, `producto_2`, etc.

Luego `_resolve_selected_product()` convierte ese valor simbolico al objeto real cargado desde el CSV.

Por eso este flujo usa dos capas:

- capa YAML: opciones simbolicas y navegacion
- capa runtime: datos reales del negocio

## Como funciona una accion en un paso terminal

En el mismo flujo existe otro patron:

```yaml
"1.4.1.1.1.1":
  question: "Consultando el estado de tu cuenta en centrales de riesgo."
  action: "consultar_centrales_producto_seleccionado"
  input_type: "terminal"
  terminal: true
```

Eso significa:

1. el YAML cierra el flujo en ese paso
2. la aplicacion aun ejecuta la accion
3. la accion prepara contexto tecnico y un mensaje base
4. el LLM puede construir la respuesta final al usuario con ese contexto

O sea, el paso es terminal desde el punto de vista del arbol, pero aun permite procesamiento posterior.

## Datos de conversacion que usa el motor

El motor y las acciones trabajan principalmente con estos campos:

- `conversation.current_step`
  Paso actual, por ejemplo `1.4.1.1`
- `conversation.flow_answers`
  Guarda respuestas normalizadas del usuario usando la clave de `save_as`
- `conversation.captured_data`
  Guarda contexto tecnico, prompts dinamicos, datos resueltos del negocio e instrucciones para el cierre
- `conversation.status`
  Indica si la conversacion esta `Active` o `Closed`

## Modelo mental practico

La regla mas util es esta:

- el YAML decide la ruta
- las acciones enriquecen el paso
- el motor vuelve al YAML despues de ejecutar la accion

Mas concretamente:

1. El YAML define que paso existe.
2. El YAML define como se compara la respuesta.
3. El YAML define que `next_step` sigue.
4. La accion define que datos adicionales deben cargarse.
5. El prompt dinamico puede reemplazar el texto mostrado.
6. La navegacion continua sobre la estructura original del YAML.

## Cuando usar solo YAML

Usa solo YAML cuando:

- el mensaje es estatico
- las opciones son fijas
- el siguiente paso depende unicamente de la opcion elegida

## Cuando usar `action`

Usa `action` cuando:

- el mensaje depende de datos del usuario
- se deben consultar productos, cuentas o referencias
- hay que guardar contexto tecnico antes del cierre
- el paso debe preparar datos para una respuesta generada por el LLM

## Tips de depuracion

Si un paso no se comporta como esperas, revisa en este orden:

1. Existe el paso en el YAML y `current_step` apunta a el?
2. El paso define bien sus `options` o su `next_step`?
3. El paso define `save_as` si la respuesta debe persistirse?
4. El paso define `action` solo cuando realmente hay comportamiento dinamico?
5. La accion guardo `dynamic_prompt_<step_id>` en `captured_data`?
6. La opcion seleccionada si mapea al `next_step` esperado?

## Resumen

El motor de workflows es deterministico.

Siempre avanza usando la definicion del YAML.

Las acciones no reemplazan el arbol del flujo. Lo enriquecen con datos en runtime y luego el sistema vuelve al mismo ciclo:

- resolver el paso
- comparar la entrada
- mover al `next_step`
- ejecutar la accion opcional
- renderizar la respuesta final del paso actual

Por eso un paso como seleccion de productos puede mostrar productos reales traidos por codigo, mientras sigue navegando por opciones simbolicas definidas en el YAML.
