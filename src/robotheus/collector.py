import asyncio
import datetime
import time

import structlog

from robotheus.metrics import MetricsUpdater
from robotheus.provider.base import AIProvider
from robotheus.record_tracker import RecordTracker

logger = structlog.get_logger()

# keep tracked entries for 1 hour by default
_DEFAULT_EVICTION_AGE_SECONDS = 3600

# cost window gauges cover a 30-day range — no need to refresh every cycle
_DEFAULT_WINDOW_INTERVAL_SECONDS = 1800


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
        cost_window_interval_seconds: "int" = _DEFAULT_WINDOW_INTERVAL_SECONDS,
    ) -> "None":
        self._providers = providers
        self._metrics = metrics_updater
        self._record_tracker = record_tracker
        self._interval = scrape_interval_seconds
        self._window_interval = cost_window_interval_seconds
        self._last_scrape: "int" = 0
        self._stop_event: "asyncio.Event" = asyncio.Event()
        # tracks every project name seen per provider so window gauges
        # can be zeroed out when the cost API returns no data
        self._known_projects: "dict[str, set[str]]" = {}
        # unix timestamp of the last window scrape per provider;
        # 0 forces a run on the first cycle
        self._last_window_scrape: "dict[str, float]" = {}

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
                self._known_projects.setdefault(provider.name, set()).add(
                    record.project
                )
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
                self._known_projects.setdefault(provider.name, set()).add(
                    record.project
                )
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

        # update window-based cost gauges
        elapsed = now - self._last_window_scrape.get(provider.name, 0)

        # adding some throttle here just in case as cost metrics from
        # the provider side are not updated so frequently.
        if elapsed >= self._window_interval:
            try:
                await self._collect_cost_windows(provider)
                self._last_window_scrape[provider.name] = now
            except Exception:
                logger.exception("cost_windows_error", provider=provider.name)
                self._metrics.inc_scrape_error(provider.name, "cost_windows")

        duration = time.monotonic() - cycle_start
        self._metrics.observe_scrape_duration(provider.name, duration)

        if not had_error:
            self._metrics.set_last_scrape_success(provider.name, time.time())

    async def _collect_cost_windows(
        self,
        provider: "AIProvider",
    ) -> "None":
        """
        fetches the last 30 days of cost data and sets window gauges:
        cost_usd_total, cost_usd_today, cost_usd_week, cost_usd_month,
        and cost_usd_daily.
        """
        today = datetime.datetime.now(datetime.timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_start = int(today.timestamp())
        today_end = today_start + 86400
        week_start = today_start - 7 * 86400
        month_start = today_start - 30 * 86400

        records = await provider.fetch_costs(month_start, today_end)

        today_totals: "dict[str, float]" = {}
        week_totals: "dict[str, float]" = {}
        month_totals: "dict[str, float]" = {}
        # date string (YYYY-MM-DD) -> project -> total amount
        daily_totals: "dict[str, dict[str, float]]" = {}

        for record in records:
            p = record.project
            day_str = datetime.datetime.fromtimestamp(
                record.time_frame_start, tz=datetime.timezone.utc
            ).strftime("%Y-%m-%d")

            day_bucket = daily_totals.setdefault(day_str, {})
            day_bucket[p] = day_bucket.get(p, 0.0) + record.amount_usd

            if record.time_frame_start >= today_start:
                today_totals[p] = today_totals.get(p, 0.0) + record.amount_usd
            if record.time_frame_start >= week_start:
                week_totals[p] = week_totals.get(p, 0.0) + record.amount_usd
            month_totals[p] = month_totals.get(p, 0.0) + record.amount_usd

        # include every project ever seen so that missing data shows as 0
        all_projects = (
            self._known_projects.get(provider.name, set())
            | set(today_totals)
            | set(week_totals)
            | set(month_totals)
        )

        for project in all_projects:
            self._metrics.set_cost_window(
                provider.name, project, "today", today_totals.get(project, 0.0)
            )
            self._metrics.set_cost_window(
                provider.name, project, "week", week_totals.get(project, 0.0)
            )
            self._metrics.set_cost_window(
                provider.name, project, "month", month_totals.get(project, 0.0)
            )

        for day_str, project_amounts in daily_totals.items():
            for project, amount in project_amounts.items():
                self._metrics.set_cost_daily(provider.name, project, day_str, amount)
