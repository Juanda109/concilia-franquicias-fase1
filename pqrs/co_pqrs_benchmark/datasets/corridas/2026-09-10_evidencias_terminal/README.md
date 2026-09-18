# Evidencias de terminal (locales) · 10-sep-2026

Capturas de texto de los comandos de la guía de captura (`docs/MATRIZ_EVIDENCIAS_RSS.md`) que
no dependen del ambiente de dev. Cada fichero lleva el id de la evidencia, el control, la fecha
y el commit. Para el documento de evidencias en Drive se adjunta el fichero y una captura de
pantalla del terminal con el mismo contenido.

| Evidencia | Control | Fichero | Qué muestra |
|---|---|---|---|
| E03 | IT1.2 | `IT1.2-E03_terminal_resumenes_contingencia_local.txt` | resúmenes de las corridas en contingencia (piso sin LLM) de TNR, adversarial, bypass y grounding |
| E10 | IT3.6, IT3.7, IT1.5 | `IT3.6-E10_terminal_barrido_trazas_local.txt` | el barrido detecta los cinco tipos de dato sensible en un objeto sintético "antes" y devuelve 0 en el objeto "después"; la E10 definitiva se toma contra `audit-logs` en dev |
| E11 | IT1.5, IT3.3, IT4.4, IT4.5 | `IT1.5-E11_terminal_suites_en_verde_local.txt` | las seis suites con su conteo final; los rojos son preexistentes y están identificados |
| E17 | IT2.5 | `IT2.5-E17_terminal_historial_general_yml_local.txt` | historial de commits del catálogo de ruteo (versionamiento de la base de conocimiento) |
| E23 | IT4.2 | `IT4.2-E23_terminal_catalogo_capacidades_local.txt` | generación del catálogo (34 acciones, 4 con efecto, 0 saltos) y tests de contrato e integridad en verde |

Pendientes de dev (ver la guía): E01, E02, E04, E05, E06, E07, E08, E09, E12, E13, E14, E15,
E16, E18, E19, E20, E21, E22, E24, E25, E26; y la corrida con el modelo real que reemplaza a E03.
