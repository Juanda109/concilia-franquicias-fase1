"""INC56-J: puente DEPO-Host en memoria, sin Excel ni escritura SQL.

No recupera archivos de PostgreSQL: requiere rutas reales y autorizaciones
explícitas para cualquier cálculo. No certifica conciliación monetaria.
"""
from pathlib import Path
from app.services.fase2.orquestador_depo_inc56h import conciliar_depo
from app.services.fase2.cruce_depo_host_inc56h3 import cruzar


def ejecutar(ruta_depo, movimientos_host=(), *, fuente_host=None,
            clasificaciones_aprobadas=None, escala_aprobada=None,
            regla_version=None, correspondencias_aprobadas=None,
            regla_neto=None):
    """Devuelve evidencia del orquestador y un cruce separado no certificado.

    Nunca presenta diferencia diagnóstica como diferencia contable definitiva.
    """
    if not Path(ruta_depo).is_file():
        raise FileNotFoundError(ruta_depo)
    evidencia = conciliar_depo(
        ruta_depo, movimientos_host=movimientos_host,
        fuente_host=fuente_host,
        clasificaciones_aprobadas=clasificaciones_aprobadas,
        escala_aprobada=escala_aprobada, regla_version=regla_version,
    )
    cruce = cruzar(evidencia['agregados_depo'], evidencia['sumatorias_host'],
                  fuente_host=fuente_host,
                  correspondencias_aprobadas=correspondencias_aprobadas,
                  regla_neto=regla_neto)
    filas = []
    for fila in cruce['resultados']:
        filas.append({
            'tipo_insumo': 'DEPO', 'concepto': fila['concepto'],
            'cuenta': fila['cuenta'],
            'valor_franquicia': fila['valor_franquicia'],
            'debe_host': fila['debe_host'], 'haber_host': fila['haber_host'],
            'neto_host': fila['neto_host'], 'diferencia': None,
            'diferencia_diagnostica': fila['diferencia_diagnostica'],
            'estado': fila['estado'], 'lineas_origen': fila['lineas_origen'],
            'certificado_monetario': False,
        })
    return {
        'archivo_depo': evidencia['archivo_depo'],
        'fuente_host_seleccionada': fuente_host,
        'filas': filas, 'pendientes_clasificacion': evidencia['pendientes_clasificacion'],
        'diagnostico_depo': evidencia['diagnostico_depo'],
        'certificado_monetario': False,
        'estado': 'DIAGNOSTICO_NO_CERTIFICADO',
        'advertencia': 'Valores de prueba; no proyectar al Reporte Maestro como conciliados.',
    }
