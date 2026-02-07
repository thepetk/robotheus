import asyncio
import time

import structlog

from robotheus.dedup import DeduplicationStore
from robotheus.metrics import MetricsUpdater
from robotheus.provider.base import UsageProvider

logger = structlog.get_logger()


class Collector:
    """
    Collector is responsible for orchestrating the periodic
    collection of usage and cost data. It manages multiple
    providers, handles deduplication, and updates the metrics
    store with new records. The main collection loop runs indefinitely,
    sleeping for a configured interval between cycles.
    """

    def __init__(
        self,
        providers: "list[UsageProvider]",
        metrics_updater: "MetricsUpdater",
        dedup: "DeduplicationStore",
        scrape_interval_seconds: "int" = 60,
    ) -> "None":
        self._providers = providers
        self._metrics = metrics_updater
        self._dedup = dedup
        self._interval = scrape_interval_seconds
        self._last_scrape: "int" = 0

    async def run(self) -> "None":
        """
        runs the main collection loop. Runs indefinitely.
        """
        self._last_scrape = int(time.time()) - self._interval

        while True:
            start_time = self._last_scrape
            end_time = self._last_scrape + self._interval
            now = int(time.time())

            logger.info(
                "collection_cycle_start",
                start_time=start_time,
                end_time=end_time,
            )

            tasks = [
                self._collect_provider(provider, start_time, end_time, now)
                for provider in self._providers
            ]
            await asyncio.gather(*tasks)

            self._last_scrape = end_time
            logger.info("collection_cycle_end")
            await asyncio.sleep(self._interval)

    async def _collect_provider(
        self,
        provider: "UsageProvider",
        start_time: "int",
        end_time: "int",
        now: "int",
    ) -> "None":
        # collect usage data first since it's more time-sensitive.
        # Cost data may lag behind usage and we want to ensure we
        # capture all usage before costs.
        try:
            usage_records = await provider.fetch_usage(start_time, end_time)

            for record in usage_records:
                # skip buckets that haven't completed yet
                if record.bucket_end > now:
                    continue

                if self._dedup.is_new(
                    provider=record.provider,
                    model=record.model,
                    project=record.project,
                    api_key=record.api_key,
                    bucket_start=record.bucket_start,
                ):
                    self._metrics.update_usage(record)

        except Exception:
            logger.exception("usage_fetch_error", provider=provider.name)

        # collect cost data separately since some providers may not
        # support it or it may be less time-sensitive
        try:
            cost_records = await provider.fetch_costs(start_time, end_time)
            for record in cost_records:
                self._metrics.update_cost(record)

        except Exception:
            logger.exception("cost_fetch_error", provider=provider.name)
