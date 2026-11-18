import pytest

from app.parsers.caet import CAETParser
from app.parsers.cant import CANTParser


@pytest.mark.parametrize(
    "parser_class",
    [CAETParser, CANTParser]
)
def test_registro_longitud_invalida(
    tmp_path, parser_class
):
    archivo = tmp_path / "registro_corto.txt"
    archivo.write_text("02" + " " * 100, encoding="utf-8")

    resultado = parser_class().parse(archivo)

    assert len(resultado.records) == 0
    assert len(resultado.errors) == 1
    assert resultado.errors[0].codigo == "LONGITUD_INVALIDA"
    assert resultado.errors[0].linea == 1


@pytest.mark.parametrize(
    "parser_class",
    [CAETParser, CANTParser]
)
def test_archivo_vacio(
    tmp_path, parser_class
):
    archivo = tmp_path / "archivo_vacio.txt"
    archivo.write_text("", encoding="utf-8")

    resultado = parser_class().parse(archivo)

    assert len(resultado.records) == 0
    assert len(resultado.errors) == 0
    assert any(
        control["codigo"] == "TOTAL_REGISTROS"
        and control["obtenido"] == 0
        for control in resultado.controls
    )


def construir_registro(**campos):
    from app.parsers.caet import FIELDS

    longitud = max(
        inicio + ancho - 1
        for _, inicio, ancho in FIELDS
    )

    caracteres = [" "] * longitud

    for nombre, inicio, ancho in FIELDS:
        valor = str(campos.get(nombre, ""))

        if len(valor) > ancho:
            raise ValueError(
                f"Campo {nombre} supera longitud {ancho}"
            )

        caracteres[
            inicio - 1:inicio - 1 + ancho
        ] = list(valor.ljust(ancho))

    return "".join(caracteres)


@pytest.mark.parametrize(
    "parser_class",
    [CAETParser, CANTParser]
)
def test_parse_registro_debito_valido(
    tmp_path, monkeypatch, parser_class
):
    from app.parsers import caet, cant

    modulo = (
        caet if parser_class is CAETParser else cant
    )

    monkeypatch.setattr(
        modulo,
        "cargar_bines_activos",
        lambda: {123456: "DEBITO"}
    )

    registro = construir_registro(
        TX="02",
        BIN_DEST="123456",
        TARJETA="0001234560000000000",
        VL_TOTAL="000010000",
        VL_INTERC_RAW="000000500",
        COD_ERROR="00",
        MOT_COB="00",
        XX="99"
    )

    archivo = tmp_path / "registro_valido.txt"
    archivo.write_text(registro + "\n", encoding="utf-8")

    resultado = parser_class().parse(archivo)

    assert len(resultado.errors) == 0
    assert len(resultado.records) == 1

    fila = resultado.records[0]

    assert fila["TX"] == "02"
    assert fila["BIN_DEST"] == "123456"
    assert fila["TIPO"] == "DEBITO"
    assert fila["ESPACIOS"] == "ELECTRONICO"
    assert fila["VL_INTERC"] == 500
    assert fila["COMISION_OP_EXITOSAS"] == 7450
    assert fila["CUENTA"] == (
        "017-CANJE RECIBIDO TARJETA DEBITO"
    )

    assert any(
        control["codigo"] == "TOTAL_REGISTROS"
        and control["obtenido"] == 1
        for control in resultado.controls
    )


@pytest.mark.parametrize(
    "parser_class",
    [CAETParser, CANTParser]
)
def test_parse_registro_descartado(
    tmp_path, monkeypatch, parser_class
):
    from app.parsers import caet, cant

    modulo = (
        caet if parser_class is CAETParser else cant
    )

    monkeypatch.setattr(
        modulo,
        "cargar_bines_activos",
        lambda: {123456: "DEBITO"}
    )

    registro = construir_registro(
        TX="06",
        BIN_DEST="123456",
        TARJETA="0001234560000000000",
        VL_TOTAL="000010000",
        VL_INTERC_RAW="000000500",
        COD_ERROR="99",
        MOT_COB="00",
        XX="99"
    )

    archivo = tmp_path / "registro_descartado.txt"
    archivo.write_text(registro + "\n", encoding="utf-8")

    resultado = parser_class().parse(archivo)

    assert len(resultado.errors) == 0
    assert len(resultado.records) == 0

    assert any(
        control["codigo"] == "TOTAL_REGISTROS"
        and control["obtenido"] == 0
        for control in resultado.controls
    )


@pytest.mark.parametrize(
    "parser_class",
    [CAETParser, CANTParser]
)
def test_parse_archivo_mixto(
    tmp_path, monkeypatch, parser_class
):
    from app.parsers import caet, cant

    modulo = caet if parser_class is CAETParser else cant

    monkeypatch.setattr(
        modulo,
        "cargar_bines_activos",
        lambda: {123456: "DEBITO"}
    )

    valido = construir_registro(
        TX="02",
        BIN_DEST="123456",
        TARJETA="0001234560000000000",
        VL_TOTAL="000010000",
        VL_INTERC_RAW="000000500",
        COD_ERROR="00",
        MOT_COB="00",
        XX="99"
    )

    descartado = construir_registro(
        TX="06",
        BIN_DEST="123456",
        TARJETA="0001234560000000000",
        VL_TOTAL="000010000",
        VL_INTERC_RAW="000000500",
        COD_ERROR="99",
        MOT_COB="00",
        XX="99"
    )

    invalido = "02" + " " * 100

    archivo = tmp_path / "archivo_mixto.txt"
    archivo.write_text(
        valido + "\n" +
        descartado + "\n" +
        invalido + "\n",
        encoding="utf-8"
    )

    resultado = parser_class().parse(archivo)

    assert len(resultado.records) == 1
    assert len(resultado.errors) == 1

    assert resultado.records[0]["numero_linea"] == 1
    assert resultado.errors[0].linea == 3
    assert resultado.errors[0].codigo == "LONGITUD_INVALIDA"

    assert any(
        control["codigo"] == "TOTAL_REGISTROS"
        and control["obtenido"] == 1
        for control in resultado.controls
    )


@pytest.mark.parametrize(
    "parser_class",
    [CAETParser, CANTParser]
)
def test_controles_descartes_y_errores(
    tmp_path, monkeypatch, parser_class
):
    from app.parsers import caet, cant

    modulo = caet if parser_class is CAETParser else cant

    monkeypatch.setattr(
        modulo,
        "cargar_bines_activos",
        lambda: {123456: "DEBITO"}
    )

    def registro(tx, codigo_error, bin_dest="123456"):
        return construir_registro(
            TX=tx,
            BIN_DEST=bin_dest,
            TARJETA="0001234560000000000",
            VL_TOTAL="000010000",
            VL_INTERC_RAW="000000500",
            COD_ERROR=codigo_error,
            MOT_COB="00",
            XX="99"
        )

    lineas = [
        registro("02", "00"),
        registro("06", "99"),
        registro("08", "99"),
        registro("02", "99", "439467"),
        "02" + " " * 100,
    ]

    archivo = tmp_path / "controles.txt"
    archivo.write_text(
        "\n".join(lineas) + "\n",
        encoding="utf-8"
    )

    resultado = parser_class().parse(archivo)

    controles = {
        control["codigo"]: control["obtenido"]
        for control in resultado.controls
    }

    assert controles["TOTAL_REGISTROS"] == len(resultado.records)

    assert controles["TOTAL_REGISTROS"] == 1

    assert controles["DESCARTADOS_COD_ERROR_NO_APLICABLE"] == 3

    assert len(resultado.errors) == 1
    assert resultado.errors[0].codigo == "LONGITUD_INVALIDA"
    assert resultado.errors[0].linea == 5

    assert (
        controles["TOTAL_REGISTROS"]
        + controles["DESCARTADOS_COD_ERROR_NO_APLICABLE"]
        + len(resultado.errors)
    ) == 5
