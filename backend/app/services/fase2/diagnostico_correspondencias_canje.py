"""Diagnostico F2-27: evidencia documental, sin aprobacion automatica."""
import argparse
import json
from pathlib import Path

EXPECTED_IDS = {f'F2-016-{i:02d}' for i in range(1, 8)}
REQUIRED = ('centro_host', 'campo_host', 'campo_franquicia', 'factor_signo', 'tolerancia')


def analizar(propuesta, evidencias):
    if propuesta.get('fase') != 2 or evidencias.get('fase') != 2:
        raise ValueError('Fase incorrecta')
    if propuesta.get('tipo') != 'MATRIZ_PROPUESTA' or evidencias.get('tipo') != 'MATRIZ_EVIDENCIAS_NO_OPERATIVA':
        raise ValueError('Tipo de matriz incorrecto')
    p = propuesta.get('reglas')
    e = evidencias.get('reglas')
    if not isinstance(p, list) or not isinstance(e, list):
        raise ValueError('Reglas invalidas')
    if len(p) != 7 or len(e) != 7:
        raise ValueError('Se requieren siete reglas por matriz')
    for rows in (p, e):
        ids = [r.get('id_regla') for r in rows]
        if len(set(ids)) != 7 or set(ids) != EXPECTED_IDS:
            raise ValueError('Identificadores duplicados o diferentes de linea base')
    por_id = {r['id_regla']: r for r in e}
    salida = []
    for r in sorted(p, key=lambda x: x['id_regla']):
        ev = por_id[r['id_regla']]
        for campo in ('tipo_insumo', 'tx', 'tipo', 'cuenta_franquicia'):
            if r.get(campo) != ev.get(campo):
                raise ValueError(f'Inconsistencia documental {r["id_regla"]}: {campo}')
        if r.get('habilitada') is not False or ev.get('habilitada') is not False:
            raise ValueError('Regla habilitada sin autorizacion')
        if r.get('estado_regla') != 'PENDIENTE_VALIDACION' or ev.get('estado_regla') != 'PENDIENTE_VALIDACION':
            raise ValueError('Estado no permitido')
        faltantes = list(ev.get('pendientes') or [])
        for campo in REQUIRED:
            if ev.get(campo) is None and campo not in faltantes:
                faltantes.append(campo)
        if not ev.get('cuenta_host_candidata'):
            faltantes.append('Cuenta Host homologada')
        if not ev.get('fuente_host_candidata'):
            faltantes.append('Fuente Host homologada')
        if not ev.get('evidencias'):
            faltantes.append('Evidencia documental')
        salida.append({
            'id_regla': r['id_regla'], 'insumo': r['tipo_insumo'],
            'tx': r['tx'], 'tipo': r['tipo'], 'cuenta_franquicia': r['cuenta_franquicia'],
            'cuenta_host_candidata': ev.get('cuenta_host_candidata'),
            'fuentes_host_candidatas': ev.get('fuente_host_candidata') or [],
            'evidencias': ev.get('evidencias') or [],
            'campos_pendientes': dict((c, ev.get(c)) for c in REQUIRED),
            'faltantes': list(dict.fromkeys(faltantes)),
            'estado': 'CANDIDATA_DOCUMENTAL_NO_HOMOLOGADA' if ev.get('cuenta_host_candidata') else 'SIN_CORRESPONDENCIA_HOST_ACREDITADA',
            'habilitada': False, 'certificable': False,
        })
    return {
        'estado': 'DIAGNOSTICO_CORRESPONDENCIAS_NO_CERTIFICADO',
        'total_reglas': 7,
        'candidatas_documentales': sum(bool(x['cuenta_host_candidata']) for x in salida),
        'reglas_aprobadas': 0, 'cruces_certificados': 0,
        'advertencias': ['La evidencia documental no homologa una cuenta Host.',
                         'Jornada 1377 tiene Host sintetico/no verificado; no sirve para certificacion.',
                         'No se calcula conciliacion monetaria ni se modifican matrices.'],
        'reglas': salida,
    }


def ejecutar(ruta_propuesta, ruta_evidencias, salida):
    destino = Path(salida)
    if destino.exists():
        raise FileExistsError('La carpeta de salida ya existe; no sobrescribir')
    propuesta = json.loads(Path(ruta_propuesta).read_text(encoding='utf-8-sig'))
    evidencias = json.loads(Path(ruta_evidencias).read_text(encoding='utf-8-sig'))
    informe = analizar(propuesta, evidencias)
    destino.mkdir(parents=True, exist_ok=False)
    (destino / 'informe.json').write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding='utf-8')
    return informe


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--propuesta', required=True)
    parser.add_argument('--evidencias', required=True)
    parser.add_argument('--salida', required=True)
    a = parser.parse_args()
    print(json.dumps(ejecutar(a.propuesta, a.evidencias, a.salida), ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
