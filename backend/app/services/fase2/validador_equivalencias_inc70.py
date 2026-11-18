"""INC70: decisiones estructurales sin atribucion monetaria."""
from collections import Counter
from copy import deepcopy


def validar(matriz, cardinalidad):
    if matriz.get('certificado') is not False or cardinalidad.get('certificado') is not False:
        raise ValueError('Entrada certificada no permitida')
    filas = matriz['matriz']
    grupos = cardinalidad['grupos']
    if len(filas) != 364 or len(grupos) != 46:
        raise ValueError('Universo INC69 inesperado')
    if matriz['id_jornada'] != cardinalidad['id_jornada'] or matriz['id_jornada'] != 6466:
        raise ValueError('Jornada incompatible')
    indices = [f['fila_excel'] for f in filas]
    if len(set(indices)) != 364:
        raise ValueError('Filas Excel duplicadas')
    if any(f.get('regla_homologada') is not False or f.get('neto_homologado') is not None for f in filas):
        raise ValueError('Importe o homologacion no autorizados')
    grupos_por_fila = {}
    decisiones_grupos = []
    for grupo in grupos:
        padre = grupo['nivel_padre']
        hijas = grupo['filas_excel']
        if len(hijas) != grupo['operaciones_hijas'] or len(hijas) != len(set(hijas)):
            raise ValueError('Cardinalidad de grupo invalida')
        if grupo.get('homologado') is not False or grupo.get('neto_homologado') is not None:
            raise ValueError('Grupo homologado sin evidencia')
        decision = 'PADRE_COMPARTIDO_NO_DISTRIBUIR' if len(hijas)>1 else 'PADRE_UNICO_PENDIENTE_HOMOLOGACION'
        for indice in hijas:
            if indice in grupos_por_fila:
                raise ValueError('Fila asignada a multiples padres')
            grupos_por_fila[indice] = (padre, decision)
        decisiones_grupos.append({'nivel_padre':padre,'operaciones_hijas':len(hijas),'filas_excel':hijas,'cuentas':grupo['cuentas'],'lineas_pmd_candidatas':grupo['lineas_pmd_candidatas'],'decision':decision,'importe_asignado':None,'certificado':False})
    decisiones = []
    for fila in filas:
        indice = fila['fila_excel']
        padre, decision = grupos_por_fila.get(indice, (None, 'SIN_EQUIVALENCIA'))
        if padre is None and fila['tipo_candidato'] != 'SIN_CANDIDATO_JERARQUICO':
            raise ValueError('Fila con candidato no agrupada')
        if padre is not None and fila['tipo_candidato'] == 'SIN_CANDIDATO_JERARQUICO':
            raise ValueError('Fila sin candidato agrupada')
        decisiones.append({'fila_excel':indice,'cuenta_contable':fila['cuenta_contable'],'codigo_operacion':fila['codigo_operacion'],'categoria':fila.get('categoria'),'nivel_padre':padre,'lineas_pmd_candidatas':fila.get('lineas_pmd_candidatas',[]),'decision':decision,'neto_homologado':None,'certificado':False})
    conteos = Counter(x['decision'] for x in decisiones)
    esperado = {'PADRE_COMPARTIDO_NO_DISTRIBUIR':350,'PADRE_UNICO_PENDIENTE_HOMOLOGACION':6,'SIN_EQUIVALENCIA':8}
    if dict(conteos) != esperado or len(grupos_por_fila)!=356:
        raise ValueError(f'Inconsistencia en distribucion: {conteos}')
    return {'id_jornada':6466,'total':364,'conteos':dict(conteos),'grupos':decisiones_grupos,'decisiones':decisiones,'certificado':False,'advertencia':'No se atribuyen importes ni se aprueban equivalencias monetarias.'}
