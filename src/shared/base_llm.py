import asyncio
import logging
from enum import Enum
from typing import Any

import orjson
import vertexai  # type: ignore
import vertexai.generative_models  # type: ignore
from google.oauth2 import service_account
from pydantic_ai.models import KnownModelName, Model
from pydantic_ai.models.gemini import GeminiModel
from pydantic_ai.providers import Provider
from pydantic_ai.providers.google_vertex import GoogleVertexProvider
from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel
from vertexai.language_models._language_models import TextEmbedding  # type: ignore

from src.shared.secrets import OnePasswordManager, SecretsFactory

logger = logging.getLogger("athena.base_llm")


class VertexEnvFields(Enum):
    PROJECT_ID = "VERTEX_PROJECT_ID"
    REGION = "VERTEX_REGION"
    SERVICE_ID = "VERTEX_SERVICE_ID"
    GEMINI_API_KEY = "GEMINI_API_KEY"


class VertexLLM:
    """Vertex LLM provider"""

    EMBEDDING_MODEL_NAME = "gemini-embedding-001"
    DIMENSIONALITY = 768
    DEFAULT_ITEM_NAME = "ATHENA_VERTEX"

    VERTEX_LITE_MODEL = "gemini-2.5-flash-lite-preview-06-17"

    def __init__(self):
        self.embedding_model: TextEmbeddingModel | None = None
        self.project_id: str | None = None
        self.region: str | None = None
        self.gemini_api_key: str | None = None

    @classmethod
    async def create(cls):
        secrets_manager = await SecretsFactory.get_instance()

        self = cls()
        await self.__init_client(secrets_manager)
        return self

    async def __init_client(self, secrets_manager: OnePasswordManager):
        secrets = await secrets_manager.get_secret_item(self.DEFAULT_ITEM_NAME)

        self.project_id = secrets.secrets.get(VertexEnvFields.PROJECT_ID.value)
        self.region = secrets.secrets.get(VertexEnvFields.REGION.value)
        self.gemini_api_key = secrets.secrets.get(VertexEnvFields.GEMINI_API_KEY.value)
        self.embedding_model = TextEmbeddingModel.from_pretrained(
            self.EMBEDDING_MODEL_NAME
        )

        service_id = secrets.secrets.get(VertexEnvFields.SERVICE_ID.value)
        assert service_id is not None, "Service ID is not set"
        service_file = await secrets_manager.get_secret_file(
            self.DEFAULT_ITEM_NAME, service_id
        )
        service_credentials = await self.__init_service_account(service_file)
        vertexai.init(
            project=self.project_id,
            location=self.region,
            credentials=service_credentials,
        )

    async def __init_service_account(
        self, service_id: str
    ) -> service_account.Credentials:
        creds_info = orjson.loads(service_id)
        credentials = service_account.Credentials.from_service_account_info(creds_info)  # type: ignore
        return credentials

    @property
    def provider(self) -> Provider[Any]:
        return GoogleVertexProvider(project_id=self.project_id)

    @property
    def provider_name(self) -> KnownModelName:
        return "google-vertex:gemini-2.5-flash-preview-04-17"

    @property
    def model(self) -> Model:
        return GeminiModel("gemini-2.5-flash-preview-04-17", provider=self.provider)

    async def generate_multimodal(self, prompt: str, image: bytes):  # type: ignore
        client = vertexai.generative_models.GenerativeModel(
            model_name=self.VERTEX_LITE_MODEL,
        )
        part_1_bytes = vertexai.generative_models.Image.from_bytes(image)
        part_1 = vertexai.generative_models.Part.from_image(part_1_bytes)
        part_2 = vertexai.generative_models.Part.from_text(prompt)

        content = vertexai.generative_models.Content(
            role="user",
            parts=[part_1, part_2],
        )

        response = client.generate_content(
            contents=[content],
        )
        return response

    async def generate_text(self, prompt: str):
        client = vertexai.generative_models.GenerativeModel(
            model_name=self.VERTEX_LITE_MODEL,
        )
        response = client.generate_content(
            contents=[
                vertexai.generative_models.Content(
                    role="user",
                    parts=[vertexai.generative_models.Part.from_text(prompt)],
                )
            ],
        )
        return response

    async def embed_content(
        self,
        content: str | list[str],
        task_type: str | None = None,
    ) -> list[float] | list[list[float]]:
        try:
            assert content, "Content is empty"
            assert isinstance(content, list), "Content is not a list"
            assert len(content) > 0, "Content is empty"
            assert all(isinstance(item, str) for item in content), (
                "Content is not a list of strings"
            )
            assert task_type is not None, "Task type is not set"
            assert self.embedding_model is not None, "Embedding model is not set"
        except AssertionError as e:
            raise ValueError("Invalid content or dimensionality") from e

        inputs: list[TextEmbeddingInput | str] = [
            TextEmbeddingInput(text, task_type) for text in content
        ]

        embeddings = self.embedding_model.get_embeddings(
            texts=inputs, output_dimensionality=self.DIMENSIONALITY
        )
        try:
            assert embeddings
            assert len(embeddings) > 0
            assert isinstance(embeddings[0], TextEmbedding)
            assert embeddings[0].values
        except AssertionError as e:
            raise ValueError("Invalid embeddings") from e

        return_array: list[list[float]] = []
        for embedding in embeddings:
            return_array.append(embedding.values)

        if len(return_array) == 1:
            return return_array[0]
        return return_array


class LLMFactory:
    _instance: VertexLLM | None = None
    _lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls) -> VertexLLM:
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = await VertexLLM.create()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        cls._instance = None
