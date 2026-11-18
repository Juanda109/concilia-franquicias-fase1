from pathlib import Path

def test_adaptador_v67_expone_intercambio_2():
    ruta = (
        Path(__file__).resolve().parents[1]
        / "backend"
        / "app"
        / "services"
        / "fase2"
        / "cierre_credibanco_pg_v67.py"
    )

    codigo = ruta.read_text(encoding="utf-8-sig")

    inicio = codigo.index("if d_ids:")
    fin = codigo.index("if carta_ids:", inicio)
    sql_depo = codigo[inicio:fin]

    assert "AS valor_intercambio_2_crudo" in sql_depo
    assert "AS nulos_valor_intercambio_2" in sql_depo
    assert "d.valor_intercambio_2" in sql_depo
