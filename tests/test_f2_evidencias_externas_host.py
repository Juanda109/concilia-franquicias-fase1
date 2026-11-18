import hashlib
from app.services.fase2.evidencias_externas_host import validar_evidencia, sha256_archivo


def datos(ruta):
    return {'tipo_insumo': 'HA22', 'nombre_archivo': ruta.name, 'sha256': sha256_archivo(ruta),
            'fecha_contable': '2026-10-21', 'id_archivo': 1136,
            'fuente_emisora': 'HOST', 'id_autorizacion': 'A1',
            'identidad_contrastada_externamente': True}


def test_sin_archivo(tmp_path):
    assert 'ARCHIVO_NO_ENCONTRADO' in validar_evidencia(tmp_path/'nada', {})['motivos']


def test_sin_evidencia(tmp_path):
    p=tmp_path/'HA22.txt'; p.write_text('x')
    assert 'EVIDENCIA_AUSENTE' in validar_evidencia(p,None)['motivos']


def test_hash_incorrecto(tmp_path):
    p=tmp_path/'HA22.txt'; p.write_text('x'); e=datos(p); e['sha256']='0'*64
    assert 'INTEGRIDAD_NO_ACREDITADA' in validar_evidencia(p,e)['motivos']


def test_identidad_incorrecta(tmp_path):
    p=tmp_path/'HA22.txt'; p.write_text('x'); e=datos(p); e['nombre_archivo']='otro'
    assert 'IDENTIDAD_ARCHIVO_NO_COINCIDE' in validar_evidencia(p,e)['motivos']


def test_fecha_invalida(tmp_path):
    p=tmp_path/'HA22.txt'; p.write_text('x'); e=datos(p); e['fecha_contable']='2026-99-99'
    assert 'FECHA_INVALIDA' in validar_evidencia(p,e)['motivos']


def test_sin_autorizacion_externa(tmp_path):
    p=tmp_path/'HA22.txt'; p.write_text('x'); e=datos(p)
    assert 'AUTORIZACION_EXTERNA_NO_ACREDITADA' in validar_evidencia(p,e)['motivos']


def test_hash_y_autorizacion_no_certifican(tmp_path):
    p=tmp_path/'HA22.txt'; p.write_text('x'); e=datos(p)
    r=validar_evidencia(p,e,fuentes_acreditadas={'HOST':{'A1'}})
    assert r['estado']=='ORIGEN_NO_VERIFICADO'
    assert 'REQUIERE_VERIFICACION_INDEPENDIENTE_DE_EVIDENCIA' in r['motivos']


def test_no_se_modifica_archivo(tmp_path):
    p=tmp_path/'HA32.txt'; p.write_bytes(b'original'); antes=p.read_bytes()
    validar_evidencia(p,{})
    assert p.read_bytes()==antes
