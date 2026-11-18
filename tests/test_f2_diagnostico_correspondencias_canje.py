import copy
import json
from pathlib import Path
import pytest
from app.services.fase2.diagnostico_correspondencias_canje import analizar, ejecutar


def matrices():
    p = {'fase': 2, 'tipo': 'MATRIZ_PROPUESTA', 'reglas': []}
    e = {'fase': 2, 'tipo': 'MATRIZ_EVIDENCIAS_NO_OPERATIVA', 'reglas': []}
    for i in range(1, 8):
        base = {'id_regla': f'F2-016-{i:02d}', 'tipo_insumo': 'CAET' if i == 1 else 'CANT',
                'tx': '36', 'tipo': 'CREDITO', 'cuenta_franquicia': f'017-CUENTA-{i}',
                'habilitada': False, 'estado_regla': 'PENDIENTE_VALIDACION'}
        p['reglas'].append(dict(base))
        e['reglas'].append(dict(base, cuenta_host_candidata='299095302' if i in (2,5,6) else None,
                                fuente_host_candidata=['HA22'] if i in (2,5,6) else [],
                                evidencias=[{'documento':'fuente'}] if i in (2,5,6) else [],
                                pendientes=['Homologacion'], centro_host=None, campo_host=None,
                                campo_franquicia=None, factor_signo=None, tolerancia=None))
    return p, e


def test_siete_pendientes():
    result = analizar(*matrices())
    assert result['total_reglas'] == 7 and result['reglas_aprobadas'] == 0
    assert all(not x['certificable'] for x in result['reglas'])


def test_candidatas_no_aprobadas():
    result = analizar(*matrices())
    assert result['candidatas_documentales'] == 3
    assert sum(x['estado'] == 'CANDIDATA_DOCUMENTAL_NO_HOMOLOGADA' for x in result['reglas']) == 3


def test_inconsistencia_bloqueada():
    p, e = matrices(); e['reglas'][0]['tx'] = '99'
    with pytest.raises(ValueError): analizar(p, e)


def test_activacion_bloqueada():
    p, e = matrices(); p['reglas'][0]['habilitada'] = True
    with pytest.raises(ValueError): analizar(p, e)


def test_ids_duplicados_bloqueados():
    p, e = matrices(); e['reglas'][1]['id_regla'] = e['reglas'][0]['id_regla']
    with pytest.raises(ValueError): analizar(p, e)


def test_salida_no_sobrescribe(tmp_path):
    p, e = matrices()
    a = tmp_path/'p.json'; b = tmp_path/'e.json'; d = tmp_path/'out'
    a.write_text(json.dumps(p)); b.write_text(json.dumps(e))
    ejecutar(a, b, d)
    with pytest.raises(FileExistsError): ejecutar(a, b, d)


def test_sin_matriz_completa():
    p, e = matrices(); e['reglas'].pop()
    with pytest.raises(ValueError): analizar(p, e)
