# Co-PQRS Back Conversation Extractor

## 📋 Descripción

Módulo de extracción y transformación de conversaciones desde MinIO hacia archivos Excel para Looker. Se ejecuta cada 30 minutos como CronJob en Kubernetes.

**Características principales:**
- Extrae conversaciones del bucket MinIO: `pqr-conversations-history/conversation/{customer_id}_{YYYYMMDD}/YYYY/MM/DD/*.json`
- Extrae conversaciones del bucket MinIO: `pqr-conversations-history/conversations/{customer_id}_{YYYYMMDD}/YYYY/MM/DD/*.json`
- Transforma datos y genera Excel con columnas normalizadas
- Implementa deduplicación robusta (Opción 4 Combinada)
- Soporta append mode: agrupa ~1000 conversaciones/día en un Excel
- Manejo inteligente de valores nulos
- Logs detallados de ejecución
- **Salida**: `/mnt/ada_data/looker_conversation_pqrs/conversaciones_YYYYMMDD.xlsx` (misma ruta que `co_pqrs_back_load_ada_data`)

---

## 🔄 Flujo de Proceso

```
1. Carga configuración desde variables de entorno
   ↓
2. Conecta a MinIO con credenciales
   ↓
3. Valida/crea carpeta destino: {RUTA_PROCESO}/looker_conversation_pqrs/
   ↓
4. Extrae conversation_ids del Excel existente (si existe) → Set de deduplicación
   ↓
5. Lista conversaciones desde pqr-conversations-history/conversations/
   ↓
6. Para cada conversación:
   ├─ Extrae conversation_id de la ruta
   ├─ Verifica si ya fue procesada (deduplicación)
   │  ├─ SÍ → SKIP + Log warning
   │  └─ NO → Procesar normalmente
   ├─ Descarga y parsea JSON
   ├─ Ordena mensajes por responded_at
   └─ Extrae campos: FECHA, CLIENTE, FEEDBACK, CONVERSACION, timestamp
   ↓
7. Crea o abre Excel: conversaciones_YYYYMMDD.xlsx (APPEND MODE)
   ↓
8. Agrega filas + columna auxiliar _CONV_ID
   ↓
9. Guarda en filesystem
   ↓
10. Registra resumen: "1000 procesadas, 45 duplicadas (skipped)"
```

---

## 📊 Estructura Excel

| Columna | Tipo | Contenido | Ejemplo |
|---|---|---|---|
| **FECHA** | Texto | YYYY-MM-DD | 2026-07-28 |
| **CLIENTE** | Texto | user_id o "SIN_DATO" | 09690295 |
| **FEEDBACK** | Texto | satisfaction_status | positive |
| **CONVERSACION** | Texto | Mensajes concatenados | "agent: Hola\nclient: Buenos días" |
| **timestamp** | Texto | ISO con timezone | 2026-07-28T15:30:45Z |
| **_CONV_ID** | Texto | ID único (auxiliar) | 09690295_20260728 |

---

## 🔐 Deduplicación (Opción 4 - Combinada)

### Estrategia
1. **Primera carga**: Extrae set de `conversation_id` del Excel existente
2. **Procesamiento**: Compara cada `conversation_id` vs set
   - Si existe → SKIP (log warning: "Conversación 09690295_20260728 ya existe")
   - Si es nuevo → Procesar normalmente
3. **Secondary check**: Valida `closed_at` vs timestamp de última ejecución
4. **Persistencia**: Almacena `_CONV_ID` en Excel para próximas ejecuciones

### Ventajas
- ⚡ Búsqueda O(1) en set
- 🛡️ Backup timestamp si falla deduplicación
- 📈 Escalable hasta 1000+ conversaciones/día
- 📝 Logs detallados de duplicados detectados

---

## 🔧 Variables de Entorno

### Requeridas
```env
MINIO_ENDPOINT_URL=http://minio.pqr-genai-dev.svc.cluster.local:9000
MINIO_ACCESS_KEY=<secret>
MINIO_SECRET_KEY=<secret>
MINIO_BUCKET=pqr-conversations-history
```

### Opcionales
```env
MINIO_REGION=us-east-1
RUTA_PROCESO=/mnt/ada_data
LOOKER_FOLDER_NAME=looker_conversation_pqrs
MINIO_CONVERSATIONS_PREFIX=conversations
CONVERSATIONS_BATCH_SIZE=100
LOG_LEVEL=INFO
```

---

## 🏃 Ejecución Local

### Requisitos
- Python 3.11+
- MinIO accesible
- Variables de entorno configuradas

### Instalación
```bash
cd co_pqrs_back_conversation_extractor
pip install .
```

### Ejecución
```bash
# Definir variables de entorno requeridas
export MINIO_ENDPOINT_URL=http://localhost:9000
export MINIO_ACCESS_KEY=minioadmin
export MINIO_SECRET_KEY=minioadmin
export MINIO_BUCKET=pqr-conversations-history

# Ejecutar proceso
python main.py
```

---

## 🐳 Ejecución con Docker

### Build
```bash
docker build -t quay.apps.work.ocp.co.igrupobbva/bbvaco/co_pqrs_back_conversation_extractor:v1 .
```

### Run (local)
```bash
docker run \
  -e MINIO_ENDPOINT_URL=http://minio:9000 \
  -e MINIO_ACCESS_KEY=minioadmin \
  -e MINIO_SECRET_KEY=minioadmin \
  -e RUTA_PROCESO=/mnt/ada_data \
  -v $PWD/ada_data:/mnt/ada_data \
  co-pqrs-back-conversation-extractor:latest
```

---

## ☸️ Deployment en Kubernetes

### Crear Secrets
```bash
El secreto de MinIO (`minio-creds`) ya existe en OKD para este entorno.
```

### Aplicar CronJob
```bash
kubectl apply -k IaC/backend
```

### Monitorear
```bash
# Ver ejecuciones
kubectl get cronjobs -n pqr-genai-dev
kubectl get jobs -n pqr-genai-dev

# Ver logs
kubectl logs -n pqr-genai-dev -l app.kubernetes.io/name=co-pqrs-back-conversation-extractor --tail=100
```

---

## 📝 Manejo de Valores Especiales

| Caso | Valor | Ejemplo |
|---|---|---|
| Campo NULL/no existe | "SIN_DATO" | CLIENTE = "SIN_DATO" |
| Array de mensajes vacío | "SKIP" | CONVERSACION = "SKIP" |
| closed_at ausente | "SIN_DATO" | timestamp = "SIN_DATO" |

---

## 📊 Volumen Procesado

- **Por día**: ~1000 conversaciones
- **Por ejecución (30 min)**: ~20-30 conversaciones
- **Scope temporal**: Últimas 24h
- **Modo**: Append (acumula en Excel diario)
- **Salida**: Un archivo Excel por día de formato `conversaciones_YYYYMMDD.xlsx`

---

## 🧪 Testing

```bash
# Instalar dependencias de test
pip install -e ".[dev]"

# Ejecutar tests
pytest tests/ -v

# Con cobertura
pytest tests/ --cov=. --cov-report=html
```

---

## 📦 Estructura de Archivos

```
co_pqrs_back_conversation_extractor/
├── main.py                    # Lógica principal
├── pyproject.toml            # Configuración del proyecto
├── Dockerfile                # Imagen Docker
├── cronJob.yml               # Manifest Kubernetes
├── README.md                 # Este archivo
├── src/
│   └── __init__.py
└── tests/
    ├── conftest.py
    ├── test_minio_connection.py
    ├── test_conversation_listing.py
    ├── test_data_extraction.py
    └── test_batch_processing.py
```

---

## 🔍 Logs

Formato de logs:
```
[2026-07-28 15:30:45] INFO     Iniciando extracción de conversaciones...
[2026-07-28 15:30:46] INFO     Conectado a MinIO en http://minio:9000
[2026-07-28 15:30:47] INFO     Cargadas 145 conversation_ids del Excel existente
[2026-07-28 15:31:00] WARNING  Conversación 09690295_20260728 ya existe (DUPLICADA)
[2026-07-28 15:32:15] INFO     Procesadas: 1000, Duplicadas (skipped): 45
[2026-07-28 15:32:16] INFO     Excel guardado en /mnt/ada_data/looker_conversation_pqrs/conversaciones_20260728.xlsx
```

---

## 🚀 Roadmap

- [ ] Implementar WebSocket para notificaciones en tiempo real
- [ ] Agregar estadísticas por tipo de feedback
- [ ] Cacheo de MinIO credentials en memory
- [ ] Soporte para múltiples buckets
- [ ] Dashboard de monitoreo

---

## 📞 Soporte

Para problemas o sugerencias, contactar al equipo de datos.
