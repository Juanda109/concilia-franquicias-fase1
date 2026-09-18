from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Query

from application.scenarios.resolver import ScenarioResolver


def build_app() -> FastAPI:
    app = FastAPI(
        title="commercial_info simulator",
        version="0.1.0",
        description="Simulador de commercial-information con JSONs por escenario.",
    )

    resolver = ScenarioResolver(data_dir=Path(__file__).resolve().parents[3] / "data")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/risks/v0/commercial-information")
    async def commercial_information(
        document_type: str = Query(
            ...,
            alias="identityDocument.documentType",
        ),
        document_number: str = Query(
            ...,
            alias="identityDocument.documentNumber",
        ),
        last_name: str = Query(
            "",
            alias="customer.lastName",
        ),
    ) -> dict:
        result = resolver.resolve(
            document_type=document_type,
            document_number=document_number,
            last_name=last_name,
        )
        return resolver.read_payload(result.file_path)

    return app


app = build_app()
