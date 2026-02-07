from typing import Protocol, Sequence

from robotheus.models import CostRecord, UsageRecord


class UsageProvider(Protocol):
    """
    UsageProvider stands as a common protocol that all
    AI providers must satisfy.

    Providers fetch usage and cost data for a specific
    time window and return provider-agnostic record objects.
    """

    @property
    def name(self) -> "str": ...

    async def fetch_usage(
        self,
        start_time: "int",
        end_time: "int",
    ) -> "Sequence[UsageRecord]": ...

    async def fetch_costs(
        self,
        start_time: "int",
        end_time: "int",
    ) -> "Sequence[CostRecord]": ...
