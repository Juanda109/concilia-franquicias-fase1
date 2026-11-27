# Migración a PVCs más pequeños y CPU reservada de 200m

Cambio pedido por arquitectura: bajar la CPU reservada (requests) de MinIO y
PostgreSQL a 200m y reducir los PVCs, que estaban casi vacíos.

| Recurso | Antes | Después |
|---|---|---|
| CPU request `statefulset/minio` | 500m (limit 1500m) | **200m** (limit sin cambio) |
| CPU request `statefulset/postgresql` | 500m (limit 2) | **200m** (limit sin cambio) |
| PVC PostgreSQL | `postgresql-data` 10Gi (ceph-rbd) | **`postgresql-data-v2` 5Gi** |
| PVC MinIO | `minio-data-pvc` 50Gi (cephfs-sc) | **`minio-data-v2` 10Gi** |

## Por qué los PVCs cambian de nombre

Kubernetes **no permite reducir** un PVC: `oc apply` con un tamaño menor falla
con `field can not be less than previous value`. Por eso se crean PVCs nuevos
(`-v2`), se copian los datos y los StatefulSets pasan a usar los nuevos. Los
viejos no se borran hasta validar, y sirven de rollback.

> ⚠️ **No correr `oc apply -k IaC` antes del paso 4.** Si se aplica primero,
> los StatefulSets arrancan sobre los PVCs nuevos vacíos: PostgreSQL crearía
> una base nueva sin datos y MinIO un bucket vacío.

Crecer después sí es fácil y en caliente (solo se sube el número en
`01-pvc.yaml`), siempre que la storage class lo permita:

```bash
oc get sc ceph-rbd cephfs-sc -o custom-columns=NAME:.metadata.name,EXPANSION:.allowVolumeExpansion
```

## Paso 0: respaldo y estado actual

```bash
oc get pvc                       # anotar nombre, tamaño y estado de cada uno
oc describe pvc | grep -E "^Name:|^Used By:"

# Respaldo lógico de la base, a tu máquina (no sube a ningún lado):
oc exec statefulset/postgresql -- bash -c \
  'pg_dump -U "$POSTGRESQL_USER" -d "$POSTGRESQL_DATABASE" -Fc' > concilia_antes_migracion.dump
```

**El PVC de 10G vacío** no está definido en este repo (`IaC/` solo declara
los dos de arriba). Si `oc describe pvc <nombre>` muestra `Used By: <none>` y
no aparece en ningún YAML de `IaC/`, es un sobrante de un despliegue anterior:

```bash
oc delete pvc <nombre-del-pvc-vacio>
```

## Paso 1: detener la aplicación

```bash
oc scale deployment/co-backend-concilia deployment/co-api-parseo --replicas=0
oc scale statefulset/postgresql statefulset/minio --replicas=0
oc get pods -w        # esperar a que no quede ningún pod de postgresql/minio
```

## Paso 2: crear solo los PVCs nuevos

```bash
oc apply -f IaC/BD/postgresql/01-pvc.yaml -f IaC/bucket/01-pvc.yaml
oc get pvc postgresql-data-v2 minio-data-v2
```

(Si la storage class usa `WaitForFirstConsumer`, quedan en `Pending` hasta
el paso 3. Es normal.)

## Paso 3: copiar los datos

```bash
oc apply -f IaC/migracion-pvc/copiar-postgresql.yaml
oc logs -f pod/copiar-pvc-postgresql      # debe terminar en "COPIA OK"

oc apply -f IaC/migracion-pvc/copiar-minio.yaml
oc logs -f pod/copiar-pvc-minio           # debe terminar en "COPIA OK"
```

Comparar en el log la cantidad de archivos de origen y destino (deben ser
iguales). Luego:

```bash
oc delete pod copiar-pvc-postgresql copiar-pvc-minio
```

Si un pod de copia falla por permisos, revisar que corra con el mismo UID que
el StatefulSet (`oc get pod <pod> -o jsonpath='{.spec.securityContext}'`). En
la SCC `restricted-v2` todos los pods del namespace reciben el mismo UID por
defecto.

## Paso 4: aplicar el IaC

```bash
oc apply -k IaC
oc scale statefulset/postgresql statefulset/minio --replicas=1
oc scale deployment/co-backend-concilia deployment/co-api-parseo --replicas=1   # o las réplicas que tenían
```

`oc apply -k` deja los StatefulSets en 1 réplica, pero el `scale` se deja
explícito por si alguien aplica por partes.

## Paso 5: validar

- `oc get pods`: postgresql, minio, backend y parseo en `Running` y `Ready`.
- `oc describe statefulset/postgresql | grep -A2 Requests` muestra `cpu: 200m`.
- En la aplicación: las jornadas y archivos que ya existían siguen apareciendo,
  y un archivo cargado antes se puede descargar (eso prueba MinIO).
- Cargar un archivo nuevo y confirmar que se procesa.

## Paso 6: borrar los PVCs viejos (después de unos días de validación)

```bash
oc delete pvc postgresql-data minio-data-pvc
```

## Rollback (mientras no se haya hecho el paso 6)

```bash
oc scale deployment/co-backend-concilia deployment/co-api-parseo --replicas=0
oc scale statefulset/postgresql statefulset/minio --replicas=0
# volver claimName a postgresql-data / minio-data-pvc en los 02-deployment.yaml
oc apply -k IaC
```

Si algo se perdió en PostgreSQL, el respaldo del paso 0 se restaura con
`pg_restore -U "$POSTGRESQL_USER" -d "$POSTGRESQL_DATABASE" --clean`.
