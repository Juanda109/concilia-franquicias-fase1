from app.core.nombres_archivo import formato_esperado, validar_nombre


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
