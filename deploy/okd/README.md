# Despliegue en OKD

Esta carpeta es exclusiva para el clúster OKD (dev/QA/prod). Para pruebas
locales se sigue usando `docker-compose.yml` en la raíz del repo — no tiene
relación con lo de aquí.

## Estado

Estructura lista (`kustomization.yaml`, `Deployment`, `Service`, `Route`,
`ConfigMap`, plantilla de `Secret`), pero **sin namespace ni registry de
imagen asignados todavía por la plataforma**. Hasta tenerlos, todo lo que
depende de esos datos queda como variable `${VAR}` sin resolver.

## Variables pendientes de resolver

| Variable | Dónde se usa | Valor hoy |
|---|---|---|
| `OKD_NAMESPACE` | `kustomization.yaml` (namespace de todos los recursos) | Pendiente — lo asigna la plataforma |
| `OKD_ROUTE_HOST` | `route.yaml` | Pendiente — depende del dominio de apps del clúster |
| `IMAGE_CONCILIA_BACKEND` | `backend.yaml` | Pendiente — depende del registry (Quay/Artifactory interno) |
| `DATABASE_URL` | `secret-template.yaml` | Pendiente — Postgres real del ambiente, no el de `docker-compose` |
| `MINIO_ENDPOINT`, `MINIO_BUCKET` | `configmap.yaml` | No bloqueante: MinIO aún no está integrado en el código del backend |
| `SFTP_USERNAME`, `SFTP_PASSWORD` | `secret-template.yaml` | No bloqueante: la ingesta SFTP aún no está implementada en el código |

## Cómo se aplica (cuando haya namespace/registry)

```bash
# 1. Definir las variables del ambiente (dev/qa/prod), no versionarlas
export OKD_NAMESPACE=...
export OKD_ROUTE_HOST=...
export IMAGE_CONCILIA_BACKEND=...
export DATABASE_URL=...
export MINIO_ENDPOINT=...
export MINIO_BUCKET=...
export SFTP_USERNAME=...
export SFTP_PASSWORD=...

# 2. Construir con kustomize y resolver las variables con envsubst
kubectl kustomize deploy/okd | envsubst | oc apply -f -
```

## Verificación local (sin clúster)

`kubectl kustomize` valida que los manifiestos son válidos como YAML/kustomize,
sin necesitar un clúster real ni resolver las variables:

```bash
kubectl kustomize deploy/okd > /dev/null && echo OK
```
