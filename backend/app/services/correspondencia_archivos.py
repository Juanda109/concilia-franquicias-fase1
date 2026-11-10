from pathlib import Path
from datetime import date, datetime
import re


class CorrespondenciaInvalida(ValueError):
    def __init__(self, codigo, mensaje):
        self.codigo = codigo
        self.mensaje = mensaje
        super().__init__(mensaje)

    def detalle(self):
        return {
            "codigo": self.codigo,
            "mensaje": self.mensaje,
            "errores": []
        }


# Patrones cuya semantica se ha identificado.
# No se utiliza una fecha fija.
PATRONES_FECHA = (
    re.compile(r"F(?P<fecha>\d{6})(?=\.|_|$)", re.I),
)


def extraer_fecha_nombre(nombre_original):
    coincidencias = []

    for patron in PATRONES_FECHA:
        for match in patron.finditer(nombre_original):
            token = match.group("fecha")

            try:
                fecha = datetime.strptime(
                    token, "%y%m%d"
                ).date()
            except ValueError as exc:
                raise CorrespondenciaInvalida(
                    "FECHA_ARCHIVO_INVALIDA",
                    "La fecha indicada en el nombre no es valida"
                ) from exc

            coincidencias.append(fecha)

    if not coincidencias:
        return None

    if len(set(coincidencias)) != 1:
        raise CorrespondenciaInvalida(
            "FECHA_ARCHIVO_AMBIGUA",
            "El nombre contiene fechas diferentes"
        )

    return coincidencias[0]



def extraer_fecha_pmd(nombre):
    patron = re.fullmatch(
        r"PMDGeneralEntidad(?P<fecha>\d{6}|\d{8})"
        r"(?:\s*\(\d+\))?\.(?:xls|xlsx)",
        nombre,
        re.I,
    )

    if not patron:
        raise CorrespondenciaInvalida(
            "NOMBRE_ARCHIVO_INVALIDO",
            "Nombre PMD no corresponde al contrato"
        )

    token = patron.group("fecha")
    formato = "%Y%m%d" if len(token) == 8 else "%y%m%d"

    try:
        return datetime.strptime(token, formato).date()
    except ValueError as exc:
        raise CorrespondenciaInvalida(
            "FECHA_ARCHIVO_INVALIDA",
            "Fecha PMD invalida"
        ) from exc




MESES_VSS = {
    "JAN": 1, "FEB": 2, "MAR": 3,
    "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9,
    "OCT": 10, "NOV": 11, "DEC": 12,
}


def extraer_fecha_mep(nombre):
    patron = re.fullmatch(
        r"ANEXO\s+0017\s+MEP_COMPENSACION\s+"
        r"(?P<fecha>\d{8})\.XLSX",
        nombre,
        re.I,
    )

    if not patron:
        raise CorrespondenciaInvalida(
            "NOMBRE_ARCHIVO_INVALIDO",
            "Nombre MEP no corresponde al contrato"
        )

    try:
        return datetime.strptime(
            patron.group("fecha"), "%d%m%Y"
        ).date()
    except ValueError as exc:
        raise CorrespondenciaInvalida(
            "FECHA_ARCHIVO_INVALIDA",
            "Fecha MEP invalida"
        ) from exc


def extraer_fecha_vss(nombre):
    patron = re.fullmatch(
        r"VSS\s+BBVA\s+"
        r"(?P<dia>\d{2})"
        r"(?P<mes>[A-Z]{3})"
        r"(?P<anio>\d{2})\.TXT",
        nombre,
        re.I,
    )

    if not patron:
        raise CorrespondenciaInvalida(
            "NOMBRE_ARCHIVO_INVALIDO",
            "Nombre VSS no corresponde al contrato"
        )

    mes = MESES_VSS.get(patron.group("mes").upper())

    if mes is None:
        raise CorrespondenciaInvalida(
            "FECHA_ARCHIVO_INVALIDA",
            "Mes VSS invalido"
        )

    anio = int(patron.group("anio"))

    try:
        return date(
            2000 + anio,
            mes,
            int(patron.group("dia")),
        )
    except ValueError as exc:
        raise CorrespondenciaInvalida(
            "FECHA_ARCHIVO_INVALIDA",
            "Fecha VSS invalida"
        ) from exc


def validar_correspondencia(
    *,
    tipo_insumo,
    nombre_original,
    fecha_contable,
):
    if not isinstance(fecha_contable, date):
        fecha_contable = date.fromisoformat(
            str(fecha_contable)
        )

    nombre = Path(nombre_original).name.upper()

    # Identidad funcional explicita para archivos Host.
    tipos_host = ("HA22", "HA26", "HA32")

    identificados = [
        tipo for tipo in tipos_host
        if tipo in nombre
    ]

    if identificados and tipo_insumo not in identificados:
        raise CorrespondenciaInvalida(
            "TIPO_ARCHIVO_INCORRECTO",
            "El archivo Host no corresponde al insumo seleccionado"
        )

    # Identidad Credibanco: CAET, CANT y DEPO.
    # Se compara el identificador funcional final del nombre.
    tipos_credibanco = ("CAET", "CANT", "DEPO")

    identificados_credibanco = [
        tipo
        for tipo in tipos_credibanco
        if nombre.endswith("." + tipo + ".TXT")
        or nombre.endswith("." + tipo)
    ]

    if identificados_credibanco:
        if tipo_insumo not in identificados_credibanco:
            raise CorrespondenciaInvalida(
                "TIPO_ARCHIVO_INCORRECTO",
                "El archivo Credibanco no corresponde al insumo seleccionado"
            )

    # CAIT no pertenece al MVP1.
    if re.search(r"(?<![A-Z])CAIT(?![A-Z])", nombre):
        raise CorrespondenciaInvalida(
            "INSUMO_FUERA_ALCANCE",
            "CAIT esta excluido del MVP1"
        )

    if tipo_insumo == "CARTA_COMPENSACION":
        patron_carta = re.fullmatch(
            r"CARTA\s+(\d{2})-(\d{2})-(\d{4})\.XLSX",
            nombre,
            re.I,
        )

        if not patron_carta:
            raise CorrespondenciaInvalida(
                "NOMBRE_ARCHIVO_INVALIDO",
                "Se espera carta DD-MM-AAAA.xlsx"
            )

        dia, mes, anio = patron_carta.groups()

        try:
            fecha_archivo = date(
                int(anio), int(mes), int(dia)
            )
        except ValueError as exc:
            raise CorrespondenciaInvalida(
                "FECHA_ARCHIVO_INVALIDA",
                "La fecha indicada en Carta no es valida"
            ) from exc

    elif tipo_insumo == "PMD":
        fecha_archivo = extraer_fecha_pmd(nombre)

    elif tipo_insumo == "MEP":
        fecha_archivo = extraer_fecha_mep(nombre)

    elif tipo_insumo == "VISA_SS_INTERNATIONAL":
        patron_ss = re.fullmatch(
            r"INTERNATIONAL\s+SS_DATA_(\d{4}-\d{2}-\d{2})(?:\(\d+\))?\.PDF",
            nombre, re.I,
        )
        if not patron_ss:
            raise CorrespondenciaInvalida(
                "NOMBRE_ARCHIVO_INVALIDO", "Nombre International SS Data no valido"
            )
        try:
            fecha_archivo = date.fromisoformat(patron_ss.group(1))
        except ValueError as exc:
            raise CorrespondenciaInvalida(
                "FECHA_ARCHIVO_INVALIDA", "Fecha International SS invalida"
            ) from exc

    elif tipo_insumo == "VSS":
        fecha_archivo = extraer_fecha_vss(nombre)

    else:
        fecha_archivo = extraer_fecha_nombre(nombre)

    if fecha_archivo is None:
        raise CorrespondenciaInvalida(
            "FECHA_ARCHIVO_NO_IDENTIFICADA",
            "No se pudo identificar la fecha contable del archivo"
        )

    if fecha_archivo != fecha_contable:
        raise CorrespondenciaInvalida(
            "FECHA_ARCHIVO_NO_CORRESPONDE",
            "La fecha del archivo no corresponde a la jornada seleccionada"
        )

    return fecha_archivo
