import os
from typing import Any
from uuid import UUID

from pymilvus import (
    AnnSearchRequest,
    DataType,
    Function,
    FunctionType,
    MilvusClient,
    RRFRanker,
)


class MilvusStore:
    def __init__(
        self,
        uri: str | None = None,
        collection_name: str | None = None,
        embedding_dimension: int | None = None,
        client: MilvusClient | None = None,
    ) -> None:
        self.uri = uri or os.getenv("MILVUS_URI", "http://localhost:19530")
        self.collection_name = collection_name or os.getenv(
            "MILVUS_COLLECTION", "knowledge_chunks"
        )
        self.embedding_dimension = (
            embedding_dimension
            if embedding_dimension is not None
            else int(os.getenv("EMBEDDING_DIMENSION", "768"))
        )
        if self.embedding_dimension <= 0:
            raise ValueError("EMBEDDING_DIMENSION must be greater than zero")

        self.client = client if client is not None else MilvusClient(uri=self.uri)

    def ensure_collection(self) -> bool:
        if self.client.has_collection(collection_name=self.collection_name):
            self._validate_existing_collection()
            self.client.load_collection(collection_name=self.collection_name)
            return False

        schema = self.client.create_schema(
            auto_id=False,
            enable_dynamic_field=False,
        )
        schema.add_field(
            field_name="id",
            datatype=DataType.VARCHAR,
            is_primary=True,
            max_length=128,
        )
        schema.add_field(
            field_name="document_id",
            datatype=DataType.VARCHAR,
            max_length=256,
        )
        schema.add_field(field_name="chunk_index", datatype=DataType.INT64)
        schema.add_field(
            field_name="content",
            datatype=DataType.VARCHAR,
            max_length=65535,
            enable_analyzer=True,
        )
        schema.add_field(
            field_name="embedding",
            datatype=DataType.FLOAT_VECTOR,
            dim=self.embedding_dimension,
        )
        schema.add_field(
            field_name="sparse_embedding",
            datatype=DataType.SPARSE_FLOAT_VECTOR,
        )
        schema.add_field(field_name="metadata", datatype=DataType.JSON)
        schema.add_function(
            Function(
                name="content_bm25",
                input_field_names=["content"],
                output_field_names=["sparse_embedding"],
                function_type=FunctionType.BM25,
            )
        )

        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="HNSW",
            metric_type="COSINE",
            params={"M": 16, "efConstruction": 256},
        )
        index_params.add_index(
            field_name="sparse_embedding",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="BM25",
            params={
                "inverted_index_algo": "DAAT_MAXSCORE",
                "bm25_k1": 1.2,
                "bm25_b": 0.75,
            },
        )

        self.client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params,
        )
        self.client.load_collection(collection_name=self.collection_name)
        return True

    def _validate_existing_collection(self) -> None:
        description = self.client.describe_collection(
            collection_name=self.collection_name
        )
        fields = description.get("fields")
        if not isinstance(fields, list):
            raise ValueError(
                f"Collection '{self.collection_name}' description has no field list"
            )
        vector_field = next(
            (field for field in fields if field.get("name") == "embedding"),
            None,
        )
        if vector_field is None:
            raise ValueError(
                f"Collection '{self.collection_name}' has no 'embedding' field"
            )

        actual_dimension = vector_field.get("params", {}).get("dim")
        if actual_dimension is None or int(actual_dimension) != self.embedding_dimension:
            raise ValueError(
                f"Collection '{self.collection_name}' embedding dimension "
                f"does not match configured dimension {self.embedding_dimension}"
            )

    def insert_chunks(self, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        result = self.client.insert(
            collection_name=self.collection_name,
            data=records,
        )
        inserted_count = result.get("insert_count")
        if inserted_count is None or int(inserted_count) != len(records):
            raise RuntimeError(
                f"Milvus inserted {inserted_count} of {len(records)} chunks"
            )
        return int(inserted_count)

    def delete_document(self, document_id: UUID | str) -> int:
        safe_id = str(UUID(str(document_id)))
        result = self.client.delete(
            collection_name=self.collection_name,
            filter=f'document_id == "{safe_id}"',
        )
        return int(result.get("delete_count", 0))

    def hybrid_search(
        self,
        query: str,
        query_embedding: list[float],
        limit: int,
        document_id: UUID | str | None = None,
        owner_id: UUID | str | None = None,
    ) -> list[list[dict[str, Any]]]:
        filters: list[str] = []
        if owner_id is not None:
            filters.append(f'metadata["owner_id"] == "{UUID(str(owner_id))}"')
        if document_id is not None:
            filters.append(f'document_id == "{UUID(str(document_id))}"')
        expression = " and ".join(filters) if filters else None
        requests = [
            AnnSearchRequest(
                data=[query_embedding],
                anns_field="embedding",
                param={"metric_type": "COSINE", "params": {"ef": 64}},
                limit=limit,
                expr=expression,
            ),
            AnnSearchRequest(
                data=[query],
                anns_field="sparse_embedding",
                param={"metric_type": "BM25", "params": {}},
                limit=limit,
                expr=expression,
            ),
        ]
        return self.client.hybrid_search(
            collection_name=self.collection_name,
            reqs=requests,
            ranker=RRFRanker(k=60),
            limit=limit,
            output_fields=["document_id", "chunk_index", "content", "metadata"],
            consistency_level="Strong",
        )

    def close(self) -> None:
        self.client.close()
