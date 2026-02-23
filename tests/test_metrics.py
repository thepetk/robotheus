from prometheus_client import CollectorRegistry

from robotheus.metrics import MetricsUpdater
from robotheus.models import CostRecord, UsageRecord


class TestMetricsUpdater:
    def test_register_provider_creates_metrics(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        updater = MetricsUpdater(registry=registry)
        updater.register_provider("openai")
        # verify metric families are registered
        # prometheus_client strips _total suffix from Counter family names
        metric_names = [m.name for m in registry.collect()]
        assert "robotheus_openai_requests" in metric_names
        assert "robotheus_openai_tokens" in metric_names
        assert "robotheus_openai_cost_usd" in metric_names

    def test_update_usage_increments_counters(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        updater = MetricsUpdater(registry=registry)
        updater.register_provider("openai")

        record = UsageRecord(
            provider="openai",
            model="gpt-4o",
            project="my-project",
            api_key_id="key-1",
            input_tokens=100,
            output_tokens=50,
            request_count=3,
            time_frame_start=1000,
            time_frame_end=1060,
        )
        updater.update_usage(record)

        # check requests counter
        requests_value = registry.get_sample_value(
            "robotheus_openai_requests_total",
            {"model": "gpt-4o", "project": "my-project", "api_key_id": "key-1"},
        )
        assert requests_value == 3.0

        # check input tokens
        input_value = registry.get_sample_value(
            "robotheus_openai_tokens_total",
            {
                "model": "gpt-4o",
                "project": "my-project",
                "api_key_id": "key-1",
                "direction": "input",
            },
        )
        assert input_value == 100.0

        # check output tokens
        output_value = registry.get_sample_value(
            "robotheus_openai_tokens_total",
            {
                "model": "gpt-4o",
                "project": "my-project",
                "api_key_id": "key-1",
                "direction": "output",
            },
        )
        assert output_value == 50.0

    def test_update_cost_increments_counter(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        updater = MetricsUpdater(registry=registry)
        updater.register_provider("openai")

        record = CostRecord(
            provider="openai",
            project="my-project",
            amount_usd=1.50,
            time_frame_start=1000,
            time_frame_end=1060,
        )
        updater.update_cost(record)

        cost_value = registry.get_sample_value(
            "robotheus_openai_cost_usd_total",
            {"project": "my-project"},
        )
        assert cost_value == 1.50

    def test_duplicate_register_is_idempotent(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        updater = MetricsUpdater(registry=registry)
        updater.register_provider("openai")
        # should not raise
        updater.register_provider("openai")

    def test_self_metrics_are_created(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        MetricsUpdater(registry=registry)
        metric_names = [m.name for m in registry.collect()]
        assert "robotheus_scrape_duration_seconds" in metric_names
        assert "robotheus_scrape_errors" in metric_names
        assert "robotheus_last_scrape_success_timestamp_seconds" in metric_names

    def test_self_metrics_update(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        updater = MetricsUpdater(registry=registry)

        updater.observe_scrape_duration("openai", 0.5)
        updater.inc_scrape_error("openai", "usage")
        updater.set_last_scrape_success("openai", 1000.0)

        error_val = registry.get_sample_value(
            "robotheus_scrape_errors_total",
            {"provider": "openai", "stage": "usage"},
        )
        assert error_val == 1.0

        success_val = registry.get_sample_value(
            "robotheus_last_scrape_success_timestamp_seconds",
            {"provider": "openai"},
        )
        assert success_val == 1000.0

    def test_register_provider_creates_window_metrics(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        updater = MetricsUpdater(registry=registry)
        updater.register_provider("openai")
        metric_names = [m.name for m in registry.collect()]
        assert "robotheus_openai_cost_usd_today" in metric_names
        assert "robotheus_openai_cost_usd_week" in metric_names
        assert "robotheus_openai_cost_usd_month" in metric_names
        assert "robotheus_openai_cost_usd_daily" in metric_names

    def test_set_cost_window_sets_all_three_windows(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        updater = MetricsUpdater(registry=registry)
        updater.register_provider("openai")

        updater.set_cost_window("openai", "proj", "today", 5.0)
        updater.set_cost_window("openai", "proj", "week", 20.0)
        updater.set_cost_window("openai", "proj", "month", 80.0)

        assert (
            registry.get_sample_value(
                "robotheus_openai_cost_usd_today", {"project": "proj"}
            )
            == 5.0
        )
        assert (
            registry.get_sample_value(
                "robotheus_openai_cost_usd_week", {"project": "proj"}
            )
            == 20.0
        )
        assert (
            registry.get_sample_value(
                "robotheus_openai_cost_usd_month", {"project": "proj"}
            )
            == 80.0
        )

    def test_set_cost_window_overwrites_previous_value(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        updater = MetricsUpdater(registry=registry)
        updater.register_provider("openai")

        updater.set_cost_window("openai", "proj", "today", 5.0)
        updater.set_cost_window("openai", "proj", "today", 7.5)

        assert (
            registry.get_sample_value(
                "robotheus_openai_cost_usd_today", {"project": "proj"}
            )
            == 7.5
        )

    def test_set_cost_daily_sets_gauge(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        updater = MetricsUpdater(registry=registry)
        updater.register_provider("openai")

        updater.set_cost_daily("openai", "proj", "2026-02-23", 3.0)

        assert (
            registry.get_sample_value(
                "robotheus_openai_cost_usd_daily",
                {"project": "proj", "date": "2026-02-23"},
            )
            == 3.0
        )

    def test_set_cost_daily_multiple_dates_are_independent(
        self,
        registry: "CollectorRegistry",
    ) -> "None":
        updater = MetricsUpdater(registry=registry)
        updater.register_provider("openai")

        updater.set_cost_daily("openai", "proj", "2026-02-22", 4.0)
        updater.set_cost_daily("openai", "proj", "2026-02-23", 6.0)

        assert (
            registry.get_sample_value(
                "robotheus_openai_cost_usd_daily",
                {"project": "proj", "date": "2026-02-22"},
            )
            == 4.0
        )
        assert (
            registry.get_sample_value(
                "robotheus_openai_cost_usd_daily",
                {"project": "proj", "date": "2026-02-23"},
            )
            == 6.0
        )
