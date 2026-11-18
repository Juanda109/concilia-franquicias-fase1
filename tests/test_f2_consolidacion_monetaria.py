from decimal import Decimal
from app.services.fase2.consolidacion_monetaria import aggregate, money
import pytest

def test_decimal():
    assert money('0.10') + money('0.20') == Decimal('0.30')

def test_null_vs_zero():
    _, totals = aggregate([{'id_archivo':1,'vl_total':None},{'id_archivo':1,'vl_total':'0'}])
    assert totals['campos']['vl_total']['nulos'] == 1
    assert totals['campos']['vl_total']['ceros'] == 1

def test_grouping():
    groups, totals = aggregate([{'id_archivo':1,'tx':'02','bin_dest':'123456','cuenta':'A','vl_total':'5'}, {'id_archivo':1,'tx':'02','bin_dest':'123456','cuenta':'A','vl_total':'7'}])
    assert len(groups)==1 and groups[0]['vl_total']==12 and totals['filas']==2

def test_no_float_nonfinite():
    with pytest.raises(ValueError): money('NaN')

def test_separate_keys():
    groups,_=aggregate([{'id_archivo':1,'tx':'02'},{'id_archivo':2,'tx':'02'}])
    assert len(groups)==2
