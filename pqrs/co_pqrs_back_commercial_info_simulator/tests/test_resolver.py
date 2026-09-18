from pathlib import Path

from application.scenarios.resolver import ScenarioResolver


def _resolver() -> ScenarioResolver:
    data_dir = Path(__file__).resolve().parents[1] / "data"
    return ScenarioResolver(data_dir=data_dir)


def test_resolves_exact_query_match() -> None:
    resolver = _resolver()
    result = resolver.resolve(
        document_type="01",
        document_number="000001069759414",
        last_name="GUTIERREZ",
    )

    assert result.strategy == "query_exact"
    assert result.file_path.name == "commercial_info_000001069759414.json"


def test_resolves_financial_statements_e2e_scenario() -> None:
    resolver = _resolver()
    result = resolver.resolve(
        document_type="C.C",
        document_number="000000080255840",
        last_name="ALVAREZ",
    )

    assert result.strategy == "query_exact"
    assert result.file_path.name == "financial_statements_00130009005078159809.json"


def test_resolves_default_when_last_name_is_provided_but_wrong() -> None:
    resolver = _resolver()
    result = resolver.resolve(
        document_type="01",
        document_number="000001069759414",
        last_name="no-match",
    )

    assert result.strategy == "default_fallback"
    assert result.file_path.name == "commercial_info_default.json"


def test_resolves_document_fallback_when_last_name_does_not_match() -> None:
    resolver = _resolver()
    result = resolver.resolve(
        document_type="01",
        document_number="000001069759414",
        last_name="",
    )

    assert result.strategy == "query_without_last_name"
    assert result.file_path.name == "commercial_info_000001069759414.json"


def test_resolves_default_when_nothing_matches() -> None:
    resolver = _resolver()
    result = resolver.resolve(
        document_type="01",
        document_number="999999999999999",
        last_name="desconocido",
    )

    assert result.strategy == "default_fallback"
    assert result.file_path.name == "commercial_info_default.json"
