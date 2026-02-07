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
            api_key="key-1",
            input_tokens=100,
            output_tokens=50,
            request_count=3,
            bucket_start=1000,
            bucket_end=1060,
        )
        updater.update_usage(record)

        # check requests counter
        requests_value = registry.get_sample_value(
            "robotheus_openai_requests_total",
            {"model": "gpt-4o", "project": "my-project", "api_key": "key-1"},
        )
        assert requests_value == 3.0

        # check input tokens
        input_value = registry.get_sample_value(
            "robotheus_openai_tokens_total",
            {
                "model": "gpt-4o",
                "project": "my-project",
                "api_key": "key-1",
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
                "api_key": "key-1",
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
            bucket_start=1000,
            bucket_end=1060,
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
