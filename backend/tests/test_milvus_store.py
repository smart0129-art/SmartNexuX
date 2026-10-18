import unittest
from unittest.mock import Mock

from pymilvus import MilvusClient

from app.services.milvus_store import MilvusStore


class MilvusStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = Mock(spec=MilvusClient)
        self.client.has_collection.return_value = False
        self.client.create_schema.return_value = Mock()
        self.client.prepare_index_params.return_value = Mock()

    def test_creates_collection_with_dense_and_bm25_indexes(self) -> None:
        store = MilvusStore(
            collection_name="knowledge_chunks",
            embedding_dimension=768,
            client=self.client,
        )

        created = store.ensure_collection()

        self.assertTrue(created)
        self.client.create_collection.assert_called_once()
        self.assertEqual(self.client.prepare_index_params.return_value.add_index.call_count, 2)
        self.client.load_collection.assert_called_once_with(
            collection_name="knowledge_chunks"
        )

    def test_existing_collection_with_matching_dimension_is_reused(self) -> None:
        self.client.has_collection.return_value = True
        self.client.describe_collection.return_value = {
            "fields": [
                {"name": "embedding", "params": {"dim": 768}},
            ]
        }
        store = MilvusStore(embedding_dimension=768, client=self.client)

        created = store.ensure_collection()

        self.assertFalse(created)
        self.client.create_collection.assert_not_called()
        self.client.load_collection.assert_called_once()

    def test_existing_collection_with_different_dimension_is_rejected(self) -> None:
        self.client.has_collection.return_value = True
        self.client.describe_collection.return_value = {
            "fields": [
                {"name": "embedding", "params": {"dim": 1024}},
            ]
        }
        store = MilvusStore(embedding_dimension=768, client=self.client)

        with self.assertRaisesRegex(ValueError, "does not match"):
            store.ensure_collection()

        self.client.load_collection.assert_not_called()

    def test_non_positive_embedding_dimension_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            MilvusStore(embedding_dimension=0, client=self.client)

    def test_insert_chunks_requires_all_records_to_be_inserted(self) -> None:
        self.client.insert.return_value = {"insert_count": 2}
        store = MilvusStore(client=self.client)

        inserted = store.insert_chunks([{"id": "one"}, {"id": "two"}])

        self.assertEqual(inserted, 2)
        self.client.insert.assert_called_once()

    def test_hybrid_search_uses_dense_and_bm25_requests(self) -> None:
        self.client.hybrid_search.return_value = [[]]
        document_id = "61d3ce87-1670-49df-8f52-c10de8fbe33c"
        store = MilvusStore(client=self.client)

        result = store.hybrid_search(
            "search words",
            [0.1] * 768,
            limit=5,
            document_id=document_id,
            owner_id="9bf758f7-2e4f-42b3-98ac-37ae8e9d32ad",
        )

        self.assertEqual(result, [[]])
        request_args = self.client.hybrid_search.call_args.kwargs["reqs"]
        self.assertEqual(
            [request.anns_field for request in request_args],
            ["embedding", "sparse_embedding"],
        )
        self.assertTrue(
            all(
                request.expr
                == (
                    '(metadata["owner_id"] == '
                    '"9bf758f7-2e4f-42b3-98ac-37ae8e9d32ad" or '
                    'metadata["visibility"] == "shared") and '
                    f'document_id == "{document_id}"'
                )
                for request in request_args
            )
        )
        self.assertEqual(
            self.client.hybrid_search.call_args.kwargs["consistency_level"],
            "Strong",
        )

    def test_delete_document_uses_validated_document_id_filter(self) -> None:
        self.client.delete.return_value = {"delete_count": 3}
        store = MilvusStore(client=self.client)
        document_id = "61d3ce87-1670-49df-8f52-c10de8fbe33c"

        deleted = store.delete_document(document_id)

        self.assertEqual(deleted, 3)
        self.client.delete.assert_called_once_with(
            collection_name="knowledge_chunks",
            filter=f'document_id == "{document_id}"',
        )

    def test_shared_document_export_iterator_includes_shared_records(self) -> None:
        iterator = Mock()
        iterator.next.side_effect = [[{"chunk_index": 0}], []]
        self.client.query_iterator.return_value = iterator
        store = MilvusStore(client=self.client)
        owner_id = "9bf758f7-2e4f-42b3-98ac-37ae8e9d32ad"
        document_id = "61d3ce87-1670-49df-8f52-c10de8fbe33c"

        records = list(store.iter_document_chunks(owner_id, document_id, True))

        self.assertEqual(records, [{"chunk_index": 0}])
        self.client.query_iterator.assert_called_once_with(
            collection_name="knowledge_chunks",
            batch_size=256,
            filter=(
                f'document_id == "{document_id}" and '
                f'(metadata["owner_id"] == "{owner_id}" or '
                'metadata["visibility"] == "shared")'
            ),
            output_fields=[
                "document_id",
                "chunk_index",
                "content",
                "embedding",
                "metadata",
            ],
        )
        iterator.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
