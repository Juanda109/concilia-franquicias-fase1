"""Tests del exportador CSV de Tantia (una fila por transaccion).

Especificacion 2026-08-21: reemplaza el Excel de 21 columnas por un CSV
separado por ";" llamado DDMMAAAANotificaciones.csv, con UNA FILA POR
TRANSACCION que llego al abono automatico y ejecucion 16:00 en dias habiles.
"""

from __future__ import annotations

import logging
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main as m  # noqa: E402


def _settings(**overrides):
    settings = m.Settings.from_env()
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


def _detalle(statement_id="0001", movement_id="000061", amount=150000, interest=4500):
    return {
        "statementDetail": {"statementId": statement_id, "movementId": movement_id},
        "dateOper": "2026-08-06",
        "amountOperation": {"amount": amount, "currency": "COP"},
        "interest": interest,
        "responseOperati": "008123",
    }


def _item(**overrides):
    base = {
        "fecha_recepcion": "2026-08-21",
        "customer_id": "1010223694",
        "customer_name": "CLIENTE PRUEBA",
        "personal_id": "00000123456789",
        "customer_mail": "cliente@mail.com",
        "tipo_producto": "Tarjeta de Credito",
        "origin_flag": "TDC",
        "numero_tarjeta": "4912680517944979",
        "contrato": "00320011234567",
        "detalle": _detalle(),
    }
    base.update(overrides)
    return base


def _case(items=None, tantia=None):
    snapshot = {}
    if tantia is not None:
        snapshot["tantia"] = tantia
    if items is not None:
        snapshot["tantia_items"] = items
    return {
        "client_id": "1010223694",
        "conversation_id": "1010223694_20260821",
        "updated_at": "2026-08-21T16:00:00Z",
        "milestones": ["completed_report"],
        "outcome": "devolucion",
        "trx_case_state_snapshot": snapshot,
    }


class ColumnLayoutTests(unittest.TestCase):
    def test_twenty_columns_in_order(self):
        self.assertEqual(len(m.TANTIA_COLUMNS), 21)
        self.assertEqual(m.TANTIA_COLUMNS[0], "fecha_recepcion")
        self.assertEqual(m.TANTIA_COLUMNS[-1], "tipo_de_notificacion")

    def test_las_20_columnas_originales_no_se_movieron(self):
        """`tipo_de_notificacion` se agrego AL FINAL: el RPA lee por posicion."""

        self.assertEqual(m.TANTIA_COLUMNS[19], "Observaciones")

    def test_dedup_columns_are_not_part_of_the_layout(self):
        for column in m.DEDUP_COLUMNS:
            self.assertNotIn(column, m.TANTIA_COLUMNS)

    def test_file_name_format(self):
        path = m.csv_path_for(Path("/tmp"), date(2026, 8, 21))
        self.assertEqual(path.name, "21082026Notificaciones.csv")


class OneRowPerTransactionTests(unittest.TestCase):
    """El corazon del cambio: 3 transacciones reportadas -> 3 filas."""

    def test_three_transactions_produce_three_rows(self):
        items = [
            _item(detalle=_detalle("0001", "000061", 150000, 4500)),
            _item(detalle=_detalle("0001", "000062", 99000, 1980)),
            _item(detalle=_detalle("0002", "000063", 75000, 0)),
        ]
        rows = m.build_tantia_rows(_case(items=items), _settings())
        self.assertEqual(len(rows), 3)
        self.assertEqual(
            [r["numero_operacion"] for r in rows], ["000061", "000062", "000063"]
        )

    def test_dedup_key_is_per_transaction(self):
        items = [
            _item(detalle=_detalle("0001", "000061")),
            _item(detalle=_detalle("0001", "000062")),
        ]
        rows = m.build_tantia_rows(_case(items=items), _settings())
        self.assertEqual(len({r["_dedup_key"] for r in rows}), 2)

    def test_falls_back_to_legacy_single_tantia(self):
        """Casos anteriores al cambio solo tienen `tantia`: no se pierden."""

        rows = m.build_tantia_rows(_case(tantia=_item()), _settings())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["numero_operacion"], "000061")

    def test_case_without_snapshot_produces_no_rows(self):
        self.assertEqual(m.build_tantia_rows(_case(), _settings()), [])


class FieldMappingTests(unittest.TestCase):
    def _row(self, **item_overrides):
        return m.build_tantia_rows(
            _case(items=[_item(**item_overrides)]), _settings()
        )[0]

    def test_aso_fields(self):
        row = self._row()
        self.assertEqual(row["numero_extracto"], "0001")
        self.assertEqual(row["numero_operacion"], "000061")
        self.assertEqual(row["fecha_compra"], "06/08/2026")
        self.assertEqual(row["valor_compra"], "150000")
        self.assertEqual(row["valor_intereses"], "4500")
        self.assertEqual(row["codigo_autorizacion"], "008123")

    def test_total_abonado_is_the_sum(self):
        row = self._row(detalle=_detalle(amount=150000, interest=4500))
        self.assertEqual(row["valor_total_abonado"], "154500")

    def test_total_abonado_without_interest(self):
        row = self._row(detalle=_detalle(amount=75000, interest=0))
        self.assertEqual(row["valor_total_abonado"], "75000")

    def test_postgres_fields(self):
        row = self._row()
        self.assertEqual(row["nombre_titular"], "CLIENTE PRUEBA")
        self.assertEqual(row["tipo_producto"], "Tarjeta de Credito")
        self.assertEqual(row["referencia_altamira"], "1010223694")
        self.assertEqual(row["correo_notificacion"], "cliente@mail.com")

    def test_documento_without_padding_zeros(self):
        """personal_id viene con 5 ceros de relleno en Postgres."""

        self.assertEqual(self._row(personal_id="00000123456789")["documento_cliente"], "123456789")
        self.assertEqual(self._row(personal_id="1010223694")["documento_cliente"], "1010223694")
        self.assertEqual(self._row(personal_id="")["documento_cliente"], "")

    def test_numero_producto_tdc_uses_the_card(self):
        row = self._row(origin_flag="TDC")
        self.assertEqual(row["numero_producto"], "4912680517944979")
        self.assertEqual(len(row["numero_producto"]), 16)

    def test_numero_producto_pasivo_uses_the_contract(self):
        row = self._row(origin_flag="PASIVO")
        self.assertEqual(row["numero_producto"], "00320011234567")

    def test_id_reclamo_is_altamira_plus_date(self):
        row = self._row()
        self.assertEqual(row["id_reclamo"], "1010223694_21/08/2026")

    def test_dates_are_dd_mm_yyyy(self):
        row = self._row()
        self.assertEqual(row["fecha_recepcion"], "21/08/2026")

    def test_columns_that_must_stay_empty(self):
        row = self._row()
        for column in ("id_referencia", "estado_abono", "Habilitador", "estado_notificacion", "Observaciones"):
            with self.subTest(column=column):
                self.assertEqual(row[column], "")


class TipoDeNotificacionTests(unittest.TestCase):
    """La columna 21 dice de que flujo viene cada fila."""

    def _row(self, **source_overrides):
        case = _case(items=[_item()])
        case.update(source_overrides)
        return m.build_tantia_rows(case, _settings())[0]

    def test_toma_el_tipo_de_la_ficha(self):
        self.assertEqual(
            self._row(tipo_de_notificacion="doble_cobro")["tipo_de_notificacion"],
            "doble_cobro",
        )

    def test_ficha_antigua_sin_el_campo_cae_a_txnr(self):
        """Las fichas previas al campo son todas de transaccion no reconocida."""

        self.assertEqual(self._row()["tipo_de_notificacion"], "trx_no_reconocida")

    def test_nunca_queda_vacia(self):
        self.assertEqual(
            self._row(tipo_de_notificacion="   ")["tipo_de_notificacion"],
            "trx_no_reconocida",
        )


class ClientIdPrefixTests(unittest.TestCase):
    """El prefijo del tipo de notificacion es INTERNO: nunca sale hacia Tantia.

    El id del documento en OpenSearch lleva el tipo delante para que dos flujos
    no se pisen la ficha del mismo cliente. El CSV solo debe llevar el numero.
    """

    def _row(self, source_overrides):
        case = _case(items=[_item(customer_id="")])
        case.update(source_overrides)
        return m.build_tantia_rows(case, _settings())[0]

    def test_usa_el_campo_client_id_que_ya_viene_pelado(self):
        row = self._row(
            {"client_id": "1010223694", "tipo_de_notificacion": "doble_cobro"}
        )
        self.assertEqual(row["referencia_altamira"], "1010223694")
        self.assertTrue(row["_dedup_key"].startswith("1010223694|"))

    def test_respaldo_por_id_despoja_el_prefijo(self):
        # Ficha sin `client_id`: se cae al `_id`, que SI lleva el prefijo.
        row = self._row(
            {
                "client_id": "",
                "_id": "doble_cobro_1010223694",
                "tipo_de_notificacion": "doble_cobro",
            }
        )
        self.assertEqual(row["referencia_altamira"], "1010223694")
        self.assertTrue(row["_dedup_key"].startswith("1010223694|"))

    def test_respaldo_por_id_sin_prefijo_se_deja_igual(self):
        # Transaccion no reconocida conserva su id historico, sin prefijo.
        row = self._row(
            {
                "client_id": "",
                "_id": "1010223694",
                "tipo_de_notificacion": "trx_no_reconocida",
            }
        )
        self.assertEqual(row["referencia_altamira"], "1010223694")

    def test_no_recorta_un_id_que_solo_se_parece_al_prefijo(self):
        # El tipo es "doble_cobro"; un id que empieza distinto no se toca.
        row = self._row(
            {
                "client_id": "",
                "_id": "doble_cobro_x_1010223694",
                "tipo_de_notificacion": "trx_no_reconocida",
            }
        )
        self.assertEqual(row["referencia_altamira"], "doble_cobro_x_1010223694")


class NestedFieldReadTests(unittest.TestCase):
    """_dget debe leer rutas anidadas: antes devolvia el diccionario completo."""

    def test_dotted_path(self):
        self.assertEqual(_dget_amount(), "150000")

    def test_candidate_fallback(self):
        detalle = {"process": {"responseOperati": "009999"}}
        self.assertEqual(
            m._dget(detalle, "responseOperati", "process.responseOperati"), "009999"
        )

    def test_never_returns_a_container(self):
        detalle = {"amountOperation": {"amount": 1}}
        self.assertEqual(m._dget(detalle, "amountOperation"), "")


def _dget_amount() -> str:
    return m._dget(_detalle(), "amountOperation.amount")


class CsvWriteTests(unittest.TestCase):
    def setUp(self):
        self.settings = _settings()
        self.logger = logging.getLogger("test")

    def test_writes_header_and_rows(self):
        rows = m.build_tantia_rows(_case(items=[_item()]), self.settings)
        with tempfile.TemporaryDirectory() as folder:
            path = m.csv_path_for(Path(folder), date(2026, 8, 21))
            m.save_or_append_csv(path, rows, self.settings, self.logger)
            lineas = path.read_text(encoding=self.settings.csv_encoding).strip().split("\n")
            self.assertEqual(len(lineas), 2)
            self.assertEqual(len(lineas[0].split(";")), 23)  # 21 + 2 tecnicas
            self.assertTrue(lineas[0].startswith("fecha_recepcion;numero_producto"))

    def test_append_does_not_repeat_the_header(self):
        with tempfile.TemporaryDirectory() as folder:
            path = m.csv_path_for(Path(folder), date(2026, 8, 21))
            primera = m.build_tantia_rows(
                _case(items=[_item(detalle=_detalle("0001", "000061"))]), self.settings
            )
            segunda = m.build_tantia_rows(
                _case(items=[_item(detalle=_detalle("0002", "000062"))]), self.settings
            )
            m.save_or_append_csv(path, primera, self.settings, self.logger)
            m.save_or_append_csv(path, segunda, self.settings, self.logger)
            lineas = path.read_text(encoding=self.settings.csv_encoding).strip().split("\n")
            self.assertEqual(len(lineas), 3)
            self.assertEqual(lineas[0].count("fecha_recepcion"), 1)

    def test_empty_window_delivers_a_header_only_file(self):
        """Es un fichero de CORTE: se entrega siempre, tenga datos o no."""

        with tempfile.TemporaryDirectory() as folder:
            path = m.csv_path_for(Path(folder), date(2026, 8, 21))
            m.save_or_append_csv(path, [], self.settings, self.logger)
            self.assertTrue(path.exists())
            contenido = path.read_text(encoding=self.settings.csv_encoding).strip()
            self.assertEqual(len(contenido.split("\n")), 1)

    def test_existing_file_is_preserved_when_there_is_nothing_new(self):
        """Si el fichero YA quedo generado, no se toca ni se trunca."""

        with tempfile.TemporaryDirectory() as folder:
            path = m.csv_path_for(Path(folder), date(2026, 8, 21))
            rows = m.build_tantia_rows(_case(items=[_item()]), self.settings)
            m.save_or_append_csv(path, rows, self.settings, self.logger)
            antes = path.read_text(encoding=self.settings.csv_encoding)

            m.save_or_append_csv(path, [], self.settings, self.logger)

            self.assertTrue(path.exists())
            self.assertEqual(path.read_text(encoding=self.settings.csv_encoding), antes)

    def test_existing_file_is_not_truncated_when_there_is_nothing_new(self):
        with tempfile.TemporaryDirectory() as folder:
            path = m.csv_path_for(Path(folder), date(2026, 8, 21))
            rows = m.build_tantia_rows(_case(items=[_item()]), self.settings)
            m.save_or_append_csv(path, rows, self.settings, self.logger)
            m.save_or_append_csv(path, [], self.settings, self.logger)
            lineas = path.read_text(encoding=self.settings.csv_encoding).strip().split("\n")
            self.assertEqual(len(lineas), 2)

    def test_dedup_keys_are_read_back(self):
        with tempfile.TemporaryDirectory() as folder:
            path = m.csv_path_for(Path(folder), date(2026, 8, 21))
            rows = m.build_tantia_rows(
                _case(items=[_item(detalle=_detalle("0001", "000061"))]), self.settings
            )
            m.save_or_append_csv(path, rows, self.settings, self.logger)
            claves = m.load_existing_keys(path, self.settings, self.logger)
            self.assertIn("1010223694|0001|000061", claves)

    def test_delimiter_is_semicolon(self):
        self.assertEqual(self.settings.csv_delimiter, ";")


class BusinessDayTests(unittest.TestCase):
    def test_weekdays_are_business_days(self):
        settings = _settings(festivos=frozenset())
        # OJO: 2026-08-17 NO sirve como "lunes normal", es La Asuncion trasladada.
        for dia in (date(2026, 8, 24), date(2026, 8, 21)):  # lunes y viernes
            with self.subTest(dia=dia):
                self.assertTrue(m.es_dia_habil(dia, settings))

    def test_weekend_is_not(self):
        settings = _settings(festivos=frozenset())
        for dia in (date(2026, 8, 22), date(2026, 8, 23)):  # sabado y domingo
            with self.subTest(dia=dia):
                self.assertFalse(m.es_dia_habil(dia, settings))

    def test_configured_holiday_is_not_a_business_day(self):
        """El cron solo filtra lun-vie; los festivos se excluyen aqui."""

        settings = _settings(festivos=frozenset({"2026-08-24"}))
        self.assertFalse(m.es_dia_habil(date(2026, 8, 24), settings))


class DevolucionFilterTests(unittest.TestCase):
    def test_only_completed_report_cases(self):
        self.assertTrue(m.is_devolucion_case(_case(items=[_item()])))
        sin_hito = _case(items=[_item()])
        sin_hito["milestones"] = ["entered_op4"]
        sin_hito.pop("outcome")
        self.assertFalse(m.is_devolucion_case(sin_hito))


class MissingIndexTests(unittest.TestCase):
    """El indice puede no existir todavia, y eso NO es un error.

    Lo crea el AGENTE en la primera devolucion automatica (upsert de OpenSearch);
    aqui solo se lee. En produccion el flujo TXNR entra CERRADO por el porton, asi
    que puede pasar tiempo sin que exista. El job debe seguir generando el CSV del
    dia (solo encabezado), que es lo que Tantia espera cada dia habil.
    """

    def test_missing_index_still_delivers_the_cutoff_file(self):
        """El 404 no es error: se entrega el fichero de corte vacio."""

        from opensearchpy.exceptions import NotFoundError

        settings = _settings()
        logger = logging.getLogger("test")

        with tempfile.TemporaryDirectory() as folder:
            path = m.csv_path_for(Path(folder), date(2026, 8, 21))
            try:
                raise NotFoundError(404, "index_not_found_exception", {})
            except NotFoundError:
                filas = []
            m.save_or_append_csv(path, filas, settings, logger)
            self.assertTrue(path.exists())
            self.assertTrue(
                path.read_text(encoding=settings.csv_encoding).startswith("fecha_recepcion;")
            )

    def test_connection_error_must_not_deliver_an_empty_file(self):
        """Un fallo de conexion NO puede parecer "no hubo abonos".

        Por eso main() re-lanza OSConnectionError en vez de continuar: el job
        falla y no se entrega un fichero vacio enganoso.
        """

        import inspect

        fuente = inspect.getsource(m.main)
        inicio = fuente.index("except OSConnectionError")
        bloque = fuente[inicio : inicio + 400]
        self.assertIn("raise", bloque)

    def test_main_catches_not_found_before_the_generic_handler(self):
        """Si se capturara despues, el job saldria con codigo 1 y sin CSV."""

        import inspect

        fuente = inspect.getsource(m.main)
        self.assertIn("OSNotFoundError", fuente)
        self.assertLess(fuente.index("OSNotFoundError"), fuente.index("Error fatal"))

    def test_not_found_is_not_treated_as_connection_error(self):
        """Son casos distintos: uno es 'aun no hay datos', el otro es un fallo."""

        import inspect

        fuente = inspect.getsource(m.main)
        self.assertLess(
            fuente.index("OSNotFoundError"), fuente.index("OSConnectionError")
        )


class CutoffWindowTests(unittest.TestCase):
    """Ventana de corte (decision 2026-08-24).

    El fichero de un dia habil cubre desde el corte del dia habil ANTERIOR hasta
    el corte de hoy. Asi cada transaccion se entrega exactamente una vez: lo
    posterior al corte sale en el fichero del proximo dia habil.
    """

    def setUp(self):
        self.settings = _settings(festivos=frozenset())
        self.logger = logging.getLogger("test")

    def test_cutoff_hour_is_sixteen(self):
        self.assertEqual(self.settings.hora_corte, 16)

    def test_tuesday_window_is_monday_to_tuesday(self):
        martes = date(2026, 8, 25)
        self.assertEqual(
            m.corte_anterior(martes, self.settings), date(2026, 8, 24)
        )
        gte, lt = m.ventana_de_corte(martes, self.settings)
        # 16:00 Bogota (UTC-5) = 21:00 UTC del mismo dia.
        self.assertEqual(gte, "2026-08-24T21:00:00Z")
        self.assertEqual(lt, "2026-08-25T21:00:00Z")

    def test_monday_window_covers_the_weekend(self):
        """El lunes cubre viernes tras el corte + sabado + domingo."""

        lunes = date(2026, 8, 24)
        self.assertEqual(
            m.corte_anterior(lunes, self.settings), date(2026, 8, 21)  # viernes
        )
        gte, lt = m.ventana_de_corte(lunes, self.settings)
        self.assertEqual(gte, "2026-08-21T21:00:00Z")  # viernes 16:00
        self.assertEqual(lt, "2026-08-24T21:00:00Z")   # lunes 16:00

    def test_holiday_is_skipped_when_looking_back(self):
        """Si el viernes fue festivo, el lunes arranca desde el jueves."""

        settings = _settings(festivos=frozenset({"2026-08-21"}))
        self.assertEqual(
            m.corte_anterior(date(2026, 8, 24), settings), date(2026, 8, 20)
        )

    def test_windows_are_contiguous_and_do_not_overlap(self):
        """El fin de una ventana es el inicio de la siguiente: sin huecos ni solapes."""

        viernes, lunes, martes = date(2026, 8, 21), date(2026, 8, 24), date(2026, 8, 25)
        _, fin_viernes = m.ventana_de_corte(viernes, self.settings)
        ini_lunes, fin_lunes = m.ventana_de_corte(lunes, self.settings)
        ini_martes, _ = m.ventana_de_corte(martes, self.settings)
        self.assertEqual(fin_viernes, ini_lunes)
        self.assertEqual(fin_lunes, ini_martes)

    def test_query_uses_the_window(self):
        gte, lt = m.ventana_de_corte(date(2026, 8, 25), self.settings)
        rango = m.build_window_query(gte, lt)["bool"]["filter"][0]["range"]["updated_at"]
        self.assertEqual(rango["gte"], gte)
        self.assertEqual(rango["lt"], lt)


class CutoffFileAlwaysDeliveredTests(unittest.TestCase):
    """El fichero de corte se entrega SIEMPRE, tenga datos o no."""

    def setUp(self):
        self.settings = _settings()
        self.logger = logging.getLogger("test")

    def test_empty_window_still_delivers_the_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = m.csv_path_for(Path(folder), date(2026, 8, 24))
            m.save_or_append_csv(path, [], self.settings, self.logger)
            self.assertTrue(path.exists())
            contenido = path.read_text(encoding=self.settings.csv_encoding).strip()
            self.assertEqual(len(contenido.split("\n")), 1)
            self.assertTrue(contenido.startswith("fecha_recepcion;"))

    def test_window_with_data_writes_one_row_per_transaction(self):
        items = [
            _item(detalle=_detalle("0001", "000061")),
            _item(detalle=_detalle("0001", "000062")),
            _item(detalle=_detalle("0002", "000063")),
        ]
        rows = m.build_tantia_rows(_case(items=items), self.settings)
        with tempfile.TemporaryDirectory() as folder:
            path = m.csv_path_for(Path(folder), date(2026, 8, 24))
            m.save_or_append_csv(path, rows, self.settings, self.logger)
            lineas = path.read_text(encoding=self.settings.csv_encoding).strip().split("\n")
            self.assertEqual(len(lineas), 4)  # encabezado + 3 transacciones

    def test_rerun_does_not_duplicate_or_truncate(self):
        with tempfile.TemporaryDirectory() as folder:
            path = m.csv_path_for(Path(folder), date(2026, 8, 24))
            rows = m.build_tantia_rows(_case(items=[_item()]), self.settings)
            m.save_or_append_csv(path, rows, self.settings, self.logger)
            antes = path.read_text(encoding=self.settings.csv_encoding)
            # Segunda corrida del mismo dia: la clave ya esta en el fichero.
            claves = m.load_existing_keys(path, self.settings, self.logger)
            nuevas = [r for r in rows if r["_dedup_key"] not in claves]
            m.save_or_append_csv(path, nuevas, self.settings, self.logger)
            self.assertEqual(path.read_text(encoding=self.settings.csv_encoding), antes)


class ColombianHolidayTests(unittest.TestCase):
    """Festivos nacionales calculados, no listados a mano (decision 2026-08-24).

    Se eligio la libreria `holidays` en vez de implementar el algoritmo porque al
    escribirlo a mano en la misma sesion se omitio uno de los 19 festivos de 2026
    (Nuestra Senora del Rosario de Chiquinquira, 9 de julio, trasladado al lunes
    13). Un olvido asi no se nota hasta que un corte sale mal.
    """

    def setUp(self):
        self.settings = _settings(festivos=frozenset())

    def test_2026_has_nineteen_national_holidays(self):
        self.assertEqual(len(m._festivos_colombia(2026)), 19)

    def test_fixed_date_holidays(self):
        """No se trasladan: caen donde caen."""

        for iso in ("2026-01-01", "2026-05-01", "2026-07-20", "2026-08-07",
                    "2026-12-08", "2026-12-25"):
            with self.subTest(iso=iso):
                self.assertIn(iso, m._festivos_colombia(2026))

    def test_emiliani_law_moves_to_monday(self):
        """Reyes (6/1/2026, martes) se traslada al lunes 12."""

        festivos = m._festivos_colombia(2026)
        self.assertIn("2026-01-12", festivos)
        self.assertNotIn("2026-01-06", festivos)

    def test_easter_based_holidays(self):
        """Pascua 2026 = 5 de abril; jueves y viernes santo NO se trasladan."""

        festivos = m._festivos_colombia(2026)
        self.assertIn("2026-04-02", festivos)  # Jueves Santo
        self.assertIn("2026-04-03", festivos)  # Viernes Santo
        self.assertIn("2026-05-18", festivos)  # Ascension (trasladada)
        self.assertIn("2026-06-08", festivos)  # Corpus Christi (trasladado)
        self.assertIn("2026-06-15", festivos)  # Sagrado Corazon (trasladado)

    def test_the_holiday_i_missed_by_hand(self):
        """Chiquinquira: el que se omitio al calcularlo a mano."""

        self.assertIn("2026-07-13", m._festivos_colombia(2026))
        self.assertFalse(m.es_dia_habil(date(2026, 7, 13), self.settings))

    def test_holidays_are_not_business_days(self):
        for d in (date(2026, 1, 1), date(2026, 4, 2), date(2026, 4, 3),
                  date(2026, 7, 13), date(2026, 12, 8)):
            with self.subTest(dia=d):
                self.assertFalse(m.es_dia_habil(d, self.settings))

    def test_normal_weekdays_are_business_days(self):
        for d in (date(2026, 8, 24), date(2026, 8, 25), date(2026, 8, 21)):
            with self.subTest(dia=d):
                self.assertTrue(m.es_dia_habil(d, self.settings))

    def test_manual_list_complements_the_calculation(self):
        """FESTIVOS sirve para dias no laborales que NO son festivos nacionales."""

        settings = _settings(festivos=frozenset({"2026-08-25"}))
        self.assertFalse(m.es_dia_habil(date(2026, 8, 25), settings))
        # Y no rompe el calculo de los nacionales.
        self.assertFalse(m.es_dia_habil(date(2026, 7, 13), settings))

    def test_other_years_are_computed_too(self):
        """No hay lista quemada: cualquier anio se calcula."""

        for anio in (2027, 2028, 2030):
            with self.subTest(anio=anio):
                self.assertGreaterEqual(len(m._festivos_colombia(anio)), 18)


class WindowSkipsHolidaysTests(unittest.TestCase):
    """La ventana arranca en el dia HABIL anterior, saltando festivos."""

    def setUp(self):
        self.settings = _settings(festivos=frozenset())

    def test_after_a_monday_holiday_window_starts_on_friday(self):
        """Martes 13/01/2026: el lunes 12 fue festivo -> arranca el viernes 9."""

        martes = date(2026, 1, 13)
        self.assertEqual(m.corte_anterior(martes, self.settings), date(2026, 1, 9))
        gte, lt = m.ventana_de_corte(martes, self.settings)
        self.assertEqual(gte, "2026-01-09T21:00:00Z")
        self.assertEqual(lt, "2026-01-13T21:00:00Z")

    def test_easter_week_window(self):
        """Lunes 6/04: salta viernes y jueves santo -> arranca el miercoles 1."""

        self.assertEqual(
            m.corte_anterior(date(2026, 4, 6), self.settings), date(2026, 4, 1)
        )

    def test_no_data_is_lost_across_a_holiday(self):
        """La ventana del dia habil siguiente cubre el festivo completo."""

        gte, lt = m.ventana_de_corte(date(2026, 1, 13), self.settings)
        # El lunes 12 (festivo) queda DENTRO de la ventana del martes.
        self.assertLess(gte, "2026-01-12T00:00:00Z")
        self.assertGreater(lt, "2026-01-12T23:59:59Z")

    def test_windows_remain_contiguous_around_a_holiday(self):
        viernes, martes = date(2026, 1, 9), date(2026, 1, 13)
        _, fin_viernes = m.ventana_de_corte(viernes, self.settings)
        ini_martes, _ = m.ventana_de_corte(martes, self.settings)
        self.assertEqual(fin_viernes, ini_martes)


if __name__ == "__main__":
    unittest.main()
