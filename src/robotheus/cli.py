import argparse

from robotheus.config import Config


def parse_args(argv: "list[str] | None" = None) -> "Config":
    parser = argparse.ArgumentParser(
        prog="robotheus",
        description="Multi-provider AI Prometheus exporter",
    )
    parser.add_argument(
        "--web.listen-address",
        dest="listen_address",
        default=":9185",
        help="Address to listen on (default: :9185)",
    )
    parser.add_argument(
        "--scrape.interval",
        dest="scrape_interval",
        type=int,
        default=60,
        help="Scrape interval in seconds (default: 60)",
    )
    parser.add_argument(
        "--log.level",
        dest="log_level",
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="Log level (default: info)",
    )

    args = parser.parse_args(argv)
    config = Config.from_env()
    config.listen_address = args.listen_address
    config.scrape_interval = args.scrape_interval
    config.log_level = args.log_level
    return config
