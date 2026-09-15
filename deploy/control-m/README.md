# Control-M Local Colombia

Orquestación funcional de Fase 1:
Control-M Local Colombia -> Hub Linux -> SFTP puerto 22 -> MinIO/OKD.

Definir por ambiente: jobs, calendarios, ventanas, dependencias, reintentos, usuario SFTP y rutas MinIO.
No duplicar esta orquestación con CronJobs OKD. Un CronJob OKD solo aplica a una tarea técnica interna explícitamente justificada.
