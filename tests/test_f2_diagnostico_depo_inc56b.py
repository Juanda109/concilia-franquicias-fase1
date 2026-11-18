import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from app.services.fase2.diagnostico_depo_inc56b import analizar, campo

class Pruebas(unittest.TestCase):
    def test_corte_posicional(self): self.assertEqual(campo('06ABC',1,2),'06')
    def test_registro_control_no_suma(self):
        with TemporaryDirectory() as t:
            f=Path(t)/'depo.txt'; f.write_text('05'+'0'*278+'\n'+'06'+'0'*278+'\n')
            r=analizar(f)
            self.assertEqual(r['registros_control_05'],1)
            self.assertEqual(r['movimientos'],1)
            self.assertEqual(r['sumas_crudas_por_tipo']['06']['cantidad'],1)
    def test_tipo_no_aprobado(self):
        with TemporaryDirectory() as t:
            f=Path(t)/'depo.txt'; f.write_text('99'+'0'*278)
            self.assertEqual(analizar(f)['movimientos'],0)

if __name__=='__main__': unittest.main()


def test_agrupar_depo_preserva_valor_intercambio():
    from app.services.fase2.cierre_credibanco_v67 import agrupar_depo
    filas = [{
        'id_archivo': 9, 'tipo_movimiento': '02', 'cuenta': '017-VR. DEPOSITOS ELECTRONICOS NAL CONSIGNADOS',
        'valor_total_crudo': '100.00', 'valor_intercambio_crudo': '70.00',
        'valor_intercambio_2_crudo': '65.00', 'tasa_intercambio_cruda': '30.00',
        'valores_invalidos': 0, 'nulos_valor_intercambio': 0, 'nulos_tasa': 0,
        'cantidad': 1, 'cod_oficina': '001', 'indicador_cash_back': '', 'amex_nacional': 'N',
    }]
    out = agrupar_depo(filas, {9})
    assert out[0]['valor_total_crudo'] == '100.00'
    assert out[0]['valor_intercambio_crudo'] == '70.00'
    assert out[0]['valor_intercambio_2_crudo'] == '65.00'
    assert out[0]['tasa_intercambio_cruda'] == '30.00'
