
import json
from decimal import Decimal
from pathlib import Path

FUENTES = {"HA22", "HA26", "HA32"}
INSUMOS = {"CAET", "CANT"}
CAMPOS_HOST = {
    "valor_debe", "valor_haber",
    "valor_normalizado", "valor_saldo"
}
CAMPOS_FRANQUICIA = {
    "vl_total", "vl_interc",
    "comision_op_exitosas",
    "tii_recibida_emisor_visa_op_rever_ventas"
}

def validar_matriz(ruta):
    datos = json.loads(
        Path(ruta).read_text(encoding="utf-8")
    )

    if datos.get("fase") != 2:
        raise ValueError("Fase incorrecta")

    reglas = datos.get("reglas")

    if not isinstance(reglas, list):
        raise ValueError("Reglas invalidas")

    identificadores = set()

    for regla in reglas:
        identificador = regla["id_regla"]

        if identificador in identificadores:
            raise ValueError("Regla duplicada")

        identificadores.add(identificador)

        if regla["fuente_host"] not in FUENTES:
            raise ValueError("Fuente Host invalida")

        if regla["tipo_insumo"] not in INSUMOS:
            raise ValueError("Insumo invalido")

        if regla["campo_host"] not in CAMPOS_HOST:
            raise ValueError("Campo Host invalido")

        if regla["campo_franquicia"] not in CAMPOS_FRANQUICIA:
            raise ValueError("Campo franquicia invalido")

        if regla["estado_regla"] not in {
            "PROPUESTA", "APROBADA", "INACTIVA"
        }:
            raise ValueError("Estado invalido")

        if Decimal(str(regla["tolerancia"])) < 0:
            raise ValueError("Tolerancia negativa")

        if Decimal(str(regla["factor_signo"])) not in {
            Decimal("-1"), Decimal("1")
        }:
            raise ValueError("Factor de signo invalido")

    return {
        "total_reglas": len(reglas),
        "aprobadas": sum(
            r["estado_regla"] == "APROBADA"
            for r in reglas
        ),
        "estado": "VALIDADA"
    }
