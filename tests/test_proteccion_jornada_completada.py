"""Pruebas negativas de proteccion de jornadas MVP1."""

import pytest

from app.services.bloqueo_jornada import (
    verificar_jornada_modificable,
    BloqueoJornadaError,
)


class CursorSimulado:
    def __init__(self, estado):
        self.estado = estado
        self.consultas = []

    def execute(self, consulta, parametros=None):
        self.consultas.append(
            (consulta, parametros)
        )

    def fetchone(self):
        if self.estado is None:
            return None
        return (self.estado,)


def test_jornada_pendiente_permitida():
    cursor = CursorSimulado("PENDIENTE")

    resultado = verificar_jornada_modificable(
        cursor, 295
    )

    assert resultado == 295
    assert len(cursor.consultas) == 1
    assert "FOR UPDATE" in cursor.consultas[0][0]


def test_jornada_completada_rechazada():
    cursor = CursorSimulado("COMPLETADA")

    with pytest.raises(
        BloqueoJornadaError,
        match="Jornada no modificable",
    ):
        verificar_jornada_modificable(
            cursor, 294
        )

    assert len(cursor.consultas) == 1


def test_jornada_inexistente_rechazada():
    cursor = CursorSimulado(None)

    with pytest.raises(
        BloqueoJornadaError,
        match="Jornada inexistente",
    ):
        verificar_jornada_modificable(
            cursor, 999999
        )


def test_estado_no_permitido():
    cursor = CursorSimulado("CANCELADA")

    with pytest.raises(BloqueoJornadaError):
        verificar_jornada_modificable(
            cursor, 295
        )


def test_cursor_dict():
    class CursorDict(CursorSimulado):
        def fetchone(self):
            return {"estado": "COMPLETADA"}

    cursor = CursorDict("COMPLETADA")

    with pytest.raises(BloqueoJornadaError):
        verificar_jornada_modificable(
            cursor, 294
        )
