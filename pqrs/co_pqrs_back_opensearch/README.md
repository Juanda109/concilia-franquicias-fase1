# Levantar OpenSearch con Podman

Este repositorio define un ambiente local con:

- `opensearch-node1`
- `opensearch-node2`
- `opensearch-dashboards`

La orquestacion esta en [`docker-compose.yml`](./docker-compose.yml), pero puede ejecutarse con Podman usando `podman compose`.

## Requisitos

- Podman instalado.
- PowerShell.
- Podman Machine inicializada y encendida si estas en Windows.
- Al menos 6 GB de RAM disponibles para la maquina de Podman.

## 1. Preparar la maquina de Podman

Si es la primera vez que usas Podman en Windows, crea la maquina una sola vez:

```powershell
podman machine init --cpus 4 --memory 8192 --disk-size 30
```

Luego enciendela:

```powershell
podman machine start
```

## 2. Ajustar `vm.max_map_count`

OpenSearch necesita este valor dentro de la maquina Linux de Podman:

```powershell
podman machine ssh "sudo sysctl -w vm.max_map_count=262144"
```

Si reinicias la maquina de Podman, puede que debas ejecutar este comando otra vez.

## 3. Configurar la contrasena de administrador

Edita el archivo `.env` y deja un valor real para la variable:

```env
OPENSEARCH_INITIAL_ADMIN_PASSWORD=Admin12345!
```

Recomendacion: deja solo la contrasena en la linea, sin comentarios al final.

## 4. Crear las carpetas de datos

Este `compose` usa volumenes montados desde el directorio del proyecto. Crea las carpetas antes de levantar los contenedores:

```powershell
New-Item -ItemType Directory -Force -Path .\opensearch\data\opensearch-data1
New-Item -ItemType Directory -Force -Path .\opensearch\data\opensearch-data2
```

## 5. Levantar el ambiente

Desde la raiz del proyecto ejecuta:

```powershell
podman compose up -d
```

Si quieres forzar el archivo explicitamente:

```powershell
podman compose -f .\docker-compose.yml up -d
```

## 6. Verificar que los contenedores esten arriba

```powershell
podman ps
```

Ver logs de OpenSearch:

```powershell
podman logs opensearch-node1
podman logs opensearch-node2
```

Validar el endpoint principal:

```powershell
curl.exe -k -u admin:Admin12345! https://localhost:9200
```

Abrir OpenSearch Dashboards en:

```text
http://localhost:5601
```

## Servicios y puertos

- OpenSearch nodo 1: `https://localhost:9200`
- Performance Analyzer: `http://localhost:9600`
- OpenSearch Dashboards: `http://localhost:5601`

## Detener el ambiente

```powershell
podman compose down
```

## Borrar datos y volver a iniciar desde cero

Primero baja los contenedores:

```powershell
podman compose down
```

Luego elimina las carpetas de datos del proyecto:

```powershell
Remove-Item -Recurse -Force .\opensearch\data\opensearch-data1
Remove-Item -Recurse -Force .\opensearch\data\opensearch-data2
```

Y vuelve a crearlas:

```powershell
New-Item -ItemType Directory -Force -Path .\opensearch\data\opensearch-data1
New-Item -ItemType Directory -Force -Path .\opensearch\data\opensearch-data2
```

## Problemas comunes

### `podman compose` no conecta en Windows

Verifica que la maquina este encendida:

```powershell
podman machine start
```

### OpenSearch no levanta o se reinicia

Normalmente pasa por una de estas causas:

- `vm.max_map_count` no esta configurado.
- La contrasena en `.env` no es valida.
- No existen las carpetas `.\opensearch\data\opensearch-data1` y `.\opensearch\data\opensearch-data2`.
- La maquina de Podman no tiene memoria suficiente.

### El puerto ya esta en uso

Si `9200`, `9600` o `5601` ya estan ocupados, cambia el mapeo en `docker-compose.yml`.

## Comandos utiles

```powershell
podman compose up -d
podman compose down
podman ps
podman logs opensearch-node1
podman logs opensearch-dashboards
```
