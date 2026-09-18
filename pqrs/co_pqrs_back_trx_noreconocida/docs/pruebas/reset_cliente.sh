#!/usr/bin/env bash
# Deja un cliente de la matriz "a cero" para probar desde el principio en la UI.
#
#   ./reset_cliente.sh 1013634959          # un cliente
#   ./reset_cliente.sh --todos             # los 12 de la matriz
#
# Limpia las TRES capas de estado que arrastran entre pruebas:
#   1. La conversacion del dia (una por cliente/dia: si existe, el bot RETOMA
#      donde quedo en vez de empezar).  ayer/hoy/manana en UTC.
#   2. El caso durable (trx-no-reconocida-cases): la recurrencia-BOT cuenta las
#      entradas por la opcion 4 -- una segunda entrada en la ventana desvia a
#      PQR. Es comportamiento correcto en produccion, pero entre pruebas hay
#      que borrarlo.
#   3. El contador diario de interacciones (client-control-table): con varias
#      pasadas el mismo dia puede saltar el limite por categoria.
#
# Lo que NO toca (y no hace falta): Postgres y los fixtures del simulador son
# solo-lectura por cliente -- no acumulan estado.

set -euo pipefail
OS="https://localhost:9200"
AUTH="admin:admin"

MATRIZ=(1013634958 1013634959 1013634960 1013634961 1013634962 1013634963
        1013634964 1013634965 1013634966 1013634967 1013634968 1013634969 98787954 10482895 01576905)

reset_uno() {
  local uid="$1"
  # 1. conversaciones ayer/hoy/manana (el servidor estampa el dia en UTC).
  # Fechas con python3: el date de macOS y el de GNU no comparten sintaxis, y
  # con set -e un date fallido abortaba el script ANTES de limpiar el caso
  # durable -- el sintoma era "reseteo y aun asi me desvia por recurrencia".
  for dia in $(python3 -c "
from datetime import datetime,timedelta,timezone
h=datetime.now(timezone.utc)
print(' '.join((h+timedelta(days=d)).strftime('%Y%m%d') for d in (-1,0,1)))"); do
    curl -sk -u "$AUTH" -X DELETE "$OS/conversations-reference/_doc/${uid}_${dia}" -o /dev/null
  done
  # 2. caso durable (recurrencia-bot)
  curl -sk -u "$AUTH" -X DELETE "$OS/trx-no-reconocida-cases/_doc/${uid}" -o /dev/null
  # 3. contador diario. refresh=true: sin el, el borrado esta aplicado pero
  # aun no es visible para las busquedas, y una comprobacion (o una lectura
  # del agente) inmediatamente despues puede leer el valor viejo.
  curl -sk -u "$AUTH" -X POST "$OS/client-control-table/_delete_by_query?refresh=true" \
    -H 'Content-Type: application/json' \
    -d "{\"query\":{\"term\":{\"client_id.keyword\":\"${uid}\"}}}" -o /dev/null
  curl -sk -u "$AUTH" -X POST "$OS/conversations-reference/_refresh" -o /dev/null
  echo "  ${uid} a cero"
}

if [ "${1:-}" = "--todos" ]; then
  for uid in "${MATRIZ[@]}"; do reset_uno "$uid"; done
elif [ -n "${1:-}" ]; then
  reset_uno "$1"
else
  echo "uso: $0 <user_id> | --todos"; exit 1
fi
