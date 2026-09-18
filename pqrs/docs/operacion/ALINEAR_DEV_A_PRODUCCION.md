# Alinear una rama de producción con una rama de desarrollo

Procedimiento reutilizable. Está escrito para aplicarse en **cualquier repositorio**
con el patrón «una rama por ambiente», no solo en `agentepqr`.

El objetivo es doble y las dos mitades tiran en direcciones opuestas:

- el **código** de los módulos desplegables debe quedar idéntico al de desarrollo;
- la **configuración** de producción (endpoints, namespaces, imágenes, credenciales,
  límites) debe sobrevivir intacta.

Casi todos los incidentes de este tipo de alineación vienen de tratar la segunda
mitad como si fuera la primera.

---

## Nomenclatura

| Símbolo | Significado | Ejemplo en este repositorio |
|---|---|---|
| `$DEV` | rama de desarrollo, la que aporta el código | `feature/PQRSdev` |
| `$PRD` | rama de producción, la que recibe | `feature/HiddenLeague` |
| `$NS_DEV` / `$NS_PRD` | namespaces | `pqr-genai-dev` / `pqr-genai` |

---

## Paso 0. Proteger el trabajo en curso

**Nunca cambies de rama sin comprobar el árbol.** Ya se perdió trabajo así una vez.

```bash
git rev-parse --abbrev-ref HEAD
git status --porcelain | wc -l        # tiene que dar 0
git stash list                        # por si hay algo aparcado
```

Si hay cambios sin confirmar, **para** y resuélvelo antes de seguir: commit,
stash con nombre descriptivo, o rama de respaldo. No hay atajo seguro aquí.

---

## Paso 1. Inventariar y clasificar

```bash
git diff --name-status $PRD $DEV | cut -f1 | sort | uniq -c   # A / M / D
git diff --name-only  $PRD $DEV | sed 's|/.*||' | sort | uniq -c | sort -rn
```

Cada módulo cae en una de tres cajas. La clasificación es la decisión más
importante del proceso.

### Caja 1 · Alinear

Módulos de código que producción despliega. Se copian enteros hasta `diff` cero.

### Caja 2 · Excluir

Todo lo que existe solo para desarrollar o probar:

- simuladores de servicios externos;
- módulos de benchmark o carga;
- frontales de prueba;
- CI (`.github`), scripts de desarrollo;
- jobs destructivos (borrado de índices, wipes) aunque no estén registrados.

**Criterio para decidir si un módulo es de producción:** no mires su nombre, mira
si el IaC de `$PRD` lo despliega.

```bash
git show $PRD:IaC/kustomization.yaml
git show $PRD:IaC/backend/kustomization.yaml
```

Si no aparece en ninguna kustomization de `$PRD`, no se trae. Un frontal de
pruebas con Route pública y sin autenticación en producción es una regresión de
seguridad, no una alineación.

### Caja 3 · IaC

Tratamiento especial, pasos 3 a 6. **Nunca** se copia en bloque.

---

## Paso 2. Alinear el código

Antes de copiar, comprueba que el código de `$DEV` no arrastra referencias a
infraestructura de desarrollo:

```bash
git diff $PRD $DEV -- $MODULO | grep "^+" \
  | grep -iE "simulator|localhost|127\.0\.0\.1|-dev|\.dev\."
```

Si los aciertos están solo en `.md` / `.docx`, es documentación y no afecta al
artefacto. Confírmalo mirando qué copia la imagen:

```bash
grep -E "^COPY|^ADD" $MODULO/Containerfile   # o Dockerfile
```

Después, copia y **verifica que el diff es cero**:

```bash
for m in $MODULOS_A_ALINEAR; do git checkout $DEV -- "$m"; done

for m in $MODULOS_A_ALINEAR; do
  printf "%-36s %s\n" "$m" "$(git diff $DEV --name-only -- "$m" | wc -l)"
done   # todas las filas deben terminar en 0
```

`git checkout` **no borra** ficheros que existen en `$PRD` y no en `$DEV`.
Compruébalo aparte:

```bash
git diff --name-status $PRD $DEV -- $MODULO | grep "^D"
```

### Limpiar restos de otras ramas

Los directorios ignorados sobreviven al cambio de rama y ensucian las pruebas
locales:

```bash
find $MODULO/src -type d -name __pycache__ -exec rm -rf {} +
git status --porcelain --ignored $MODULO | grep -E "^(\?\?|!!)"
```

---

## Paso 3. Comparar el IaC **por valores**, nunca por nombres

Esta es la trampa principal, y me costó un error real: comparé los **nombres** de
las variables, vi que coincidían, y se me escapó que `TRX_PRODUCTS_SOURCE` valía
`postgres` en producción y `fo` en desarrollo. Dos ambientes leyendo de fuentes
distintas con la misma lista de variables.

Segundo detalle que rompe los extractores ingenuos: los ConfigMap suelen guardar
la configuración como un bloque `.env`, o sea `CLAVE=valor` indentado, **no**
`CLAVE: valor` de YAML:

```yaml
data:
  .env: |
    BOT_NAME=blue
    OPENSEARCH_ENDPOINT=https://opensearch.pqr-genai.svc.cluster.local:9200
```

Un extractor que solo entienda `CLAVE:` encontrará una fracción de las variables
y dará una falsa sensación de limpieza. Hay que cubrir **los dos formatos**:

```python
import re, subprocess
from collections import defaultdict

EXCLUIDOS = ("simulator", "benchmark", "front_test", "frontend")

def variables(rama):
    ficheros = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", rama, "--", "IaC"],
        capture_output=True, text=True).stdout.split()
    datos = defaultdict(dict)
    for f in ficheros:
        if not f.endswith((".yaml", ".yml")): continue
        if any(x in f for x in EXCLUIDOS): continue
        txt = subprocess.run(["git", "show", f"{rama}:{f}"],
                             capture_output=True, text=True).stdout
        for linea in txt.split("\n"):
            s = linea.strip()
            if not s or s.startswith("#"): continue
            m = (re.match(r'^([A-Z][A-Z0-9_]{2,})=(.*)$', s)        # bloque .env
                 or re.match(r'^([A-Z][A-Z0-9_]{2,}):\s+(\S.*)$', s))  # YAML plano
            if m:
                datos[m.group(1)][f] = m.group(2).strip().strip('"\'')
    return datos

prd, dev = variables("$PRD"), variables("$DEV")
for k in sorted(set(prd) & set(dev)):
    if set(prd[k].values()) != set(dev[k].values()):
        print(k, sorted(set(prd[k].values())), "|", sorted(set(dev[k].values())))
print("nuevas en dev:", sorted(set(dev) - set(prd)))
print("solo en prod :", sorted(set(prd) - set(dev)))
```

Guarda **qué fichero** aporta cada valor. Una misma variable puede aparecer en
varios ConfigMap con valores distintos, y eso a veces es el hallazgo.

### Cuidado con los alias

Varios nombres pueden alimentar el mismo ajuste. Compruébalo en el código antes
de decidir:

```bash
grep -rn "getenv(\"VARIABLE\"" src/
```

Si `_resolve_x()` lee `A or B or C`, cambiar `A` altera el comportamiento aunque
`B` y `C` no se toquen. En este repositorio `ASO_BASE_URL` **gana siempre** sobre
`ASO_SOURCE` + `ASO_REAL_URL`; quitarla «porque desarrollo no la tiene» dejaría la
resolución a merced de `ASO_SOURCE`, y si ese valor no fuera `real` caería al
default del **simulador**, que apunta al namespace de desarrollo.

---

## Paso 4. Incorporar las variables nuevas

Para cada variable presente en `$DEV` y ausente en `$PRD`, decide una de tres:

| Situación | Qué hacer |
|---|---|
| Ajuste funcional neutro (timeouts, tamaños, banderas) | copiar el valor |
| Apunta a infraestructura de desarrollo | **no copiar el valor**; dejarla comentada con el motivo, o poner el equivalente de producción |
| Pertenece a un módulo excluido | no traerla |

Cuando no copies un valor, **deja el rastro por escrito** en el propio fichero:
un nombre de variable sin explicación acaba «arreglado» por quien pase después.

```yaml
# Host dedicado del reto. En dev apunta al ASO de dev (aso-dev-co.work-02...),
# así que NO se copia aquí. Vacío hace que _challenge_base() caiga a
# ASO_BASE_URL, que en producción ya es el host live.
# ASO_CHALLENGE_BASE_URL=
```

Antes de dejar una variable vacía, **lee el fallback en el código** y confirma que
el comportamiento resultante es el que hay hoy en producción.

---

## Paso 5. Preservar producción

Nunca se alinean:

- **Imágenes**: registro, organización y etiqueta. Producción suele tener su
  propia línea de release. Copiar las de desarrollo hace que producción tire de
  artefactos de desarrollo, o de un registro al que no tiene acceso.
- **Hosts y URLs**: pasarelas, bases de datos, colas, buscadores, proveedores de
  modelo, callbacks entre servicios.
- **Namespaces** en cualquier forma: `*.svc.cluster.local`, Routes, hosts.
- **Credenciales**.
- **Límites de abuso**: en desarrollo se suben para poder probar. Alinearlos deja
  producción sin control de abuso.
- **Banderas de negocio** apagadas a propósito en producción.
- **RBAC, ServiceAccounts y SecurityContext**.

Verificación de imágenes y de RBAC:

```bash
for r in $PRD $DEV; do
  echo "── $r"
  git ls-tree -r --name-only $r -- IaC | grep -E '\.ya?ml$' \
    | xargs -I{} git show $r:{} 2>/dev/null | grep -E "^\s*image:" | sort -u
done

git show $PRD:IaC/<componente>/kustomization.yaml
git show $PRD:IaC/<componente>/02-statefulset.yaml | grep -E "serviceAccountName|runAsUser"
```

Si un StatefulSet de producción declara `serviceAccountName` y la rama de
desarrollo borró esa ServiceAccount, **no la borres**: el pod se queda sin poder
arrancar. Que desarrollo funcione sin ella solo significa que su namespace
concede los permisos de otra manera.

---

## Paso 6. Diferencias que no se deciden solas

Hay diferencias que no son técnicas. Nunca las cambies en silencio: documéntalas
y devuélvelas a quien tenga la autoridad para decidir.

- **Códigos de operación de terceros** (identificadores de contrato con un ASO,
  códigos de canal). Aunque el valor de producción parezca el default antiguo,
  cambiarlo sin confirmación es tocar un contrato externo.
- **Parámetros de negocio visibles para el cliente** (plazos, importes). Aquí
  apareció un caso que merece señalarse: el **mismo** parámetro con **dos**
  valores en el **mismo** ambiente, en dos módulos distintos. Eso no es una
  diferencia entre ramas, es una incoherencia interna de producción.

Búsqueda del patrón:

```bash
python3 - <<'PY'
# reutiliza variables() del paso 3 y lista las claves con >1 valor distinto
# dentro de la MISMA rama
for k, porf in variables("$PRD").items():
    if len(set(porf.values())) > 1:
        print(k, porf)
PY
```

---

## Paso 7. Verificar

Renderizado y ausencia de fugas:

```bash
kubectl kustomize IaC > /tmp/render.yaml
grep -E "^\s+namespace:" /tmp/render.yaml | sort -u        # solo $NS_PRD
grep -icE "$NS_DEV|simulator|benchmark|front-test" /tmp/render.yaml   # 0
```

### Trampa de kustomize: el namespace del padre gana

Verificado empíricamente: si una kustomization padre declara `namespace:`, **sobre­escribe**
el de las hijas. Un componente con su propio namespace, incluido desde el padre,
acaba desplegado en el del padre. Si necesitas un namespace distinto, ese
componente **no puede** colgar de la kustomization principal: se aplica aparte.

### Tests: comparar contra la rama de origen, no contra tu memoria

Un fallo tras alinear no significa que hayas roto algo. Reprodúcelo en la rama de
origen antes de investigar:

```bash
git worktree add --detach /tmp/wt_dev $DEV
cd /tmp/wt_dev/$MODULO && <comando de tests>
git worktree remove --force /tmp/wt_dev
```

Si el fallo es idéntico, es preexistente. Si difiere, sospecha del **entorno**
antes que del código: en este repositorio dos diferencias se explicaron por un
`.env` local ausente en el worktree y por `pytest` instalado en un `.venv` y no en
el otro. Ninguna era del código.

Nota práctica: los extras del `pyproject.toml` también son configuración por rama.
Un comando de test válido en una rama puede fallar en otra por un extra que no
existe allí.

---

## Lista de verificación

```
[ ] Árbol limpio antes de empezar; stashes revisados
[ ] Módulos clasificados según lo que despliega el IaC de producción, no por nombre
[ ] Código con diff cero contra $DEV en los módulos alineados
[ ] Borrados de $DEV comprobados aparte (git checkout no los aplica)
[ ] Restos ignorados de otras ramas limpiados
[ ] IaC comparado por VALORES, cubriendo bloques .env y YAML plano
[ ] Alias de variables verificados en el código
[ ] Variables nuevas decididas una por una, con el motivo escrito en el fichero
[ ] Imágenes, hosts, namespaces, credenciales y RBAC de producción intactos
[ ] Límites de abuso y banderas de negocio de producción intactos
[ ] kubectl kustomize renderiza; un solo namespace; cero fugas de desarrollo
[ ] Tests comparados contra un worktree de $DEV
[ ] Diferencias de negocio documentadas y devueltas a quien decide
[ ] Sin commit ni push: los hace la persona responsable del repositorio
```

---

## Los tres errores que más cuestan

1. **Comparar nombres en lugar de valores.** Da una falsa sensación de haber
   terminado. Compara siempre valores, y guarda de qué fichero sale cada uno.
2. **Concluir por estructura en lugar de medir.** «El padre no debería sobre­escribir
   el namespace», «este fallo lo he causado yo». Renderiza, ejecuta, reproduce en un
   worktree. La medición cambia la conclusión más veces de lo que parece.
3. **Copiar en bloque el IaC.** El código quiere ser idéntico; la configuración
   quiere ser distinta. Son operaciones opuestas y se hacen por separado.
