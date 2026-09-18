#!/bin/sh
# Genera el PDF del dashboard y lo envía por SMTP. Todo por variables de entorno
# (las inyecta el CronJob). Flags oficiales del reporting-cli:
#   -u url | -f pdf|png|csv | -a basic | -c user:pass | -e smtp
#   -s FROM | -r TO | --smtphost | --smtpport | --subject
set -eu

: "${DASHBOARD_URL:?falta DASHBOARD_URL}"
: "${OPENSEARCH_PASSWORD:?falta OPENSEARCH_PASSWORD}"
: "${SMTP_HOST:?falta SMTP_HOST}"
: "${SMTP_PORT:?falta SMTP_PORT}"
: "${REPORT_SENDER:?falta REPORT_SENDER}"
: "${REPORT_RECIPIENTS:?falta REPORT_RECIPIENTS}"

REPORT_FORMAT="${REPORT_FORMAT:-pdf}"
REPORT_SUBJECT="${REPORT_SUBJECT:-Informe PQRS - Analitica}"
OPENSEARCH_USER="${OPENSEARCH_USER:-admin}"

echo "[report] generando ${REPORT_FORMAT} de ${DASHBOARD_URL} -> ${REPORT_RECIPIENTS}"

# SMTP interno de BBVA sin TLS ni auth -> se omiten --smtpsecure/--smtpusername.
# Si tu relay exige credenciales, agrega: --smtpusername "$SMTP_USER" --smtppassword "$SMTP_PASS"
exec opensearch-reporting-cli \
  -u "$DASHBOARD_URL" \
  -f "$REPORT_FORMAT" \
  -a basic \
  -c "${OPENSEARCH_USER}:${OPENSEARCH_PASSWORD}" \
  -e smtp \
  --smtphost "$SMTP_HOST" \
  --smtpport "$SMTP_PORT" \
  -s "$REPORT_SENDER" \
  -r "$REPORT_RECIPIENTS" \
  --subject "$REPORT_SUBJECT"
