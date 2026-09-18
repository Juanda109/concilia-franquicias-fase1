import pandas as pd
import requests
import json
from datetime import datetime, timedelta, timezone

# Lista de client_id


# Archivo CSV
csv_file = "data/unificado_prioridad_sample_new_pqrs.csv"

# Leer CSV
df = pd.read_csv(csv_file, dtype={"customer_id": str})
client_ids = df["customer_id"].str.strip().tolist()


# Configuración
url_base = "https://localhost:9200/client-control-table/_doc"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Basic YWRtaW46YWRtaW4="
}

# Fechas dinámicas
now = datetime.now(timezone.utc)
expires = now + timedelta(days=30)

for client_id in client_ids:

    payload = {
        "client_id": client_id,
        "total_interactions": 1,
        "last_interaction_at": now.isoformat(),
        "last_flow_id": "cuenta_embargada",
        "last_flow_label": "Cuenta Embargada",
        "updated_at": now.isoformat(),
        "expires_at": expires.isoformat(),

        "workflows": {},

        "daily": {},

        "monthly": {
            now.strftime("%Y-%m"): {
                "total_interactions": 1,
                "last_interaction_at": now.isoformat(),
                "workflows": {
                    "cuenta_embargada": {
                        "count": 1,
                        "last_interaction_at": now.isoformat(),
                        "label": "Cuenta Embargada",
                        "data": {}
                    }
                }
            }
        }
    }

    url = f"{url_base}/{client_id}"

    try:
        response = requests.put(
            url,
            headers=headers,
            data=json.dumps(payload),
            verify=False  # porque estás usando localhost con HTTPS
        )

        print(f"[{client_id}] Status: {response.status_code}")
        print(response.text)

    except Exception as e:
        print(f"[{client_id}] Error: {e}")