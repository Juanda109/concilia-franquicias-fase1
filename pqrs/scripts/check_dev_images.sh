#!/usr/bin/env bash
# Compara las tres capas que tienen que coincidir antes de capturar evidencias:
#   1. lo que DECLARA el manifiesto de la rama (git, funciona sin red)
#   2. lo que EXISTE en el registro          (skopeo, exige red del banco)
#   3. lo que CORRE en el ambiente           (oc, exige sesion iniciada)
#
# Uso:  scripts/check_dev_images.sh [rama] [namespace]
#       scripts/check_dev_images.sh origin/feature/PQRSdev pqr-genai-dev
set -uo pipefail
cd "$(dirname "$0")/.."

RAMA="${1:-origin/feature/PQRSdev}"
NS="${2:-pqr-genai-dev}"
REG="quay.apps.work.ocp.co.igrupobbva/pqr-genai"
ULTIMO_ERROR=""
SERVICIOS="co_pqrs_back_agent co_pqrs_benchmark co_pqrs_front_test co_pqrs_back_error_handler co_pqrs_back_trx_noreconocida co_pqrs_back_data co_pqrs_back_doble_cobro"

tiene() { command -v "$1" >/dev/null 2>&1; }
# Para consultar el registro sirve cualquiera de los tres; se usa el primero disponible.
CONSULTA=""
tiene skopeo && CONSULTA=skopeo
[ -z "$CONSULTA" ] && tiene podman && CONSULTA=podman
[ -z "$CONSULTA" ] && tiene docker && CONSULTA=docker
HAY_OC=no; tiene oc && HAY_OC=si

# existe_en_registro <imagen:tag>
#   0 = esta en el registro
#   1 = NO esta (el registro respondio y dijo que no existe)
#   2 = no se pudo comprobar (sin red, sin sesion, certificado, etc.)
# La distincion importa: un fallo de red no es una imagen ausente.
existe_en_registro() {
  local salida rc
  case "$CONSULTA" in
    skopeo) salida=$(skopeo inspect --format '{{.Digest}}' "docker://$REG/$1" 2>&1); rc=$? ;;
    podman) salida=$(podman manifest inspect "$REG/$1" 2>&1); rc=$? ;;
    docker) salida=$(docker manifest inspect "$REG/$1" 2>&1); rc=$? ;;
    *) return 2 ;;
  esac
  [ $rc -eq 0 ] && return 0
  # El registro contesto y la imagen no esta
  printf '%s' "$salida" | grep -qiE 'manifest unknown|manifest for .* not found|not found|no such manifest|does not exist|MANIFEST_UNKNOWN' && return 1
  # Cualquier otra cosa es un problema de acceso, no una ausencia
  ULTIMO_ERROR=$(printf '%s' "$salida" | head -1 | cut -c1-70)
  return 2
}

# Sonda previa: si el registro no contesta, no tiene sentido preguntar siete veces
if [ -n "$CONSULTA" ]; then
  existe_en_registro "co_pqrs_back_agent:__sonda__"; sonda=$?
  if [ $sonda -eq 2 ]; then
    echo "AVISO: no se pudo consultar el registro. Motivo: ${ULTIMO_ERROR:-desconocido}"
    echo "       La columna REGISTRO quedara sin datos; no significa que falten las imagenes."
    echo
    CONSULTA=""
  fi
fi

echo "Rama:      $RAMA"
echo "Ambiente:  $NS"
echo "Registro:  $REG"
echo "consulta al registro: ${CONSULTA:-ninguna}   oc: $HAY_OC"
echo

# --- 3. lo que corre ahora, en una sola consulta
CORRIENDO=""
if [ "$HAY_OC" = si ]; then
  CORRIENDO=$(oc -n "$NS" get deploy,cronjob \
    -o jsonpath='{range .items[*]}{..image}{"\n"}{end}' 2>/dev/null | tr ' ' '\n' | grep "$REG" || true)
  [ -z "$CORRIENDO" ] && echo "AVISO: oc no devolvio imagenes; revisa la sesion o el namespace." && echo
fi

printf '%-32s %-14s %-12s %-12s %s\n' SERVICIO DECLARADO REGISTRO CORRIENDO VEREDICTO
printf '%-32s %-14s %-12s %-12s %s\n' "--------------------------------" "-------------" "-----------" "-----------" "---------"

FALTAN=0; DESFASE=0
for s in $SERVICIOS; do
  tag=$(git grep -h -oE "pqr-genai/$s:[A-Za-z0-9_.-]+" "$RAMA" -- IaC 2>/dev/null | sed "s#.*:##" | sort -u | head -1)
  [ -z "$tag" ] && tag="(no declarado)"

  reg="-"
  if [ -n "$CONSULTA" ] && [ "$tag" != "(no declarado)" ]; then
    existe_en_registro "$s:$tag"; case $? in 0) reg="si";; 1) reg="NO";; *) reg="?";; esac
  fi

  run="-"
  if [ -n "$CORRIENDO" ]; then
    run=$(printf '%s\n' "$CORRIENDO" | grep "/$s:" | sed "s#.*:##" | sort -u | head -1)
    [ -z "$run" ] && run="(sin pod)"
  fi

  ver="sin datos"
  if [ "$reg" = "NO" ]; then ver="FALTA CONSTRUIR"; FALTAN=$((FALTAN+1))
  elif [ "$reg" = "si" ] && [ "$run" = "$tag" ]; then ver="lista"
  elif [ "$reg" = "si" ] && [ "$run" != "-" ] && [ "$run" != "$tag" ]; then ver="FALTA APLICAR"; DESFASE=$((DESFASE+1))
  elif [ "$reg" = "si" ]; then ver="en registro"
  fi

  printf '%-32s %-14s %-12s %-12s %s\n' "$s" "$tag" "$reg" "$run" "$ver"
done

echo
if [ -z "$CONSULTA" ] && [ "$HAY_OC" = no ]; then
  echo "Solo se pudo leer el manifiesto. Ejecuta este script desde la red del banco,"
  echo "con skopeo, podman o docker para el registro, y con sesion de oc iniciada."
  exit 0
fi
[ "$FALTAN" -gt 0 ] && echo "$FALTAN imagen(es) sin subir al registro: hay que construirlas."
[ "$DESFASE" -gt 0 ] && echo "$DESFASE servicio(s) corriendo con un tag distinto al declarado: falta aplicar el IaC."
[ "$FALTAN" -eq 0 ] && [ "$DESFASE" -eq 0 ] && echo "Todo coincide: registro y ambiente al dia con el manifiesto."
exit $(( FALTAN + DESFASE > 0 ? 1 : 0 ))
