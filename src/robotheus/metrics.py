from prometheus_client import REGISTRY, CollectorRegistry, Counter, Gauge, Histogram

from robotheus.models import CostRecord, UsageRecord


def create_provider_metrics(
    provider: "str",
    registry: "CollectorRegistry" = REGISTRY,
) -> "dict[str, Counter | Gauge]":
    """
    creates the metric families for a given provider.
     - requests_total: counts total API requests, labeled
     by model, project, api_key_id.
     - tokens_total: counts total tokens used, labeled by
     model, project, api_key_id, direction (input/output).
     - cost_usd_total: cumulative cost counter in USD, labeled by project.
     - cost_usd_today: gauge for cost since midnight UTC today, labeled by project.
     - cost_usd_week: gauge for cost over the last 7 days, labeled by project.
     - cost_usd_month: gauge for cost over the last 30 days, labeled by project.
     - cost_usd_daily: gauge for cost per calendar day (YYYY-MM-DD), labeled
     by project and date — used for week/month time series dashboards.
    """
    return {
        "requests_total": Counter(
            f"robotheus_{provider}_requests_total",
            f"Total API requests to {provider}",
            ["model", "project", "api_key_id"],
            registry=registry,
        ),
        "tokens_total": Counter(
            f"robotheus_{provider}_tokens_total",
            f"Total tokens used via {provider}",
            ["model", "project", "api_key_id", "direction"],
            registry=registry,
        ),
        "cost_usd_total": Counter(
            f"robotheus_{provider}_cost_usd_total",
            f"Total cost in USD for {provider} (cumulative since start)",
            ["project"],
            registry=registry,
        ),
        "cost_usd_today": Gauge(
            f"robotheus_{provider}_cost_usd_today",
            f"Total cost in USD for {provider} since midnight UTC today",
            ["project"],
            registry=registry,
        ),
        "cost_usd_week": Gauge(
            f"robotheus_{provider}_cost_usd_week",
            f"Total cost in USD for {provider} over the last 7 days",
            ["project"],
            registry=registry,
        ),
        "cost_usd_month": Gauge(
            f"robotheus_{provider}_cost_usd_month",
            f"Total cost in USD for {provider} over the last 30 days",
            ["project"],
            registry=registry,
        ),
        "cost_usd_daily": Gauge(
            f"robotheus_{provider}_cost_usd_daily",
            f"Total cost in USD for {provider} for a specific calendar day",
            ["project", "date"],
            registry=registry,
        ),
    }


class MetricsUpdater:
    """
    applies UsageRecord/CostRecord data to Prometheus counters and gauges.
    """

    def __init__(self, registry: "CollectorRegistry" = REGISTRY) -> "None":
        self._registry: "CollectorRegistry" = registry
        self._provider_metrics: "dict[str, dict[str, Counter | Gauge]]" = {}
        self._scrape_duration: "Histogram" = Histogram(
            "robotheus_scrape_duration_seconds",
            "Duration of provider scrape cycles",
            ["provider"],
            registry=registry,
        )
        self._scrape_errors: "Counter" = Counter(
            "robotheus_scrape_errors_total",
            "Total number of scrape errors by provider and stage",
            ["provider", "stage"],
            registry=registry,
        )
        self._last_scrape_success: "Gauge" = Gauge(
            "robotheus_last_scrape_success_timestamp_seconds",
            "Unix timestamp of last successful scrape per provider",
            ["provider"],
            registry=registry,
        )

    def register_provider(self, provider_name: "str") -> "None":
        """
        ensures metric families exist for the given provider.
        Should be called before processing any records for that
        provider.
        """
        if provider_name not in self._provider_metrics:
            self._provider_metrics[provider_name] = create_provider_metrics(
                provider_name, self._registry
            )

    def update_usage(self, record: "UsageRecord") -> "None":
        """
        updates the relevant counters based on the usage
        record's data.
        """
        metrics = self._provider_metrics[record.provider]
        labels = {
            "model": record.model,
            "project": record.project,
            "api_key_id": record.api_key_id,
        }
        metrics["requests_total"].labels(**labels).inc(record.request_count)
        metrics["tokens_total"].labels(**labels, direction="input").inc(
            record.input_tokens
        )
        metrics["tokens_total"].labels(**labels, direction="output").inc(
            record.output_tokens
        )

    def update_cost(self, record: "CostRecord", delta: "float | None" = None) -> "None":
        """
        updates the cost counter based on the cost record's data.
        If delta is provided, increments by that amount instead of
        the full record amount.
        """
        metrics = self._provider_metrics[record.provider]
        amount = delta if delta is not None else record.amount_usd
        metrics["cost_usd_total"].labels(project=record.project).inc(amount)

    def set_cost_window(
        self,
        provider: "str",
        project: "str",
        window: "str",
        amount: "float",
    ) -> "None":
        """
        sets the cost gauge for a given time window.
        window must be one of: "today", "week", "month".
        """
        metrics = self._provider_metrics[provider]
        gauge = metrics[f"cost_usd_{window}"]
        assert isinstance(gauge, Gauge)
        gauge.labels(project=project).set(amount)

    def set_cost_daily(
        self,
        provider: "str",
        project: "str",
        date: "str",
        amount: "float",
    ) -> "None":
        """
        sets the daily cost gauge for a specific date (YYYY-MM-DD).
        Used to populate per-day time series for week/month dashboards.
        """
        metrics = self._provider_metrics[provider]
        gauge = metrics["cost_usd_daily"]
        assert isinstance(gauge, Gauge)
        gauge.labels(project=project, date=date).set(amount)

    def observe_scrape_duration(
        self, provider: "str", duration_seconds: "float"
    ) -> "None":
        self._scrape_duration.labels(provider=provider).observe(duration_seconds)

    def inc_scrape_error(self, provider: "str", stage: "str") -> "None":
        self._scrape_errors.labels(provider=provider, stage=stage).inc()

    def set_last_scrape_success(self, provider: "str", timestamp: "float") -> "None":
        self._last_scrape_success.labels(provider=provider).set(timestamp)
