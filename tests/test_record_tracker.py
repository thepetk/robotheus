from robotheus.record_tracker import RecordTracker


class TestRecordTrackerUsage:
    def test_first_call_returns_true(self) -> "None":
        store = RecordTracker()
        assert (
            store.is_new_usage(
                provider="openai",
                model="gpt-4o",
                project="proj-1",
                api_key_id="key-1",
                time_frame_start=1000,
            )
            is True
        )

    def test_second_call_same_key_returns_false(self) -> "None":
        store = RecordTracker()
        kwargs = dict(
            provider="openai",
            model="gpt-4o",
            project="proj-1",
            api_key_id="key-1",
            time_frame_start=1000,
        )
        store.is_new_usage(**kwargs)
        assert store.is_new_usage(**kwargs) is False

    def test_different_keys_are_independent(self) -> "None":
        store = RecordTracker()
        assert (
            store.is_new_usage(
                provider="openai",
                model="gpt-4o",
                project="proj-1",
                api_key_id="key-1",
                time_frame_start=1000,
            )
            is True
        )
        assert (
            store.is_new_usage(
                provider="openai",
                model="gpt-4o",
                project="proj-1",
                api_key_id="key-1",
                time_frame_start=2000,
            )
            is True
        )

    def test_different_providers_are_independent(self) -> "None":
        store = RecordTracker()
        assert (
            store.is_new_usage(
                provider="openai",
                model="gpt-4o",
                project="proj-1",
                api_key_id="key-1",
                time_frame_start=1000,
            )
            is True
        )
        assert (
            store.is_new_usage(
                provider="gemini",
                model="gpt-4o",
                project="proj-1",
                api_key_id="key-1",
                time_frame_start=1000,
            )
            is True
        )


class TestRecordTrackerCost:
    def test_first_call_returns_true(self) -> "None":
        store = RecordTracker()
        assert (
            store.is_new_cost(
                provider="openai",
                project="proj-1",
                time_frame_start=1000,
            )
            is True
        )

    def test_second_call_same_key_returns_false(self) -> "None":
        store = RecordTracker()
        kwargs = dict(
            provider="openai",
            project="proj-1",
            time_frame_start=1000,
        )
        store.is_new_cost(**kwargs)
        assert store.is_new_cost(**kwargs) is False

    def test_different_projects_are_independent(self) -> "None":
        store = RecordTracker()
        assert (
            store.is_new_cost(
                provider="openai",
                project="proj-1",
                time_frame_start=1000,
            )
            is True
        )
        assert (
            store.is_new_cost(
                provider="openai",
                project="proj-2",
                time_frame_start=1000,
            )
            is True
        )


class TestRecordTrackerEviction:
    def test_evicts_entries_before_cutoff(self) -> "None":
        store = RecordTracker()
        store.is_new_usage(
            provider="openai",
            model="gpt-4o",
            project="proj-1",
            api_key_id="key-1",
            time_frame_start=1000,
        )
        store.is_new_usage(
            provider="openai",
            model="gpt-4o",
            project="proj-1",
            api_key_id="key-1",
            time_frame_start=5000,
        )

        evicted = store.evict_before(3000)
        assert evicted == 1

        # the old entry should now be accepted again
        assert (
            store.is_new_usage(
                provider="openai",
                model="gpt-4o",
                project="proj-1",
                api_key_id="key-1",
                time_frame_start=1000,
            )
            is True
        )
        # the newer entry should still be seen
        assert (
            store.is_new_usage(
                provider="openai",
                model="gpt-4o",
                project="proj-1",
                api_key_id="key-1",
                time_frame_start=5000,
            )
            is False
        )

    def test_evict_returns_zero_when_nothing_to_evict(self) -> "None":
        store = RecordTracker()
        store.is_new_usage(
            provider="openai",
            model="gpt-4o",
            project="proj-1",
            api_key_id="key-1",
            time_frame_start=5000,
        )
        assert store.evict_before(1000) == 0
