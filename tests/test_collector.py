import time

import pytest
from prometheus_client import CollectorRegistry

from robotheus.collector import Collector
from robotheus.dedup import DeduplicationStore
from robotheus.metrics import MetricsUpdater
from robotheus.models import CostRecord, UsageRecord


class MockProvider:
    """
    A mock provider that returns pre-configured records.
    """

    def __init__(
        self,
        usage_records: "list[UsageRecord]",
        cost_records: "list[CostRecord]",
    ) -> "None":
        self._usage = usage_records
        self._costs = cost_records

    @property
    def name(self) -> "str":
        return "mock"

    async def fetch_usage(
        self,
        start_time: "int",
        end_time: "int",
    ) -> "list[UsageRecord]":
        return self._usage

    async def fetch_costs(
        self,
        start_time: "int",
        end_time: "int",
    ) -> "list[CostRecord]":
        return self._costs


class FailingProvider:
    """
    A mock provider that always raises on fetch.
    """

    @property
    def name(self) -> "str":
        return "failing"

    async def fetch_usage(
        self,
        start_time: "int",
        end_time: "int",
    ) -> "list[UsageRecord]":
        raise RuntimeError("usage fetch failed")

    async def fetch_costs(
        self,
        start_time: "int",
        end_time: "int",
    ) -> "list[CostRecord]":
        raise RuntimeError("cost fetch failed")


class TestCollector:
    @pytest.mark.asyncio
    async def test_collects_usage_and_cost(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        now = int(time.time())
        # bucket that has already completed
        past_end = now - 10

        usage = [
            UsageRecord(
                provider="fake",
                model="test-model",
                project="proj",
                api_key="key",
                input_tokens=10,
                output_tokens=5,
                request_count=1,
                bucket_start=past_end - 60,
                bucket_end=past_end,
            ),
        ]
        costs = [
            CostRecord(
                provider="fake",
                project="proj",
                amount_usd=0.01,
                bucket_start=past_end - 60,
                bucket_end=past_end,
            ),
        ]

        updater = MetricsUpdater(registry=registry)
        updater.register_provider("fake")
        dedup = DeduplicationStore()

        provider = MockProvider(usage, costs)
        collector = Collector([provider], updater, dedup)

        await collector._collect_provider(
            provider,
            past_end - 60,
            past_end,
            now,
        )

        requests_val = registry.get_sample_value(
            "robotheus_fake_requests_total",
            {"model": "test-model", "project": "proj", "api_key": "key"},
        )
        assert requests_val == 1.0

    @pytest.mark.asyncio
    async def test_skips_incomplete_buckets(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        now = int(time.time())
        # bucket that hasn't completed yet
        future_end = now + 600

        usage = [
            UsageRecord(
                provider="fake",
                model="test-model",
                project="proj",
                api_key="key",
                input_tokens=10,
                output_tokens=5,
                request_count=1,
                bucket_start=now,
                bucket_end=future_end,
            ),
        ]

        updater = MetricsUpdater(registry=registry)
        updater.register_provider("fake")
        dedup = DeduplicationStore()

        provider = MockProvider(usage, [])
        collector = Collector([provider], updater, dedup)

        await collector._collect_provider(provider, now, future_end, now)

        requests_val = registry.get_sample_value(
            "robotheus_fake_requests_total",
            {"model": "test-model", "project": "proj", "api_key": "key"},
        )
        # should be None since the bucket was skipped
        assert requests_val is None

    @pytest.mark.asyncio
    async def test_deduplicates_records(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        now = int(time.time())
        past_end = now - 10

        record = UsageRecord(
            provider="fake",
            model="test-model",
            project="proj",
            api_key="key",
            input_tokens=10,
            output_tokens=5,
            request_count=1,
            bucket_start=past_end - 60,
            bucket_end=past_end,
        )

        updater = MetricsUpdater(registry=registry)
        updater.register_provider("fake")
        dedup = DeduplicationStore()

        provider = MockProvider([record], [])
        collector = Collector([provider], updater, dedup)

        # collect twice
        await collector._collect_provider(provider, past_end - 60, past_end, now)
        await collector._collect_provider(provider, past_end - 60, past_end, now)

        requests_val = registry.get_sample_value(
            "robotheus_fake_requests_total",
            {"model": "test-model", "project": "proj", "api_key": "key"},
        )
        # should only be counted once
        assert requests_val == 1.0

    @pytest.mark.asyncio
    async def test_provider_error_does_not_crash(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        updater = MetricsUpdater(registry=registry)
        dedup = DeduplicationStore()

        provider = FailingProvider()
        collector = Collector([provider], updater, dedup)

        # should not raise
        await collector._collect_provider(provider, 0, 60, int(time.time()))
