from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UsageRecord:
    """
    UsageRecord represents a single usage data
    point from an AI provider.
    """

    provider: "str"
    model: "str"
    # note - resolved project name, not raw ID
    project: "str"
    # API key identifier, not the secret itself
    api_key_id: "str"
    input_tokens: "int"
    output_tokens: "int"
    request_count: "int"
    # unix timestamp marking the start of the time window
    time_frame_start: "int"
    # unix timestamp marking the end of the time window
    time_frame_end: "int"


@dataclass(frozen=True, slots=True)
class CostRecord:
    """
    CostRecord represents a single cost
    data point from a provider.
    """

    provider: "str"
    project: "str"
    amount_usd: "float"
    # unix timestamp marking the start of the time window
    time_frame_start: "int"
    # unix timestamp marking the end of the time window
    time_frame_end: "int"
