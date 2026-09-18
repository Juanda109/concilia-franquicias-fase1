from pathlib import Path

from application.scenarios.resolver import TrxAsoResolver

DATA = Path(__file__).resolve().parents[1] / "data"
resolver = TrxAsoResolver(data_dir=DATA)


def test_doc_number_extraction() -> None:
    assert TrxAsoResolver._doc_number_from_target("01-1013634958") == "1013634958"
    assert TrxAsoResolver._doc_number_from_target("1013634958") == "1013634958"


def test_salesforce_known_and_unknown() -> None:
    assert len(resolver.salesforce_issues("01-1013634958")["data"]) == 3
    assert resolver.salesforce_issues("01-0000000000")["data"] == []


def test_financial_overview_default_empty() -> None:
    assert resolver.financial_overview("no-existe")["data"]["contracts"] == []


def test_transactions_and_operations_present() -> None:
    assert len(resolver.transactions("4912680517940060")["data"]) == 3
    assert resolver.transactions("4912680517940066")["data"] == []
    ops = resolver.operations("4912680517940063")["data"][0]["operations"]
    assert ops[0]["responseOperati"] == "Reversado"


def test_block_failure_default_false() -> None:
    assert resolver.block_should_fail("4912680517940060") is False
