from app.services.milvus_store import MilvusStore


def main() -> None:
    store = MilvusStore()
    try:
        created = store.ensure_collection()
        state = "created" if created else "already exists"
        print(
            f"Collection '{store.collection_name}' {state} "
            f"(embedding dimension={store.embedding_dimension})."
        )
    finally:
        store.close()


if __name__ == "__main__":
    main()
