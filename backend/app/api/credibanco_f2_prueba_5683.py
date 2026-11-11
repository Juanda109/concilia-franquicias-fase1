"""Escenario tecnico controlado, deshabilitado salvo activacion explicita."""
import os
from datetime import date
from fastapi import APIRouter, HTTPException
from app.services.fase2.cierre_credibanco_pg_v67 import ejecutar

router = APIRouter(prefix="/api/v1/jornadas", tags=["F2 diagnostico aislado"])

@router.get("/{id_jornada}/credibanco-f2-prueba-5683")
def diagnostico_prueba_5683(id_jornada: int):
    if os.getenv("CONCILIA_F2_DIAGNOSTICO_TEST") != "1" or id_jornada != 5683:
        raise HTTPException(status_code=404, detail="Diagnostico de prueba no habilitado")
    regla = {
        "id_regla": "CB-F2-TEST-302-CANJE-CREDITO-10112026",
        "version": "TEST-20261110-01", "estado": "APROBADA",
        "evidencia_aprobacion": "PRUEBA_TECNICA_LOCAL_NO_PRODUCTIVA",
        "insumo": "CANT", "concepto": "017-CANJE RECIBIDO TARJETA CREDITO",
        "tx": "02", "campo_importe": "total_valor",
        "cuenta_host": "299095302", "centro_host": "0017",
        "fuente_host": "HA22", "moneda": "COP",
        "naturaleza_host": "DEBE_MENOS_HABER", "factor_signo": 1,
        "escala_origen": "1", "tolerancia": "0",
        "fechas_host_validas": ["2026-11-10"]
    }
    try:
        resultado = ejecutar(id_jornada, reglas_diagnostico=[regla])
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail="Escenario de prueba inconsistente") from exc
    if resultado is None or str(resultado.get("fecha_contable")) != "2026-11-10":
        raise HTTPException(status_code=409, detail="Jornada o fecha no coincide")
    cruces = resultado.get("cruces_host_credibanco_diagnosticos", [])
    if len(cruces) != 1:
        raise HTTPException(status_code=409, detail="Cantidad de cruces inesperada")
    cruce = cruces[0]
    if cruce.get("archivos_origen") != [5046] or cruce.get("archivo_host") != [5035]:
        raise HTTPException(status_code=409, detail="Archivos no corresponden al escenario aislado")
    evidencias = resultado.get("evidencia_monetaria_regla_prueba", [])
    if len(evidencias) != 1 or evidencias[0].get("vl_total") is None:
        raise HTTPException(status_code=409, detail="Evidencia monetaria CANT incompleta")
    from decimal import Decimal
    if Decimal(evidencias[0]["vl_total"]) != Decimal(cruce["valor_franquicia"]):
        raise HTTPException(status_code=409, detail="VL TOTAL no coincide con valor de cruce")
    return {"id_jornada": id_jornada, "fecha_contable": "2026-11-10",
            "tipo": "PRUEBA_DIAGNOSTICA_NO_CERTIFICADA", "certificado": False,
            "origen_canje": evidencias[0], "cruces": cruces}
