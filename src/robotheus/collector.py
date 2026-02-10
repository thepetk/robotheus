import asyncio
import time

import structlog

from robotheus.metrics import MetricsUpdater
from robotheus.provider.base import AIProvider
from robotheus.record_tracker import RecordTracker

logger = structlog.get_logger()

# keep tracked entries for 1 hour by default
_DEFAULT_EVICTION_AGE_SECONDS = 3600


class Collector:
    """
    Collector is responsible for orchestrating the periodic
    collection of usage and cost data. It manages multiple
    providers, handles record tracking, and updates the metrics
    store with new records. The main collection loop runs indefinitely,
    sleeping for a configured interval between cycles.
    """

    def __init__(
        self,
        providers: "list[AIProvider]",
        metrics_updater: "MetricsUpdater",
        record_tracker: "RecordTracker",
        scrape_interval_seconds: "int" = 60,
    ) -> "None":
        self._providers = providers
        self._metrics = metrics_updater
        self._record_tracker = record_tracker
        self._interval = scrape_interval_seconds
        self._last_scrape: "int" = 0
        self._stop_event: "asyncio.Event" = asyncio.Event()

    def stop(self) -> "None":
        """
        signals the collector loop to stop after the current cycle.
        """
        self._stop_event.set()

    async def close(self) -> "None":
        """
        closes all provider sessions.
        """
        for p in self._providers:
            await p.close()

    async def run(self) -> "None":
        """
        runs the main collection loop. Runs until stop() is called.
        """
        self._last_scrape = int(time.time()) - self._interval

        while not self._stop_event.is_set():
            start_time = self._last_scrape
            end_time = self._last_scrape + self._interval
            now = int(time.time())

            logger.info(
                "collection_cycle_start",
                start_time=start_time,
                end_time=end_time,
            )

            # evict old tracked entries to prevent unbounded memory growth
            eviction_cutoff = now - _DEFAULT_EVICTION_AGE_SECONDS
            evicted = self._record_tracker.evict_before(eviction_cutoff)
            if evicted:
                logger.debug("records_evicted", count=evicted, cutoff=eviction_cutoff)

            tasks = [
                self._collect_provider(provider, start_time, end_time, now)
                for provider in self._providers
            ]
            await asyncio.gather(*tasks)

            self._last_scrape = end_time
            logger.info("collection_cycle_end")

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval)
            except TimeoutError:
                pass

    async def _collect_provider(
        self,
        provider: "AIProvider",
        start_time: "int",
        end_time: "int",
        now: "int",
    ) -> "None":
        cycle_start = time.monotonic()
        had_error = False

        # collect usage data first since it's more time-sensitive.
        # Cost data may lag behind usage and we want to ensure we
        # capture all usage before costs.
        try:
            usage_records = await provider.fetch_usage(start_time, end_time)

            for record in usage_records:
                # skip time frames that haven't completed yet
                if record.time_frame_end > now:
                    continue

                if self._record_tracker.is_new_usage(
                    provider=record.provider,
                    model=record.model,
                    project=record.project,
                    api_key_id=record.api_key_id,
                    time_frame_start=record.time_frame_start,
                ):
                    self._metrics.update_usage(record)

        except Exception:
            logger.exception("usage_fetch_error", provider=provider.name)
            self._metrics.inc_scrape_error(provider.name, "usage")
            had_error = True

        # collect cost data separately since some providers may not
        # support it or it may be less time-sensitive
        try:
            cost_records = await provider.fetch_costs(start_time, end_time)
            for record in cost_records:
                if record.time_frame_end > now:
                    continue

                delta = self._record_tracker.cost_delta(
                    provider=record.provider,
                    project=record.project,
                    time_frame_start=record.time_frame_start,
                    amount=record.amount_usd,
                )
                if delta > 0:
                    self._metrics.update_cost(record, delta)

        except Exception:
            logger.exception("cost_fetch_error", provider=provider.name)
            self._metrics.inc_scrape_error(provider.name, "cost")
            had_error = True

        duration = time.monotonic() - cycle_start
        self._metrics.observe_scrape_duration(provider.name, duration)

        if not had_error:
            self._metrics.set_last_scrape_success(provider.name, time.time())
