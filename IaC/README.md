# Despliegue en OKD

Esta carpeta es exclusiva para el clúster OKD (dev/QA/prod). Para pruebas
locales se sigue usando `docker-compose.yml` en la raíz del repo — no tiene
relación con lo de aquí.

Estructura tomada como referencia del proyecto `pqrs` (BBVA): una carpeta
`IaC/` separada del código de cada servicio, organizada por categoría
(`BD`, `bucket`, `backend`), con un `kustomization.yaml` por categoría y
manifiestos de un solo recurso por archivo, numerados en orden de aplicación
(`00-secret`/`00-configmap` → `01-pvc` → `02-deployment` → `03-service` →
`04-route`).

## Componentes

Cada uno es un pod independiente con su propio Deployment/Service, y se
llaman entre sí por el nombre del Service (DNS interno del clúster):

| Componente | Carpeta | Expone | Lo llaman |
|---|---|---|---|
| **front** | `frontend/co-frontend-concilia/` | `co-frontend-concilia:8080` (Route pública) | Usuario final |
| **back** | `backend/co-backend-concilia/` | `co-backend-concilia:8080` (solo interno, sin Route) | front (vía nginx `/api/`, `/health`) |
| **api de parseo** | `backend/co-api-parseo/` | `co-api-parseo:8081` | back |
| **postgres** | `BD/postgresql/` | `co-db-concilia:5432` | back (lectura/jornadas) y parseo (escritura de resultados) |
| **minio** | `bucket/` | `co-bucket-concilia:9000` (API) / `:9001` (consola) | back (sube el archivo original) y parseo (lo descarga para parsear) |

`backend/00-configmap.yaml` y `backend/00-secret-template.yaml` son
compartidos por `co-backend-concilia` y `co-api-parseo` (mismo `DATABASE_URL`,
`MINIO_*` y `PARSEO_API_URL`), por eso quedan al nivel de la categoría y no
duplicados en cada subcarpeta de servicio.

Flujo real de una carga: front → back (recibe el archivo) → back sube a
**minio** → back llama a **parseo** (`POST /parse` con la referencia de MinIO)
→ parseo descarga de minio, parsea, e inserta en **postgres** → parseo
responde a back → back responde a front.

## Estado

Estructura lista (`kustomization.yaml` anidado por categoría,
Deployments/Services/Route de los componentes existentes, plantillas de
`Secret`), pero **sin namespace ni registry de imagen asignados todavía por
la plataforma**. Hasta tenerlos, todo lo que depende de esos datos queda
como variable `${VAR}` sin resolver.

`securityContext` en cada Deployment (`runAsNonRoot: true`, sin `runAsUser`
fijo, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`) sigue el
mismo patrón validado en `pqrs` para MinIO bajo la SCC `restricted` de OKD —
ya no es un riesgo sin confirmar, como se había dejado documentado
originalmente.

## Paso 0 — ConfigMap del DDL/seed de Postgres (fuera de kustomize)

`BD/postgresql/02-deployment.yaml` monta un ConfigMap
`concilia-postgres-initdb` con el DDL de las 21 tablas y el seed de los 12
insumos esperados. Kustomize no puede generarlo automáticamente porque
bloquea por seguridad referenciar archivos fuera de esta carpeta
(`../database/*.sql`), así que se crea aparte, **antes** de aplicar el resto:

```bash
oc create configmap concilia-postgres-initdb \
  --from-file=../database/00_concilia_fase1_ddl_21_tablas.sql \
  --from-file=../database/22_seed_insumos_esperados.sql
```

Si cambia el DDL, hay que recrear este ConfigMap (`oc create ... --dry-run=client -o yaml | oc apply -f -`)
y reiniciar el pod de postgres para que un volumen ya inicializado no lo ignore.

## Paso 0.5 — Ejecutar el DDL/seed a mano (verificado en clúster real)

El ConfigMap se monta en `/opt/app-root/src/postgresql-init` dentro del pod,
pero **la imagen `registry.redhat.io/rhel9/postgresql-15` no tiene ningún
hook que auto-ejecute ese contenido** al arrancar (a diferencia de la
imagen S2I `openshift/postgresql` que se intentó usar originalmente, pero
que no resulta alcanzable en este clúster — ver el comentario en
`BD/postgresql/02-deployment.yaml`). Confirmado en clúster: los `.sql`
llegan montados, pero la base de datos queda vacía tras el primer arranque.

Hay que correrlo a mano, **una vez**, después de que el pod de postgres
esté `Ready` (usa los archivos que ya están montados dentro del propio pod,
no hace falta copiar nada):

```bash
oc exec deploy/co-db-concilia -o jsonpath='{.metadata.namespace}' # confirma tu namespace si tienes dudas

oc exec deploy/co-db-concilia -- bash -c \
  'psql -U "$POSTGRESQL_USER" -d "$POSTGRESQL_DATABASE" -f /opt/app-root/src/postgresql-init/00_concilia_fase1_ddl_21_tablas.sql'
oc exec deploy/co-db-concilia -- bash -c \
  'psql -U "$POSTGRESQL_USER" -d "$POSTGRESQL_DATABASE" -f /opt/app-root/src/postgresql-init/22_seed_insumos_esperados.sql'

# Verificar (debe listar 21 tablas):
oc exec deploy/co-db-concilia -- bash -c 'psql -U "$POSTGRESQL_USER" -d "$POSTGRESQL_DATABASE" -c "\dt"'
```

Hay que repetir este paso cada vez que el PVC de postgres se borre/recree
desde cero (por ejemplo, si se reinicializa el ambiente).

## Variables pendientes de resolver

| Variable | Dónde se usa | Valor hoy |
|---|---|---|
| `OKD_NAMESPACE` | `kustomization.yaml` (namespace de todos los recursos) | Pendiente — lo asigna la plataforma |
| `IMAGE_CONCILIA_BACKEND` | `backend/co-backend-concilia/01-deployment.yaml` | Pendiente — registry Quay corporativo (`quay.apps.work.ocp.co.igrupobbva/<organización>`) |
| `IMAGE_CONCILIA_PARSEO` | `backend/co-api-parseo/01-deployment.yaml` | Pendiente — mismo registry que el backend |
| `IMAGE_CONCILIA_FRONTEND` | `frontend/co-frontend-concilia/01-deployment.yaml` | Pendiente — mismo registry que el backend |
| `DATABASE_URL` | `backend/00-secret-template.yaml` | Se construye con las credenciales de abajo: `postgresql://<POSTGRES_USER>:<POSTGRES_PASSWORD>@co-db-concilia:5432/<POSTGRES_DB>` |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | `BD/postgresql/00-secret-template.yaml` | Pendiente — definir credenciales del ambiente |
| `MINIO_ENDPOINT` | `backend/00-configmap.yaml` | `co-bucket-concilia:9000` si se usa el MinIO de este repo (`bucket/`); endpoint real si es un MinIO corporativo externo |
| `MINIO_BUCKET` | `backend/00-configmap.yaml` | Sugerido: `concilia-fase1` |
| `MINIO_SECURE` | `backend/00-configmap.yaml` | `"false"` en HTTP interno del clúster; `"true"` si el Service de MinIO exige TLS |
| `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` | `backend/00-secret-template.yaml` | Deben coincidir con `bucket/00-secret-template.yaml` (mismas credenciales, back/parseo como cliente) |
| `SFTP_USERNAME`, `SFTP_PASSWORD` | `backend/00-secret-template.yaml` | No bloqueante: la ingesta SFTP aún no está implementada en el código |

## Construir y publicar las imágenes

`co-backend-concilia/` y `co-api-parseo/` (carpetas de código fuente, en la raíz del repo) tienen **dos** Dockerfile:
- `Dockerfile`: el que usa `docker-compose.yml` para desarrollo local (imagen pública `python:3.12-slim`, sin credenciales).
- `Dockerfile.okd`: el que hay que usar para construir la imagen que se despliega en OKD (imagen base del Artifactory corporativo, usuario no root `www-data`). Requiere `ARTIFACTORY_USER`/`ARTIFACTORY_PASSWORD` — pendiente completar además la ruta exacta del índice PyPI interno (queda marcada con `<COMPLETAR_RUTA_PYPI>` en el Dockerfile).

```bash
podman login quay.apps.work.ocp.co.igrupobbva
podman build -f co-backend-concilia/Dockerfile.okd \
  --build-arg ARTIFACTORY_USER=... --build-arg ARTIFACTORY_PASSWORD=... \
  -t quay.apps.work.ocp.co.igrupobbva/concilia-genai/concilia-backend:v2 co-backend-concilia/
podman push quay.apps.work.ocp.co.igrupobbva/concilia-genai/concilia-backend:v2
# repetir con co-api-parseo/Dockerfile.okd para concilia-parseo
```

`co-frontend-concilia/` no tiene variante `.okd`: es nginx + estáticos, no depende de paquetes Python ni de Artifactory, así que su único `Dockerfile` sirve tanto para local como para OKD.

## Cómo se aplica (cuando haya namespace/registry)

```bash
# 1. Definir las variables del ambiente (dev/qa/prod), no versionarlas
export OKD_NAMESPACE=...
export IMAGE_CONCILIA_BACKEND=...
export IMAGE_CONCILIA_PARSEO=...
export IMAGE_CONCILIA_FRONTEND=...
export POSTGRES_USER=concilia
export POSTGRES_PASSWORD=...
export POSTGRES_DB=concilia
export DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@co-db-concilia:5432/${POSTGRES_DB}"
export MINIO_ENDPOINT=co-bucket-concilia:9000
export MINIO_BUCKET=concilia-fase1
export MINIO_SECURE=false
export MINIO_ACCESS_KEY=concilia
export MINIO_SECRET_KEY=...
export SFTP_USERNAME=...
export SFTP_PASSWORD=...

# 2. Crear el ConfigMap del DDL/seed (paso 0, no forma parte del kustomization)
oc create configmap concilia-postgres-initdb \
  --from-file=database/00_concilia_fase1_ddl_21_tablas.sql \
  --from-file=database/22_seed_insumos_esperados.sql

# 3. Construir con kustomize y resolver el resto de variables con envsubst
kubectl kustomize IaC | envsubst | oc apply -f -
```

## Verificación local (sin clúster)

`kubectl kustomize` valida que los manifiestos son válidos como YAML/kustomize,
sin necesitar un clúster real ni resolver las variables:

```bash
kubectl kustomize IaC > /dev/null && echo OK
```
