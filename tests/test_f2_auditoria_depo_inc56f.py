from zipfile import ZipFile
from pathlib import Path
from app.services.fase2.auditoria_formulas_depo_inc56f import auditar_plantilla, inspeccionar_depo

def test_plantilla_ligera(tmp_path):
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    def xml(cells):
        return f'<worksheet xmlns="{ns}"><sheetData><row r="2">{cells}</row></sheetData></worksheet>'
    p=tmp_path/'libro.xlsx'
    with ZipFile(p,'w') as z:
        z.writestr('xl/worksheets/sheet3.xml', f'<worksheet xmlns="{ns}"><sheetData>'+''.join(
            f'<row r="{i}"><c r="D{i}"><f>SUMIFS(H:H,F:F,"{c}",G:G,"{n}")</f></c></row>'
            for i,c,n in [(2,'196095001838','D'),(3,'196095001838','H'),(4,'196095001839','D'),(5,'196095001839','H')])+'</sheetData></worksheet>')
        for sheet in (4,5,7):z.writestr(f'xl/worksheets/sheet{sheet}.xml',xml(''))
    r=auditar_plantilla(p)
    assert len(r['formulas'])==4 and r['certificado_monetario'] is False

def test_no_certifica_importes(tmp_path):
    p=tmp_path/'depo.txt';p.write_text('05'+' '*278+'\n'+'06'+' '*278+'\n')
    r=inspeccionar_depo(p)
    assert r['tipos']=={'05':1,'06':1} and r['certificado_monetario'] is False

def test_rechaza_longitud_invalida(tmp_path):
    import pytest
    p=tmp_path/'depo.txt';p.write_text('06corto\n')
    with pytest.raises(ValueError,match='Longitud'):inspeccionar_depo(p)
