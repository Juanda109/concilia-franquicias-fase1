from app.core.nombres_archivo import fecha_esperada_archivo, formato_esperado, validar_nombre


def test_vss_formato_nuevo_ddmmmaa_trae_fecha_completa():
    assert validar_nombre("VSS", "VSS BBVA 10NOV26.txt", "2026-11-10") == (True, True, "2026-11-10")
    # el año del nombre manda, no el de la jornada
    assert validar_nombre("VSS", "VSS BBVA 10NOV25.TXT", "2026-11-10") == (True, True, "2025-11-10")
    assert validar_nombre("VSS", "VSS BBVA 05DIC26.txt", "2026-12-05")[2] == "2026-12-05"
    assert validar_nombre("VSS", "VSS BBVA 05DEC26.txt", "2026-12-05")[2] == "2026-12-05"
    assert validar_nombre("VSS", "VSS BBVA 05ENE27.txt", "2027-01-05")[2] == "2027-01-05"


def test_vss_formato_anterior_sigue_valido():
    assert validar_nombre("VSS", "VSS BBVA 02 JULIO.txt", "2026-07-02") == (True, True, "2026-07-02")
    assert validar_nombre("VSS", "VSS BBVA 10 NOVIEMBRE.TXT", "2026-11-10") == (True, True, "2026-11-10")


def test_vss_nombres_invalidos():
    for nombre in ["VSS BBVA 10XYZ26.txt", "VSS BBVA 31NOV26.txt", "VSS BBVA 10 NOV.txt", "VSS 10NOV26.txt",
                   "VSS BBVA 10NOV2026.txt"]:
        assert validar_nombre("VSS", nombre, "2026-11-10") == (True, False, None), nombre


def test_formato_esperado():
    texto = formato_esperado("VSS")
    assert "VSS BBVA DDMMMAA.txt" in texto and "VSS BBVA 10 NOVIEMBRE.txt" in texto
    assert "DESCARHA22_FAAMMDD.TXT" in formato_esperado("HA22")
    assert formato_esperado("MEP") is None


def test_iss_acepta_uno_o_dos_espacios():
    for nombre in ["International SS_Data_2026-11-10.pdf", "International  SS_Data_2026-11-10.pdf"]:
        assert validar_nombre("ISS", nombre, "2026-11-10") == (True, True, "2026-11-10"), nombre
    assert validar_nombre("ISS", "InternationalSS_Data_2026-11-10.pdf")[1] is False


def test_tipos_sin_regla_no_validan():
    assert validar_nombre("MEP", "cualquier cosa.xls") == (False, True, None)


def test_pmd_y_vss_esperan_el_dia_anterior():
    assert fecha_esperada_archivo("PMD", "2026-11-11") == "2026-11-10"
    assert fecha_esperada_archivo("VSS", "2026-11-11") == "2026-11-10"
    # cambio de mes y de año
    assert fecha_esperada_archivo("PMD", "2026-12-01") == "2026-11-30"
    assert fecha_esperada_archivo("VSS", "2027-01-01") == "2026-12-31"
    # el resto de insumos sigue con la fecha de la jornada
    for tipo in ["HA22", "HA26", "HA32", "CAET", "CANT", "DEPO", "CARTA_COMPENSACION", "ISS", "MEP"]:
        assert fecha_esperada_archivo(tipo, "2026-11-11") == "2026-11-11"


def test_vss_sin_anio_toma_el_anio_de_la_fecha_esperada():
    # jornada 1/1/2027 -> se espera el VSS del 31/12/2026
    esperada = fecha_esperada_archivo("VSS", "2027-01-01")
    assert validar_nombre("VSS", "VSS BBVA 31 DICIEMBRE.txt", esperada) == (True, True, "2026-12-31")


def test_vss_dia_de_un_digito():
    assert validar_nombre("VSS", "VSS BBVA 9 NOVIEMBRE.txt", "2026-11-09") == (True, True, "2026-11-09")
    assert validar_nombre("VSS", "VSS BBVA 09 NOVIEMBRE.txt", "2026-11-09") == (True, True, "2026-11-09")
    assert validar_nombre("VSS", "VSS BBVA 9NOV26.txt", "2026-11-09") == (True, True, "2026-11-09")
    assert validar_nombre("VSS", "VSS BBVA 09NOV26.txt", "2026-11-09") == (True, True, "2026-11-09")
