"""Shared dependencies for API routes."""

import logging

from infrastructure.core.logger import get_logger, log_execution
from infrastructure.persistence.commercial_info_client import CommercialInfoClient
from infrastructure.persistence.customer_identity_repository import CustomerIdentityRepository
from infrastructure.persistence.opensearch_client import OpenSearchClient

customer_identity_repository = CustomerIdentityRepository()
commercial_info_client = CommercialInfoClient()
opensearch_client = OpenSearchClient()
logger = get_logger(__name__)


@log_execution
async def get_app_logger() -> logging.Logger:
    """Return the shared application logger."""

    logger.debug("Providing application logger")
    return get_logger("co_pqrs_back_data.api")


@log_execution
async def get_customer_identity_repository() -> CustomerIdentityRepository:
    """Return the shared customer identity repository."""

    logger.debug(
        "Providing customer identity repository source=%s csv_path=%s postgres_table=%s",
        customer_identity_repository.settings.source,
        customer_identity_repository.settings.customer_identity_csv_path,
        customer_identity_repository.settings.postgres_table,
    )
    return customer_identity_repository


@log_execution
async def get_commercial_info_client() -> CommercialInfoClient:
    """Return the shared commercial-info mock client."""

    logger.debug(
        "Providing commercial info client mock_dir=%s",
        commercial_info_client.settings.commercial_info_mock_dir,
    )
    return commercial_info_client


@log_execution
async def get_opensearch_client() -> OpenSearchClient:
    """Return the shared OpenSearch client."""

    logger.debug(
        "Providing OpenSearch client endpoint=%s index=%s",
        opensearch_client.settings.base_url,
        opensearch_client.settings.control_index,
    )
    return opensearch_client
