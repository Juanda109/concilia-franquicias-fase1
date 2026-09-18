from typing import Dict

from fastapi.openapi.utils import get_openapi

from infrastructure.core.config import genai_config


def custom_openapi(app) -> Dict:
    """
    Customize the OpenAPI layout.

    Returns:
        Dictionary containing opeanapi schema
    """

    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=genai_config.GENAI_APPLICATION,
        version=genai_config.COMPONENT_VERSION,
        description=genai_config.COMPONENT_DESCRIPTION,
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema
