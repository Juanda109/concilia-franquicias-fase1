from pathlib import Path
from tempfile import TemporaryDirectory
import pytest
from app.services.fase2.ejecucion_depo_inc56j import ejecutar


def test_sin_aprobaciones_no_inventa_importes():
    with TemporaryDirectory() as tmp:
        p=Path(tmp)/'GOF.RD001.DEPO.TXT'
        p.write_text('06' + '0'*280 + '\n', encoding='utf-8')
        r=ejecutar(p)
        assert r['certificado_monetario'] is False
        assert r['filas'] == []
        assert r['pendientes_clasificacion']


def test_fuente_host_obligatoria():
    with TemporaryDirectory() as tmp:
        p=Path(tmp)/'DEPO.TXT'
        p.write_text('06'+'0'*280+'\n', encoding='utf-8')
        with pytest.raises(ValueError, match='fuente_host'):
            ejecutar(p, movimientos_host=[{'fuente':'HA22','cuenta':'196095001838',
                    'naturaleza':'D','importe':'100','linea_origen':1}])


def test_no_archivo_falla():
    with pytest.raises(FileNotFoundError):
        ejecutar('NO_EXISTE_DEPO_INC56J.txt')
