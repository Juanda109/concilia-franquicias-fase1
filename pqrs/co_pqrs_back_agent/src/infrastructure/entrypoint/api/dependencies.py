"""Shared dependencies for API routes."""

import logging

from infrastructure.genai.llm.strands_workflow_agent import StrandsWorkflowAgent
from domain.workflow.workflow_engine import WorkflowEngine

from infrastructure.core.logger import get_logger, log_execution
from infrastructure.persistence.control_table_store import ControlTableStore
from infrastructure.persistence.conversation_store import ConversationStore
from infrastructure.core.config import load_back_data_service_url, load_trx_service_url


conversation_store = ConversationStore()
workflow_engine = WorkflowEngine()
control_table_store = ControlTableStore()
strands_workflow_agent: StrandsWorkflowAgent | None = None
logger = get_logger(__name__)


@log_execution
async def get_app_logger() -> logging.Logger:
    """Return the shared application logger."""

    logger.debug("Providing application logger")
    return get_logger("agentepqr.api")


@log_execution
async def get_conversation_store() -> ConversationStore:
    """Return the shared conversation persistence backend."""

    logger.debug("Providing conversation store endpoint=%s conversations_index=%s messages_index=%s",
    conversation_store.settings.endpoint,
    conversation_store.settings.conversations_index,
    conversation_store.settings.messages_index,)
    return conversation_store


@log_execution
async def get_workflow_engine() -> WorkflowEngine:
    """Return the shared workflow engine."""

    logger.debug("Providing workflow engine workflows=%s",
    sorted(workflow_engine.catalog.flows.keys()),)
    return workflow_engine


@log_execution
async def get_control_table_store() -> ControlTableStore:
    """Return the shared control-table persistence backend."""

    logger.debug("Providing control table store endpoint=%s control_index=%s",
    control_table_store.settings.endpoint,
    control_table_store.settings.control_index,)
    return control_table_store


@log_execution
async def get_strands_workflow_agent() -> StrandsWorkflowAgent:
    """Return the shared Strands workflow agent."""

    global strands_workflow_agent

    if strands_workflow_agent is None:
        logger.debug("Creating shared Strands workflow agent from environment")
        strands_workflow_agent = StrandsWorkflowAgent.from_env()
    else:
        logger.debug("Reusing shared Strands workflow agent")

    return strands_workflow_agent


@log_execution
async def get_back_data_service_url() -> str | None:
    """Return the configured base URL for the co_pqrs_back_data service, or None."""

    url = load_back_data_service_url()
    logger.debug("Providing back-data service url=%s", url or "<not configured>")
    return url


@log_execution
async def get_trx_service_url() -> str | None:
    """Return the configured base URL for the co_pqrs_back_trx_noreconocida service, or None.

    The trx path is a MOCK skeleton; this provider exists so the client can be wired
    into the flow later without touching the DI layer.
    """

    url = load_trx_service_url()
    logger.debug("Providing trx service url=%s", url or "<not configured>")
    return url
