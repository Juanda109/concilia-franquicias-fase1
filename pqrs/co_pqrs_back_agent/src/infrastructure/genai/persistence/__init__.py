import logging
import uuid

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests.adapters import HTTPAdapter
from requests_aws4auth import AWS4Auth
from urllib3.util.retry import Retry

from domain.genai.persistence import AbstractPersistenceUnitOfWork
from infrastructure.core.config import genai_config

log = logging.getLogger(__name__)


class RequestsHttpConnectionWithRetries(RequestsHttpConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session.mount("https://", self._get_http_adapter())

    @staticmethod
    def _get_http_adapter():
        # Retry on the following status errors:
        #   Connection errors (for example, due to a network connectivity problem)
        #   408 Request Timeout
        #   409 Conflict
        #   429 Rate Limit
        #   >=500 Internal errors
        internal_error_codes = list(range(500, 512))
        retry_strategy = Retry(
            total=genai_config.OPENSEARCH_MAX_RETRIES,
            backoff_factor=genai_config.OPENSEARCH_RETRIES_BACKOFF,  # exponential wait factor e.g. 0.5 would wait 0.5s, 1s, 2s, 4s...
            backoff_max=genai_config.OPENSEARCH_TIMEOUT,  # TODO: genai_config to avoid unnecessary waits
            status_forcelist=[408, 409, 429] + internal_error_codes,
            raise_on_status=False,
        )
        return HTTPAdapter(max_retries=retry_strategy)


class OpensearchVectorstoreUnitOfWork(AbstractPersistenceUnitOfWork):
    def __init__(
        self,
        endpoint: str = genai_config.OPENSEARCH_ENDPOINT,
        region: str = genai_config.OPENSEARCH_REGION,
        index_name: str = genai_config.OPENSEARCH_INDEX,
    ):
        """Initialize the OpenSearch client

        Args:
            endpoint (str): URL of the OpenSearch service (with port)
            region (str): AWS region
            index_name (str): OpenSearch index to use
        """
        self._endpoint = endpoint
        self._region = region  # For example, "us-west-1"
        self._service = "es"  # 'aoss' para 'OpenSearch Service Serverless'
        self._index_name = index_name

        if genai_config.GENAI_ENVIRONMENT == "local":
            log.debug("OpenSearch: using local OpenSearch credentials")
            self._user = genai_config.OPENSEARCH_USER
            self._password = genai_config.OPENSEARCH_PASSWORD
            self._auth = (self._user, self._password)
        else:
            log.debug("OpenSearch: using AWS OpenSearch credentials")
            self._credentials = boto3.Session().get_credentials()
            self._auth = AWS4Auth(
                self._credentials.access_key,
                self._credentials.secret_key,
                self._region,
                self._service,
                session_token=self._credentials.token,
            )

    def __enter__(self):
        self.client = OpenSearch(
            self._endpoint,
            http_auth=self._auth,
            use_ssl=True,
            verify_certs=False,
            ssl_assert_hostname=False,
            ssl_show_warn=False,
            connection_class=RequestsHttpConnectionWithRetries,
            timeout=genai_config.OPENSEARCH_TIMEOUT,
        )

        return super().__enter__()

    def get_connection(self):
        """Connect to OpenSearch service"""
        self.client = OpenSearch(
            self._endpoint,
            http_auth=self._auth,
            use_ssl=True,
            verify_certs=False,
            ssl_assert_hostname=False,
            ssl_show_warn=False,
            connection_class=RequestsHttpConnectionWithRetries,
            timeout=genai_config.OPENSEARCH_TIMEOUT,
        )

    def index_exists(self, index_name: str):
        """Check if an index exists

        Args:
            index_name (str): Index name
        """
        return self.client.indices.exists(index=index_name)

    def create_index(self, index_name: str, index_body: dict):
        """Create a new index

        Args:
            index_name (str): Index name
            index_body (dict): Index definition

        Example:
            # Create an index with KNN enabled for vector storage
            index_body = {
                "settings": {
                    "index": {
                        "knn": "true",
                        "knn.algo_param.ef_search": 100
                    }
                },
                "mappings": {
                    "properties": {
                        "text": {
                            "type": "text"
                        },
                        "metadata": {
                            "type": "object"
                        },
                        "vector_field": {
                            "type": "knn_vector",
                            "dimension": 1536,
                            "method": {
                                "name": "hnsw",
                                "space_type": "cosinesimil",
                                "engine": "nmslib",
                                "parameters": {
                                    "ef_construction": 128,
                                    "m": 24
                                },
                            },
                        },
                    }
                },
            }
        """
        response = self.client.indices.create(index=index_name, body=index_body)
        return response

    def delete_index(self, index_name: str):
        """Delete an index

        Args:
            index_name (str): Index name
        """
        response = self.client.indices.delete(index=index_name)
        return response

    def index_document(
        self,
        index_name: str,
        doc: dict,
        doc_id: str = None,
        refresh: bool = False,
    ):
        """Index a document

        Args:
            index_name (str): Index name
            doc (dict): Document to index
            doc_id (str, optional): Document ID. Defaults to None.

        Example:
            doc = {
                "text": "This is a test document",
                "metadata": {
                    "title": "Test document",
                    "author": "John Doe",
                    "date": "2021-01-01",
                },
                "vector_field": [0.1, 0.2, 0.3, ...],
            }
        """

        # Generate a unique ID if not provided
        id = doc_id if doc_id else str(uuid.uuid1().int)[:32]

        response = self.client.index(index=index_name, body=doc, id=id, refresh=refresh)
        return response

    def delete_document(self, index_name: str, doc_id: str):
        """Delete a document

        Args:
            index_name (str): Index name
            doc_id (str): Document ID
        """
        response = self.client.delete(index=index_name, id=doc_id)
        return response

    def query_index(self, index_name: str, vector: dict, top_k: int = 5):
        """Query an index by vector. Finds top-k nearest neighbors to the input vector.

        Args:
            index_name (str): Index name
            vector (list[float]): Input vector
            top_k (int, optional): Number of nearest neighbors to return. Defaults to 5.

        Returns:
            list[dict]: List of results

            Each result is a dictionary with the following keys:
                - id: Document ID
                - score: Similarity score
                - metadata: Document metadata (excluding the vector_field field)
        """
        body = {
            "size": top_k,
            "query": {
                "knn": {
                    "vector_field": {
                        "vector": vector,
                        "k": top_k,
                    }
                }
            },
        }

        response = self.client.search(index=index_name, body=body)

        results = [
            {
                "id": hit["_id"],
                "score": hit["_score"],
                "metadata": {
                    x: hit["_source"][x]
                    for x in hit["_source"].keys()
                    if x != "vector_field"
                },
            }
            for hit in response["hits"]["hits"]
        ]

        return results

    def refresh_index(self, index_name: str):
        """Refresh an index

        Args:
            index_name (str): Index name
        """
        response = self.client.indices.refresh(index=index_name)
        return response

    def close(self):
        """Close the connection"""
        self.client.transport.close()


class DynamoDBUow(AbstractPersistenceUnitOfWork):
    def __init__(self, region_name: str = genai_config.AWS_REGION_NAME):
        self.region_name = region_name

    def __enter__(self):
        try:
            self._storage_connection = boto3.client(
                "dynamodb",
                region_name=self.region_name,
                endpoint_url="http://" + genai_config.GENAI_DYNAMODB_ENDPOINT,
            )
            log.debug("Endpoint URL: " + self._storage_connection.meta.endpoint_url)
            log.info("Connected to DynamoDB")
        except Exception as e:
            log.error(f"Error connecting to DynamoDB: {e}")

    def get_connection(self):
        return self._storage_connection

    def close(self):
        pass
