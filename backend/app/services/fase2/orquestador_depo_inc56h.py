"""INC56-H1: orquestacion DEPO sin Excel, sin SQL y sin homologacion inventada."""
from decimal import Decimal, InvalidOperation
from pathlib import Path
from app.services.fase2.diagnostico_depo_inc56b import analizar, campo, CAMPOS, TIPOS_PERSISTIDOS
from app.services.fase2.reglas_depo_inc56c import evaluar as evaluar_regla
from app.services.fase2.motor_monetario_depo_inc56g import agregar
from app.services.fase2.conciliacion_depo_inc56e import sumar_contabilidad
from app.services.fase2.clasificacion_depo_inc56h2 import construir_clasificados


def _decimal(valor):
    if isinstance(valor, (bool, float)):
        raise ValueError('Importe debe ser Decimal o texto')
    try:
        n = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError('Importe invalido') from exc
    if not n.is_finite():
        raise ValueError('Importe no finito')
    return n


def _extraer(linea, numero):
    """Extrae campos solo donde INC56-B tiene posiciones documentadas."""
    tipo = campo(linea, *CAMPOS['tipo'])
    datos = {'TIPO_MOVIMIENTO': tipo, 'numero_linea': numero,
             'BIN_FUENTE': campo(linea, *CAMPOS['bin_fuente']),
             'BIN_DESTINO': campo(linea, *CAMPOS['bin_destino']),
             'INDICADOR_CNB_CRUDO': campo(linea, *CAMPOS['indicador_cnb'])}
    for nombre, clave in [('VALOR_TOTAL_CRUDO','valor_total'),
                          ('VALOR_INTERCAMBIO_CRUDO','valor_intercambio'),
                          ('VALOR_INTERCAMBIO_2_CRUDO','valor_intercambio_2')]:
        raw = campo(linea, *CAMPOS[clave])
        datos[nombre] = raw if raw.isdigit() else None
    # No inferir AMEX, cuenta, concepto o escala desde el BIN.
    if tipo in TIPOS_PERSISTIDOS and all(datos[x] is not None for x in
        ('VALOR_TOTAL_CRUDO','VALOR_INTERCAMBIO_2_CRUDO')):
        tasa = int(datos['VALOR_TOTAL_CRUDO']) - int(datos['VALOR_INTERCAMBIO_2_CRUDO'])
        datos['TASA_DE_INTERCAMBIO'] = str(-tasa if tipo == '26' else tasa)
    else:
        datos['TASA_DE_INTERCAMBIO'] = None
    return datos


def conciliar_depo(ruta_depo, movimientos_host=(), movimientos_clasificados=(), *,
                   escala_aprobada=None, regla_version=None, fuente_host=None,
                   clasificaciones_aprobadas=None):
    """Devuelve evidencia; no convierte registros crudos en conceptos no aprobados."""
    diagnostico = analizar(ruta_depo)
    reglas, extraidos, pendientes_clasificacion = [], [], []
    archivo = Path(ruta_depo)
    for numero, linea in enumerate(archivo.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
        if not linea.strip():
            continue
        datos = _extraer(linea, numero)
        extraidos.append(datos)
        # El indicador crudo no se convierte automaticamente en CNB validado.
        evaluacion = evaluar_regla(datos)
        reglas.append(evaluacion)
        if datos['TIPO_MOVIMIENTO'] in TIPOS_PERSISTIDOS:
            pendientes_clasificacion.append({'archivo_origen': archivo.name,
                'linea_origen': numero, 'motivo': 'CONCEPTO_Y_CLASIFICACION_NO_HOMOLOGADOS',
                'tipo_movimiento': datos['TIPO_MOVIMIENTO']})
    auto, pendientes_h2 = construir_clasificados(
        archivo.name, extraidos, clasificaciones_aprobadas or {})
    if auto and movimientos_clasificados:
        raise ValueError("No combinar clasificaciones automaticas y externas")
    host = list(movimientos_host)
    fuentes = sorted({str(x.get('fuente')) for x in host})
    if host and (not fuente_host or fuente_host not in fuentes):
        raise ValueError('Seleccionar fuente_host presente para impedir duplicacion')
    contables = [{'cuenta':str(x['cuenta']), 'naturaleza':str(x['naturaleza']),
                  'importe':_decimal(x['importe']), 'linea_origen':x.get('linea_origen')}
                 for x in host if x.get('fuente') == fuente_host]
    sumifs = sumar_contabilidad(contables) if fuente_host else []
    # La entrada externa sigue siendo opcional: nunca se fabrica una clasificacion aprobada.
    agregados = agregar(auto if auto else movimientos_clasificados, escala_aprobada=escala_aprobada,
                       regla_version=regla_version)
    return {'incremento':'INC56-H1', 'archivo_depo':archivo.name,
            'fuente_host_seleccionada':fuente_host, 'fuentes_host_disponibles':fuentes,
            'diagnostico_depo':diagnostico, 'campos_depo_extraidos':extraidos,
            'reglas_diagnosticas':reglas, 'pendientes_clasificacion':pendientes_h2 if clasificaciones_aprobadas is not None else pendientes_clasificacion,
            'sumatorias_host':sumifs, 'agregados_depo':agregados,
            'conceptos_conciliados':[], 'valor_franquicia':None, 'neto':None,
            'diferencia':None, 'certificado_monetario':False,
            'estado':'PENDIENTE_HOMOLOGACION_ESCALA_Y_CORRESPONDENCIA',
            'advertencia':'No hay cruce DEPO-Host certificado; valores Host son evidencia separada.'}
