import os
from dataclasses import dataclass


@dataclass
class Config:
    # listen_address: format ":9185" or
    # "0.0.0.0:9185"
    listen_address: "str" = ":9185"
    # collection interval in seconds
    scrape_interval: "int" = 60
    log_level: "str" = "info"

    openai_api_key: "str" = ""
    openai_org_id: "str" = ""

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
            openai_org_id=os.environ.get("OPENAI_ORG_ID", ""),
        )

    @property
    def openai_enabled(self) -> "bool":
        return bool(self.openai_api_key)
