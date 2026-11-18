from app.services.fase2.puente_pmd_general_inc70 import verificar_pmd_general
from app.services.fase2.motor_desagregacion_redeban import MEDIDAS


def test_pmd_general_coincide():
    medidas = {m: '0.0000' for m in MEDIDAS}
    cruce = {'id_jornada': 6466, 'certificado': False, 'grupos': [
        {'padre': '1.2', 'operaciones': 1, 'registros_pmd_reales': [
            {'id_archivo': 5728, 'linea_pmd': 5, 'medidas': medidas}]}]}
    matriz = {'id_jornada': 6466, 'certificado': False}
    filas = [{'NIVEL': '1.2', 'id_archivo': 5728, 'numero_linea': 5, **medidas}]
    r = verificar_pmd_general(cruce, matriz, filas)
    assert r['resumen'] == {'PMD_VERIFICADO_SIN_DESGLOSE': 1}
    assert r['certificado'] is False
    filas[0]['DEBITO_VALOR'] = '1'
    assert verificar_pmd_general(cruce, matriz, filas)['resumen'] == {'IMPORTE_DIFERENTE': 1}


def test_no_infiere_homologacion():
    r = verificar_pmd_general({'id_jornada': 6466, 'certificado': False, 'grupos': [
        {'padre': 'X', 'operaciones': 2, 'registros_pmd_reales': []}]},
        {'id_jornada': 6466, 'certificado': False}, [])
    assert r['grupos'][0]['homologado'] is False
