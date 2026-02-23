import datetime
import time

import pytest
from prometheus_client import CollectorRegistry

from robotheus.collector import Collector
from robotheus.metrics import MetricsUpdater
from robotheus.models import CostRecord, UsageRecord
from robotheus.record_tracker import RecordTracker


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

    async def close(self) -> "None":
        pass


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

    async def close(self) -> "None":
        pass


class TestCollector:
    @pytest.mark.asyncio
    async def test_collects_usage_and_cost(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        now = int(time.time())
        # time frame that has already completed
        past_end = now - 10

        usage = [
            UsageRecord(
                provider="fake",
                model="test-model",
                project="proj",
                api_key_id="key",
                input_tokens=10,
                output_tokens=5,
                request_count=1,
                time_frame_start=past_end - 60,
                time_frame_end=past_end,
            ),
        ]
        costs = [
            CostRecord(
                provider="fake",
                project="proj",
                amount_usd=0.01,
                time_frame_start=past_end - 60,
                time_frame_end=past_end,
            ),
        ]

        updater = MetricsUpdater(registry=registry)
        updater.register_provider("fake")
        record_tracker = RecordTracker()

        provider = MockProvider(usage, costs)
        collector = Collector([provider], updater, record_tracker)

        await collector._collect_provider(
            provider,
            past_end - 60,
            past_end,
            now,
        )

        requests_val = registry.get_sample_value(
            "robotheus_fake_requests_total",
            {"model": "test-model", "project": "proj", "api_key_id": "key"},
        )
        assert requests_val == 1.0

        cost_val = registry.get_sample_value(
            "robotheus_fake_cost_usd_total",
            {"project": "proj"},
        )
        assert cost_val == 0.01

    @pytest.mark.asyncio
    async def test_skips_incomplete_time_frames(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        now = int(time.time())
        # time frame that hasn't completed yet
        future_end = now + 600

        usage = [
            UsageRecord(
                provider="fake",
                model="test-model",
                project="proj",
                api_key_id="key",
                input_tokens=10,
                output_tokens=5,
                request_count=1,
                time_frame_start=now,
                time_frame_end=future_end,
            ),
        ]

        updater = MetricsUpdater(registry=registry)
        updater.register_provider("fake")
        record_tracker = RecordTracker()

        provider = MockProvider(usage, [])
        collector = Collector([provider], updater, record_tracker)

        await collector._collect_provider(provider, now, future_end, now)

        requests_val = registry.get_sample_value(
            "robotheus_fake_requests_total",
            {"model": "test-model", "project": "proj", "api_key_id": "key"},
        )
        # should be None since the time frame was skipped
        assert requests_val is None

    @pytest.mark.asyncio
    async def test_deduplicates_usage_records(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        now = int(time.time())
        past_end = now - 10

        record = UsageRecord(
            provider="fake",
            model="test-model",
            project="proj",
            api_key_id="key",
            input_tokens=10,
            output_tokens=5,
            request_count=1,
            time_frame_start=past_end - 60,
            time_frame_end=past_end,
        )

        updater = MetricsUpdater(registry=registry)
        updater.register_provider("fake")
        record_tracker = RecordTracker()

        provider = MockProvider([record], [])
        collector = Collector([provider], updater, record_tracker)

        # collect twice
        await collector._collect_provider(provider, past_end - 60, past_end, now)
        await collector._collect_provider(provider, past_end - 60, past_end, now)

        requests_val = registry.get_sample_value(
            "robotheus_fake_requests_total",
            {"model": "test-model", "project": "proj", "api_key_id": "key"},
        )
        # should only be counted once
        assert requests_val == 1.0

    @pytest.mark.asyncio
    async def test_deduplicates_cost_records(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        now = int(time.time())
        past_end = now - 10

        cost = CostRecord(
            provider="fake",
            project="proj",
            amount_usd=0.05,
            time_frame_start=past_end - 60,
            time_frame_end=past_end,
        )

        updater = MetricsUpdater(registry=registry)
        updater.register_provider("fake")
        record_tracker = RecordTracker()

        provider = MockProvider([], [cost])
        collector = Collector([provider], updater, record_tracker)

        # collect twice
        await collector._collect_provider(provider, past_end - 60, past_end, now)
        await collector._collect_provider(provider, past_end - 60, past_end, now)

        cost_val = registry.get_sample_value(
            "robotheus_fake_cost_usd_total",
            {"project": "proj"},
        )
        # should only be counted once
        assert cost_val == 0.05

    @pytest.mark.asyncio
    async def test_provider_error_does_not_crash(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        updater = MetricsUpdater(registry=registry)
        record_tracker = RecordTracker()

        provider = FailingProvider()
        collector = Collector([provider], updater, record_tracker)

        # should not raise
        await collector._collect_provider(provider, 0, 60, int(time.time()))

    @pytest.mark.asyncio
    async def test_collect_cost_windows_aggregates_by_window(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        today = datetime.datetime.now(datetime.timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_start = int(today.timestamp())

        costs = [
            # today — inside all three windows
            CostRecord(
                provider="mock",
                project="proj",
                amount_usd=5.0,
                time_frame_start=today_start,
                time_frame_end=today_start + 86400,
            ),
            # yesterday — inside week and month, not today
            CostRecord(
                provider="mock",
                project="proj",
                amount_usd=3.0,
                time_frame_start=today_start - 86400,
                time_frame_end=today_start,
            ),
            # 8 days ago — inside month only
            CostRecord(
                provider="mock",
                project="proj",
                amount_usd=2.0,
                time_frame_start=today_start - 8 * 86400,
                time_frame_end=today_start - 7 * 86400,
            ),
        ]

        updater = MetricsUpdater(registry=registry)
        updater.register_provider("mock")
        provider = MockProvider([], costs)
        collector = Collector([provider], updater, RecordTracker())

        await collector._collect_cost_windows(provider)

        assert (
            registry.get_sample_value(
                "robotheus_mock_cost_usd_today", {"project": "proj"}
            )
            == 5.0
        )
        assert (
            registry.get_sample_value(
                "robotheus_mock_cost_usd_week", {"project": "proj"}
            )
            == 8.0
        )
        assert (
            registry.get_sample_value(
                "robotheus_mock_cost_usd_month", {"project": "proj"}
            )
            == 10.0
        )

    @pytest.mark.asyncio
    async def test_collect_cost_windows_sets_daily_gauge(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        today = datetime.datetime.now(datetime.timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_start = int(today.timestamp())
        today_str = today.strftime("%Y-%m-%d")
        yesterday_str = (today - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

        costs = [
            CostRecord(
                provider="mock",
                project="proj",
                amount_usd=5.0,
                time_frame_start=today_start,
                time_frame_end=today_start + 86400,
            ),
            CostRecord(
                provider="mock",
                project="proj",
                amount_usd=3.0,
                time_frame_start=today_start - 86400,
                time_frame_end=today_start,
            ),
        ]

        updater = MetricsUpdater(registry=registry)
        updater.register_provider("mock")
        provider = MockProvider([], costs)
        collector = Collector([provider], updater, RecordTracker())

        await collector._collect_cost_windows(provider)

        assert (
            registry.get_sample_value(
                "robotheus_mock_cost_usd_daily",
                {"project": "proj", "date": today_str},
            )
            == 5.0
        )
        assert (
            registry.get_sample_value(
                "robotheus_mock_cost_usd_daily",
                {"project": "proj", "date": yesterday_str},
            )
            == 3.0
        )

    @pytest.mark.asyncio
    async def test_collect_cost_windows_zeros_known_projects_with_no_data(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        updater = MetricsUpdater(registry=registry)
        updater.register_provider("mock")
        provider = MockProvider([], [])
        collector = Collector([provider], updater, RecordTracker())

        # simulate projects already seen from usage records
        collector._known_projects["mock"] = {"proj-a", "proj-b"}

        await collector._collect_cost_windows(provider)

        for project in ("proj-a", "proj-b"):
            assert (
                registry.get_sample_value(
                    "robotheus_mock_cost_usd_today", {"project": project}
                )
                == 0.0
            )
            assert (
                registry.get_sample_value(
                    "robotheus_mock_cost_usd_week", {"project": project}
                )
                == 0.0
            )
            assert (
                registry.get_sample_value(
                    "robotheus_mock_cost_usd_month", {"project": project}
                )
                == 0.0
            )

    @pytest.mark.asyncio
    async def test_window_collection_throttled_within_interval(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        now = int(time.time())
        today_start = int(
            datetime.datetime.now(datetime.timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
        )

        costs = [
            CostRecord(
                provider="mock",
                project="proj",
                amount_usd=5.0,
                time_frame_start=today_start,
                time_frame_end=today_start + 86400,
            ),
        ]

        updater = MetricsUpdater(registry=registry)
        updater.register_provider("mock")
        provider = MockProvider([], costs)
        collector = Collector(
            [provider], updater, RecordTracker(), cost_window_interval_seconds=1800
        )

        # last scrape happened 100s ago — interval not yet elapsed
        collector._last_window_scrape["mock"] = now - 100

        await collector._collect_provider(provider, now - 60, now, now)

        assert (
            registry.get_sample_value(
                "robotheus_mock_cost_usd_today", {"project": "proj"}
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_window_collection_runs_after_interval(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        now = int(time.time())
        today_start = int(
            datetime.datetime.now(datetime.timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
        )

        costs = [
            CostRecord(
                provider="mock",
                project="proj",
                amount_usd=5.0,
                time_frame_start=today_start,
                time_frame_end=today_start + 86400,
            ),
        ]

        updater = MetricsUpdater(registry=registry)
        updater.register_provider("mock")
        provider = MockProvider([], costs)
        collector = Collector(
            [provider], updater, RecordTracker(), cost_window_interval_seconds=1800
        )

        # last scrape happened 1801s ago — interval has elapsed
        collector._last_window_scrape["mock"] = now - 1801

        await collector._collect_provider(provider, now - 60, now, now)

        assert (
            registry.get_sample_value(
                "robotheus_mock_cost_usd_today", {"project": "proj"}
            )
            == 5.0
        )

    @pytest.mark.asyncio
    async def test_known_projects_populated_from_usage_and_cost_records(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        now = int(time.time())
        past_end = now - 10

        usage = [
            UsageRecord(
                provider="fake",
                model="gpt-4o",
                project="proj-from-usage",
                api_key_id="key",
                input_tokens=10,
                output_tokens=5,
                request_count=1,
                time_frame_start=past_end - 60,
                time_frame_end=past_end,
            ),
        ]
        costs = [
            CostRecord(
                provider="fake",
                project="proj-from-cost",
                amount_usd=1.0,
                time_frame_start=past_end - 60,
                time_frame_end=past_end,
            ),
        ]

        updater = MetricsUpdater(registry=registry)
        updater.register_provider("fake")
        provider = MockProvider(usage, costs)
        collector = Collector([provider], updater, RecordTracker())

        # prevent window collection (needs "mock" registered separately)
        collector._last_window_scrape["mock"] = now

        await collector._collect_provider(provider, past_end - 60, past_end, now)

        seen = collector._known_projects.get("mock", set())
        assert "proj-from-usage" in seen
        assert "proj-from-cost" in seen

    @pytest.mark.asyncio
    async def test_provider_error_increments_scrape_error_metric(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        updater = MetricsUpdater(registry=registry)
        record_tracker = RecordTracker()

        provider = FailingProvider()
        collector = Collector([provider], updater, record_tracker)

        await collector._collect_provider(provider, 0, 60, int(time.time()))

        usage_errors = registry.get_sample_value(
            "robotheus_scrape_errors_total",
            {"provider": "failing", "stage": "usage"},
        )
        cost_errors = registry.get_sample_value(
            "robotheus_scrape_errors_total",
            {"provider": "failing", "stage": "cost"},
        )
        assert usage_errors == 1.0
        assert cost_errors == 1.0
