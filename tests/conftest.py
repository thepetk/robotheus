import pytest
from prometheus_client import CollectorRegistry


@pytest.fixture()
def registry() -> "CollectorRegistry":
    """
    fresh Prometheus registry to avoid cross-test state.
    """
    return CollectorRegistry()
