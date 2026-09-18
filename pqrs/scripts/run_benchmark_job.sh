#!/usr/bin/env bash
# Lanza una corrida puntual del banco de casos dentro del cluster, con el ORIGEN correcto.
#
# Importa el origen: los tableros filtran por el. Una corrida adversarial publicada como
# "benchmark" no aparece en el tablero adversarial, y la evidencia se pierde.
#
#   dataset                        origen        tablero que la recoge
#   trx_no_reconocida_routing      benchmark     PQRS · Benchmark de ruteo
#   doble_cobro_routing            benchmark     PQRS · Benchmark de ruteo
#   adversarial_routing            adversarial   PQRS · Adversarial y bypass
#   bypass_flows                   adversarial   PQRS · Adversarial y bypass
#   grounding                      grounding     PQRS · Grounding
#   canario_rutas_criticas         canario       PQRS · Canario de ruteo
#
# Uso:  scripts/run_benchmark_job.sh <dataset> [nombre-corrida]
#       scripts/run_benchmark_job.sh trx_no_reconocida_routing evidencia-tnr
set -euo pipefail

DATASET="${1:?falta el dataset, sin extension}"
NS="${NS:-pqr-genai-dev}"
IMG="${IMG:-quay.apps.work.ocp.co.igrupobbva/pqr-genai/co_pqrs_benchmark:v9}"

case "$DATASET" in
  adversarial_routing|bypass_flows) SOURCE=adversarial; MONTAJE=conf-pqrs-benchmark-dataset ;;
  grounding)                        SOURCE=grounding;   MONTAJE=conf-pqrs-benchmark-dataset ;;
  canario_rutas_criticas)           SOURCE=canario;     MONTAJE=conf-pqrs-benchmark-canario-dataset ;;
  trx_no_reconocida_routing|doble_cobro_routing) SOURCE=benchmark; MONTAJE=conf-pqrs-benchmark-dataset ;;
  *) echo "dataset no reconocido: $DATASET"; exit 1 ;;
esac

RUN="${2:-$DATASET}"
JOB="bench-$(printf '%s' "$RUN" | tr '_' '-' | tr -cd 'a-z0-9-' | cut -c1-40)-$(date +%H%M%S)"

cat <<YAML | oc -n "$NS" apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: $JOB
  labels: { app: co-pqrs-benchmark, origen: "$SOURCE" }
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 86400
  template:
    metadata:
      labels: { app: co-pqrs-benchmark }
    spec:
      restartPolicy: Never
      containers:
        - name: co-pqr-benchmark
          image: $IMG
          imagePullPolicy: Always
          command: ["python", "main.py"]
          envFrom:
            - configMapRef: { name: conf-pqrs-benchmark-env }
          env:
            - { name: TZ, value: "America/Bogota" }
            - { name: RABBITMQ_ENABLED, value: "true" }
            - { name: MINIO_ENABLED, value: "false" }
            - { name: BENCHMARK_SOURCE, value: "$SOURCE" }
            - { name: INPUT_JSON, value: "/data/input/$DATASET.json" }
            - { name: RUN_NAME, value: "$RUN" }
            - { name: SUMMARY_TXT, value: "/tmp/summary.txt" }
            - { name: OUTPUT_JSON, value: "/dev/stdout" }
            - name: RABBITMQ_USER
              valueFrom: { secretKeyRef: { name: rabbitmq-secret, key: username } }
            - name: RABBITMQ_PASSWORD
              valueFrom: { secretKeyRef: { name: rabbitmq-secret, key: password } }
          resources:
            requests: { cpu: 200m, memory: 256Mi }
            limits:   { cpu: 1000m, memory: 1024Mi }
          volumeMounts:
            - { name: dataset, mountPath: /data/input, readOnly: true }
      volumes:
        - name: dataset
          configMap: { name: $MONTAJE }
YAML

echo
echo "Corrida '$RUN' lanzada como $JOB, origen=$SOURCE"
echo "Seguirla:   oc -n $NS logs -f job/$JOB"
echo "Resumen:    oc -n $NS logs job/$JOB | tail -40"
