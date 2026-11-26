import logging
from dataclasses import asdict
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.repositories.database import connection
from app.ingestion.orchestrator import ParseoOrchestrator

logger = logging.getLogger(__name__)

app = FastAPI(title="Concilia Franquicias Fase 1 - API de Parseo", version="1.0.0")


class ParseRequest(BaseModel):
    idArchivo: int
    tipoInsumo: str
    minioKey: str
    correlationId: str


@app.get('/health')
def health():
    return {'status': 'UP'}


@app.post('/parse')
def parse(req: ParseRequest):
    with connection() as c:
        try:
            result = ParseoOrchestrator(c).execute(req.idArchivo, req.tipoInsumo, req.minioKey, req.correlationId)
        except KeyError:
            raise HTTPException(400, 'PARSER_NO_IMPLEMENTADO')
        except Exception:
            # El orquestador ya marcó ESTADO_PROCESAMIENTO='Error' en la BD (con el
            # motivo) antes de relanzar. El detalle de la excepción va solo al log;
            # la respuesta lleva un mensaje fijo para no exponer trazas ni SQL.
            logger.exception("Error procesando archivo %d (correlationId=%s)", int(req.idArchivo),
                             req.correlationId.replace('\r', '').replace('\n', ''))
            return {"estadoProcesamiento": "Error", "registrosInsertados": 0,
                    "errores": [{"codigo": "ERROR_PROCESAMIENTO", "mensaje": "Error interno de procesamiento"}],
                    "controles": []}
        return {
            "estadoProcesamiento": "Error" if result.errors else "Procesado",
            "registrosInsertados": len(result.records) if not result.errors else 0,
            "errores": [asdict(e) for e in result.errors],
            "controles": result.controls,
        }
