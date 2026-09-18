import requests
import json
import urllib3
import time  # <-- Importamos el módulo time para las pausas

# Desactivar advertencias de SSL para entornos QA
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def obtener_tsec():
    """
    Realiza la petición de autenticación y retorna el token tsec.
    """
    url = "https://qa-glomo.bbva.com.co/SERVGM_QA/TechArchitecture/co/grantingTicket/V02"
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    payload = {
        "authentication": {
            "userID": "CC000001069759414",
            "consumerID": "12000069",
            "authenticationType": "02",
            "authenticationData": [
                {
                    "idAuthenticationData": "password",
                    "authenticationData": ["Prueba01"]
                }
            ]
        },
        "backendUserRequest": {
            "userId": "",
            "accessCode": "CC000001069759414",
            "dialogId": ""
        }
    }

    try:
        response = requests.post(url, json=payload, headers=headers, verify=False)
        response.raise_for_status() # Lanza excepción si el status no es 2xx
        
        # Retorna el tsec si existe, o None si no lo encuentra
        return response.headers.get('tsec')

    except requests.exceptions.RequestException as e:
        print(f"[Error] Falló la obtención del tsec: {e}")
        return None


def consultar_financial_overview(tsec):
    """
    Recibe el token tsec y realiza la consulta al endpoint de financial-overview.
    """
    url = "https://qa-glomo.bbva.com.co/SERVGM_QA/financial-overview/v0/financial-overview"
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "tsec": tsec  # Aquí inyectamos el token recibido por argumento
    }

    payload = {
        "contracts.classification.type": None,
        "contracts.classification.level.id": None,
        "contracts.classification.level.name": None,
        "contracts.productType": None,
        "isGroupedPortfolio": None,
        "showPending": None,
        "showSicav": None,
        "contracts.id": None,
        "contracts.relatedContracts.contractProductType.id": None,
        "contracts.relatedContracts.relationType.id": None,
        "unmasked": None,
        "customer.id": None
    }

    try:
        # Petición GET pasando el payload en el parámetro json
        response = requests.get(url, headers=headers, params=payload, verify=False)
        
        print(f"Status Code Financial Overview: {response.status_code}")
        print("-" * 40)
        
        try:
            print(json.dumps(response.json(), indent=4))
        except json.JSONDecodeError:
            print("La respuesta no es un JSON válido:")
            print(response.text)

    except requests.exceptions.RequestException as e:
        print(f"[Error] Falló la consulta de financial overview: {e}")


# ==========================================
# FLUJO PRINCIPAL DE EJECUCIÓN
# ==========================================
if __name__ == "__main__":
    # Bucle infinito para que se ejecute continuamente
    while True:
        print("Iniciando proceso...")
        
        # 1. Llamamos a la primera función y guardamos el resultado
        token_tsec = obtener_tsec()
        
        # 2. Verificamos si obtuvimos el token correctamente
        if token_tsec:
            print("TSEC obtenido correctamente. Procediendo con la consulta financiera...\n")
            
            # 3. Pasamos el token como argumento a la segunda función
            consultar_financial_overview(token_tsec)
        else:
            print("No se pudo continuar porque no se obtuvo el token tsec.")
        
        # 4. Pausar la ejecución por 3 minutos (180 segundos)
        print("\n[Esperando 3 minutos para la próxima ejecución...]")
        print("=" * 60 + "\n")
        time.sleep(180)