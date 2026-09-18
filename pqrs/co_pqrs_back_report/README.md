# co_pqrs_back_report

Módulo (CronJob) que genera un **PDF de un dashboard de OpenSearch Dashboards**
(clúster de analítica) y lo **envía por correo (SMTP)**. Usa el
`@opensearch-project/reporting-cli` (no hay imagen oficial; se construye aquí).

## Qué hace
En cada ejecución (diaria) renderiza el dashboard indicado en `DASHBOARD_URL` y lo
manda a `REPORT_RECIPIENTS` por el SMTP interno de BBVA.

## Construir y publicar la imagen (como los demás módulos)
```bash
docker build -t quay.apps.work.ocp.co.igrupobbva/bbvaco/pqrs_back_report:v1 .
docker push  quay.apps.work.ocp.co.igrupobbva/bbvaco/pqrs_back_report:v1
```
(o el pipeline/registry que usen los demás `co_pqrs_back_*`). Luego, el CronJob en
`IaC/backend/co_pqrs_back_report/00-cronjob.yaml` ya apunta a esa imagen.

## Variables de entorno (las inyecta el CronJob)
| Var | Descripción |
|---|---|
| `DASHBOARD_URL` | URL del dashboard en OSD analítica (`http://opensearch-dashboards-analytics:5601/app/dashboards#/view/<ID>`). |
| `REPORT_FORMAT` | `pdf` (default), `png` o `csv`. |
| `REPORT_SENDER` | Remitente (`agente_pqrs@bbva.com`). |
| `REPORT_RECIPIENTS` | Destinatarios (uno o varios separados por coma). |
| `REPORT_SUBJECT` | Asunto del correo. |
| `SMTP_HOST` / `SMTP_PORT` | SMTP interno (`mailB.bbva.com.co` / `25`), sin auth ni TLS. |
| `OPENSEARCH_PASSWORD` | Password del usuario `admin` del OpenSearch analítico (secret `opensearch-analytics-secret`), para que el CLI inicie sesión en OSD y lo renderice. |

## Requisitos
- Debe existir un **dashboard guardado** en OSD y su **ID** en `DASHBOARD_URL`.
- `opensearch-dashboards-analytics` (OSD) y `opensearch-analytics` arriba.
- Secret `opensearch-analytics-secret`.

## Probar manualmente
```bash
oc create job --from=cronjob/co-pqrs-back-report prueba-reporte -n pqr-genai-dev
oc logs -f job/prueba-reporte -n pqr-genai-dev
```

## Notas
- Chromium en OpenShift: el CronJob usa una SA con `anyuid`; si aparece error de
  "sandbox" de Chromium, lanzar puppeteer con `--no-sandbox`.
- Si el relay SMTP exigiera credenciales, agregar `--smtpusername/--smtppassword`
  en `report.sh` (hoy el relay interno no las requiere).
