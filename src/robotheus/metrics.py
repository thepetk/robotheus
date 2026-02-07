from prometheus_client import REGISTRY, CollectorRegistry, Counter

from robotheus.models import CostRecord, UsageRecord


def create_provider_metrics(
    provider: "str",
    registry: "CollectorRegistry" = REGISTRY,
) -> "dict[str, Counter]":
    """
    creates the three metric families for a given provider.
     - requests_total: counts total API requests, labeled
     by model, project, api_key.
     - tokens_total: counts total tokens used, labeled by
     model, project, api_key, direction (input/output).
     - cost_usd_total: counts total cost in USD, labeled by
     project.
    """
    return {
        "requests_total": Counter(
            f"robotheus_{provider}_requests_total",
            f"Total API requests to {provider}",
            ["model", "project", "api_key"],
            registry=registry,
        ),
        "tokens_total": Counter(
            f"robotheus_{provider}_tokens_total",
            f"Total tokens used via {provider}",
            ["model", "project", "api_key", "direction"],
            registry=registry,
        ),
        "cost_usd_total": Counter(
            f"robotheus_{provider}_cost_usd_total",
            f"Total cost in USD for {provider}",
            ["project"],
            registry=registry,
        ),
    }


class MetricsUpdater:
    """
    applies UsageRecord/CostRecord data to Prometheus counters.
    """

    def __init__(self, registry: "CollectorRegistry" = REGISTRY) -> "None":
        self._registry: "CollectorRegistry" = registry
        self._provider_metrics: "dict[str, dict[str, Counter]]" = {}

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
            "api_key": record.api_key,
        }
        metrics["requests_total"].labels(**labels).inc(record.request_count)
        metrics["tokens_total"].labels(**labels, direction="input").inc(
            record.input_tokens
        )
        metrics["tokens_total"].labels(**labels, direction="output").inc(
            record.output_tokens
        )

    def update_cost(self, record: "CostRecord") -> "None":
        """
        updates the cost counter based on the cost record's data.
        """
        metrics = self._provider_metrics[record.provider]
        metrics["cost_usd_total"].labels(project=record.project).inc(record.amount_usd)
