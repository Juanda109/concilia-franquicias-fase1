"""Inc42: correspondencias CAET/CANT por evidencia explicita; sin cruce Host."""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
import re

CUENTA = re.compile(r"^[0-9]{9,12}$")
FAMILIAS = frozenset(("principal", "comisiones", "cuenta_880"))


def _importe(valor, campo):
    if valor is None:
        return None
    try:
        n = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Importe invalido: {campo}") from exc
    if not n.is_finite():
        raise ValueError(f"Importe no finito: {campo}")
    return n


def aplicar(informe, correspondencias=()):
    """Relaciona grupos Inc41 con cuentas acreditadas; nunca infiere por texto.

    Cada correspondencia exige insumo, familia, concepto_literal, cuenta_host,
    evidencia y campo_importe. No suma familias alternativas entre si.
    """
    if informe.get('origen') != 'POSTGRESQL_SOLO_LECTURA' or informe.get('certificado') is not False:
        raise ValueError('Se requiere informe diagnostico Inc41 no certificado')
    reglas = {}
    for r in correspondencias:
        clave = (r['insumo'], r['familia'], r['concepto_literal'])
        if clave in reglas:
            raise ValueError(f'Correspondencia ambigua: {clave}')
        if r['insumo'] not in ('CAET','CANT') or r['familia'] not in FAMILIAS:
            raise ValueError('Fuente o familia no permitida')
        if not CUENTA.fullmatch(str(r['cuenta_host'])):
            raise ValueError('Cuenta Host invalida')
        if not str(r.get('evidencia') or '').strip():
            raise ValueError('Correspondencia sin evidencia')
        if r.get('campo_importe') not in ('vl_interc','vl_total','comision','tii'):
            raise ValueError('Campo monetario no acreditado')
        reglas[clave] = r
    salidas = []
    asignadas = set()
    for grupo in informe.get('resultados', []):
        if grupo.get('id_jornada') != informe.get('id_jornada') or grupo.get('franquicia') != 'CREDIBANCO':
            raise ValueError('Jornada o franquicia inconsistente')
        clave = (grupo['insumo'],grupo['familia'],grupo['concepto_literal'])
        regla = reglas.get(clave)
        campo = regla['campo_importe'] if regla else None
        importe = _importe(grupo['importes'].get(campo), campo) if regla else None
        if regla and importe is None:
            estado = 'PENDIENTE_IMPORTE_NULO'
        elif regla:
            estado = 'CUENTA_ASIGNADA_NO_CONCILIADA'
            asignadas.add(clave)
        else:
            estado = 'PENDIENTE_CORRESPONDENCIA'
        salidas.append({'id_jornada':grupo['id_jornada'], 'id_archivo':grupo['id_archivo'],
            'franquicia':'CREDIBANCO', 'insumo':grupo['insumo'], 'familia':grupo['familia'],
            'concepto':grupo['concepto_literal'], 'cuenta':str(regla['cuenta_host']) if regla else None,
            'campo_importe':campo, 'valor_franquicia':str(importe) if importe is not None else None,
            'evidencia':regla['evidencia'] if regla else None,
            'lineas_origen':grupo['lineas_origen'], 'estado':estado, 'certificado':False,
            'ha22':None,'ha26':None,'ha32':None,'total_host':None,'diferencia':None})
    faltantes = [list(k) for k in reglas if k not in {(g['insumo'],g['familia'],g['concepto_literal']) for g in informe.get('resultados',[])}]
    return {'id_jornada':informe['id_jornada'],'origen':'INC41_CON_CORRESPONDENCIAS_EXPLICITAS',
        'resultados':salidas,'correspondencias_sin_grupo':faltantes,
        'estado':'DIAGNOSTICO_NO_CERTIFICADO','certificado':False,
        'advertencias':['No se suman grupos principal/comisiones/cuenta_880: son vistas que pueden solaparse.',
            'Sin valores Host ni diferencias hasta homologar reglas de cruce.',
            'El documento de parametros tecnicos solo es referencia de cuentas, no insumo.']}
