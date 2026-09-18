import logging
import os
from typing import Any

import httpx as _httpx
from openai.lib.azure import AzureOpenAI

from domain.genai.embedding import AbstractEmbeddingUnitOfWork
from infrastructure.core.config import genai_config

log = logging.getLogger(__name__)


def _get_http_client(proxy=genai_config.PROXY_NG):
    return _httpx.Client(proxies=proxy)


class OpenAIEmbeddingUnitOfWork(AbstractEmbeddingUnitOfWork):
    def __init__(
        self,
        model: str = genai_config.DEFAULT_EMBEDDING_MODEL_NAME,
        http_client: _httpx.Client = _get_http_client,
        proxy: Any = genai_config.PROXY_NG,
        azure_endpoint: str = genai_config.OPENAI_ENDPOINT,
        azure_apikey: str = genai_config.OPENAI_KEY,
        azure_api_version: str = genai_config.OPENAI_VERSION,
    ):
        self._model = model
        self._http_client = http_client
        self._proxy = proxy
        self._azure_endpoint = azure_endpoint
        self._azure_apikey = azure_apikey
        self._azure_api_version = azure_api_version

    def __enter__(self):
        log.info("start embedding")
        os.environ["TIKTOKEN_CACHE_DIR"] = genai_config.TIKTOKEN_CACHE_DIR

        # Retry on the following status errors:
        #   Connection errors (for example, due to a network connectivity problem)
        #   408 Request Timeout
        #   409 Conflict
        #   429 Rate Limit
        #   >=500 Internal errors

        self._embedding = AzureOpenAI(
            azure_endpoint=self._azure_endpoint,
            api_key=self._azure_apikey,
            api_version=self._azure_api_version,
            http_client=self._http_client(),
            timeout=int(genai_config.OPENAI_TIMEOUT),  # seconds
            max_retries=int(genai_config.OPENAI_MAX_RETRIES),
        )
        log.info(f"embedding{self._embedding} ")
        return super().__enter__()

    def get(self):
        return self._embedding

    def execute_embedding(self, text, input_model_name=None):
        return self._embedding.embeddings.create(
            model=input_model_name if input_model_name else self._model,
            input=text,
        )
