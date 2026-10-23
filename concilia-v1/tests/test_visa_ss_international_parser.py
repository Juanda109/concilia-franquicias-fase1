from datetime import date
from decimal import Decimal
from pathlib import Path
import os
import pytest
from app.parsers.visa_ss_international import VisaSSInternationalParser
from app.services.correspondencia_archivos import validar_correspondencia, CorrespondenciaInvalida

def test_pdf_real():
    sample=os.getenv('VISA_SS_SAMPLE')
    if not sample: pytest.skip('VISA_SS_SAMPLE no configurado')
    resultado=VisaSSInternationalParser().parse(Path(sample))
    assert not resultado.errors,resultado.errors
    assert len(resultado.records)==3
    assert [r['FTSRE'] for r in resultado.records]==['1000804671','9000737875','9000817304']
    assert all(r['FECHA_PROCESAMIENTO']==date(2026,7,3) for r in resultado.records)
    assert sum((r['IMPORTE_NETO'] for r in resultado.records if r['TIPO_MOVIMIENTO']=='CR'),Decimal('0'))==Decimal('363512.54')
    assert sum((r['IMPORTE_NETO'] for r in resultado.records if r['TIPO_MOVIMIENTO']=='DB'),Decimal('0'))==Decimal('1607760.57')

def test_fecha_nombre():
    assert validar_correspondencia(tipo_insumo='VISA_SS_INTERNATIONAL',nombre_original='International  SS_Data_2026-07-03(1).pdf',fecha_contable=date(2026,7,3))==date(2026,7,3)
    with pytest.raises(CorrespondenciaInvalida):
        validar_correspondencia(tipo_insumo='VISA_SS_INTERNATIONAL',nombre_original='International  SS_Data_2026-07-03(1).pdf',fecha_contable=date(2026,10,21))
