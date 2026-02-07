from robotheus.dedup import DeduplicationStore


class TestDeduplicationStore:
    def test_first_call_returns_true(self) -> "None":
        store = DeduplicationStore()
        assert (
            store.is_new(
                provider="openai",
                model="gpt-4o",
                project="proj-1",
                api_key="key-1",
                bucket_start=1000,
            )
            is True
        )

    def test_second_call_same_key_returns_false(self) -> "None":
        store = DeduplicationStore()
        kwargs = dict(
            provider="openai",
            model="gpt-4o",
            project="proj-1",
            api_key="key-1",
            bucket_start=1000,
        )
        store.is_new(**kwargs)
        assert store.is_new(**kwargs) is False

    def test_different_keys_are_independent(self) -> "None":
        store = DeduplicationStore()
        assert (
            store.is_new(
                provider="openai",
                model="gpt-4o",
                project="proj-1",
                api_key="key-1",
                bucket_start=1000,
            )
            is True
        )
        assert (
            store.is_new(
                provider="openai",
                model="gpt-4o",
                project="proj-1",
                api_key="key-1",
                bucket_start=2000,
            )
            is True
        )

    def test_different_providers_are_independent(self) -> "None":
        store = DeduplicationStore()
        assert (
            store.is_new(
                provider="openai",
                model="gpt-4o",
                project="proj-1",
                api_key="key-1",
                bucket_start=1000,
            )
            is True
        )
        assert (
            store.is_new(
                provider="gemini",
                model="gpt-4o",
                project="proj-1",
                api_key="key-1",
                bucket_start=1000,
            )
            is True
        )
