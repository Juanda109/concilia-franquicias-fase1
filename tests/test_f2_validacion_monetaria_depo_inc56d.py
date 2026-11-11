from pathlib import Path
from app.services.fase2.validacion_monetaria_depo_inc56d import campo, verificar_archivo

def test_campo_posicional():
    assert campo("0123456789", 3, 4) == "2345"

def test_no_certifica(tmp_path):
    f=tmp_path/"DEPO.TXT"
    f.write_text("06"+"0"*278+"\n05"+"0"*278+"\n", encoding="ascii")
    r=verificar_archivo(f)
    assert r["registros"]==2 and r["tipos_registro"]=={"05":1,"06":1}
    assert r["certificado_monetario"] is False
    assert not r["problemas"]

def test_longitud_anomala(tmp_path):
    f=tmp_path/"DEPO.TXT";f.write_text("06CORTO\n")
    assert verificar_archivo(f)["problemas"][0]["problema"]=="LONGITUD_DISTINTA_280"
