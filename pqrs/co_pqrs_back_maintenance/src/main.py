import time
import json
import os
from datetime import datetime
from opensearchpy import OpenSearch

# Configuración de OpenSearch

host = 'localhost'
port = 9200
auth = ('admin', 'admin')

client = OpenSearch(
    hosts = [{'host': 'opensearch-node1', 'port': 9200}],
    http_compress = True,
    http_auth = ('admin', 'admin'),
    use_ssl = True,
    verify_certs = False,
    ssl_assert_hostname = False,
    ssl_show_warn = False
)

INDEX_REF = "conversations-reference"
INDEX_MSG = "conversations-messages"
EXPORT_DIR = "./backups"


os.makedirs(EXPORT_DIR, exist_ok=True)

def run_maintenance():
    print(f"[{datetime.now()}] Iniciando tarea de mantenimiento...")

    # 1. Buscar conversaciones inactivas hace >= 4 minutos
    query_inactive = {
        "size": 100, 
        "query": {
            "bool": {
                "must": [
                    {"term": {"status": "Open"}},
                    {"range": {"last_msg_date": {"lte": "now-4m"}}}
                ]
            }
        }
    }

    response_ref = client.search(body=query_inactive, index=INDEX_REF)
    reference_hits = response_ref['hits']['hits']

    if not reference_hits:
        print("No hay conversaciones inactivas para procesar.")
        return

    conversation_ids = [doc['_source']['conversation_id'] for doc in reference_hits]
    print(f"Hay {len(conversation_ids)} conversaciones para procesar")

    # 2. Obtener los mensajes correspondientes
    query_messages = {
        "size": 1000,
        "query": {
            "terms": {
                "conversation_id": conversation_ids
            }
        }
    }

    response_msg = client.search(body=query_messages, index=INDEX_MSG)
    messages_hits = response_msg['hits']['hits']

    # 3. Integrar ambos índices y wardar a JSON local
    messages_by_conv = {}
    for msg in messages_hits:
        c_id = msg['_source']['conversation_id']
        if c_id not in messages_by_conv:
            messages_by_conv[c_id] = []
        messages_by_conv[c_id].append(msg['_source'])

    integrated_data = []
    for ref in reference_hits:
        c_id = ref['_source']['conversation_id']
        integrated_data.append({
            "reference_info": ref['_source'],
            "messages": messages_by_conv.get(c_id, [])
        })

    # Guardar en archivo local con timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = os.path.join(EXPORT_DIR, f"backup_{timestamp}.json")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(integrated_data, f, ensure_ascii=False, indent=4)
    print(f"Datos guardados exitosamente en: {file_path}")

    # 4. Actualizar estado en ReferenceTable a "Closed"

    update_query = {
        "query": {
            "terms": {
                "conversation_id": conversation_ids
            }
        },
        "script": {
            "source": "ctx._source.status = 'Closed'",
            "lang": "painless"
        }
    }
    
    update_res = client.update_by_query(body=update_query, index=INDEX_REF)
    print(f"Documentos actualizados a Closed: {update_res.get('updated', 0)}")

    # 5. Borrar las conversaciones de MessagesTable
    delete_query = {
        "query": {
            "terms": {
                "conversation_id": conversation_ids
            }
        }
    }
    
    delete_mes = client.delete_by_query(body=delete_query, index=INDEX_MSG)
    print(f"Mensajes eliminados: {delete_mes.get('deleted', 0)}")
    print("-" * 100)

if __name__ == "__main__":
    try:
        run_maintenance()
    except Exception as e:
        print(f"Error durante la ejecución: {e}")
        