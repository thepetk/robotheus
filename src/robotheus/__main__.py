import asyncio
import signal

import structlog
from prometheus_client import start_http_server

from robotheus.cli import parse_args
from robotheus.collector import Collector
from robotheus.logging import setup_logging
from robotheus.metrics import MetricsUpdater
from robotheus.provider.base import AIProvider
from robotheus.provider.openai import OpenAIProvider
from robotheus.record_tracker import RecordTracker

logger = structlog.get_logger()


def _parse_listen_address(addr: "str") -> "tuple[str, int]":
    """
    parses listen address in format ':9185' or '0.0.0.0:9185'.
    """
    if addr.startswith(":"):
        return ("0.0.0.0", int(addr[1:]))

    host, port = addr.rsplit(":", 1)
    return (host, int(port))


def main() -> "None":
    config = parse_args()
    setup_logging(config.log_level)

    metrics_updater = MetricsUpdater()
    record_tracker = RecordTracker()
    providers: "list[AIProvider]" = []

    if config.openai_enabled:
        provider = OpenAIProvider(
            api_key=config.openai_api_key,
            org_id=config.openai_org_id,
        )
        metrics_updater.register_provider("openai")
        providers.append(provider)
        logger.info("provider_enabled", provider="openai")

    if not providers:
        raise SystemExit(
            "No providers configured. Set OPENAI_API_KEY environment variable."
        )

    host, port = _parse_listen_address(config.listen_address)
    start_http_server(port, addr=host)
    logger.info("metrics_server_started", host=host, port=port)

    collector = Collector(
        providers, metrics_updater, record_tracker, config.scrape_interval
    )

    async def _run() -> "None":
        loop = asyncio.get_running_loop()
        # for SIGINT and SIGTERM, signal the collector
        # to stop gracefully
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, collector.stop)

        try:
            await collector.run()
        finally:
            logger.info("shutting_down")
            await collector.close()
            logger.info("shutdown_complete")

    asyncio.run(_run())


if __name__ == "__main__":
    main()
