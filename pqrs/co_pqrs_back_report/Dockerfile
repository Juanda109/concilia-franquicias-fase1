# Módulo de reporte PQRS: genera el PDF de un dashboard de OpenSearch Dashboards
# (analítica) y lo envía por SMTP, usando el reporting-cli oficial de OpenSearch.
#
# NO existe imagen oficial `opensearchproject/reporting-cli`: el CLI se instala por
# npm y renderiza con Chromium (puppeteer). Esta imagen se construye aquí y se
# publica en el registry interno (igual que los demás módulos de backend), p.ej.:
#   quay.apps.work.ocp.co.igrupobbva/bbvaco/pqrs_back_report:v1
#
# Ajusta la base image a una APROBADA por BBVA si node:20 no está permitida, y
# asegúrate de que el build tenga acceso a npm y a los repos apt (o mirrors).
FROM node:20-bookworm-slim

# Chromium + librerías que el render headless necesita para el PDF.
RUN apt-get update && apt-get install -y --no-install-recommends \
      chromium \
      ca-certificates fonts-liberation \
      libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
      libxcomposite1 libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 \
      libasound2 libatspi2.0-0 \
  && rm -rf /var/lib/apt/lists/*

# Usar el Chromium del sistema (no descargar el de puppeteer).
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    CHROMIUM_PATH=/usr/bin/chromium \
    HOME=/tmp

RUN npm install -g @opensearch-project/reporting-cli

WORKDIR /app
COPY report.sh ./
RUN chmod +x /app/report.sh

CMD ["/app/report.sh"]
