import threading


class RecordTracker:
    """
    RecordTracker: Is a thread-safe approach for tracking
    processed usage and cost time frames.

    Prevents double-counting time frames by maintaining a dict of
    keys taken from the time frame's metadata mapped to their
    time_frame_start timestamp. Only completed time frames
    (time_frame_end <= now) should be checked against this store.

    Supports time-based eviction via evict_before() to prevent
    unbounded memory growth.
    """

    def __init__(self) -> "None":
        self._lock: "threading.Lock" = threading.Lock()
        self._seen: "dict[str, int]" = {}

    @staticmethod
    def _make_usage_key(
        provider: "str",
        model: "str",
        project: "str",
        api_key_id: "str",
        time_frame_start: "int",
    ) -> "str":
        """
        constructs a unique key for a usage time frame based on its metadata.
        """
        return f"{provider}|{model}|{project}|{api_key_id}|{time_frame_start}"

    @staticmethod
    def _make_cost_key(
        provider: "str",
        project: "str",
        time_frame_start: "int",
    ) -> "str":
        """
        constructs a unique key for a cost time frame based on its metadata.
        """
        return f"{provider}|cost|{project}|{time_frame_start}"

    def is_new_usage(
        self,
        provider: "str",
        model: "str",
        project: "str",
        api_key_id: "str",
        time_frame_start: "int",
    ) -> "bool":
        """
        checks if the given usage time frame is new. If so, mark it as seen
        and returns True.
        """
        key = self._make_usage_key(
            provider, model, project, api_key_id, time_frame_start
        )
        with self._lock:
            if key in self._seen:
                return False
            self._seen[key] = time_frame_start
            return True

    def is_new_cost(
        self,
        provider: "str",
        project: "str",
        time_frame_start: "int",
    ) -> "bool":
        """
        checks if the given cost time frame is new. If so, mark it as seen
        and returns True.
        """
        key = self._make_cost_key(provider, project, time_frame_start)
        with self._lock:
            if key in self._seen:
                return False
            self._seen[key] = time_frame_start
            return True

    def evict_before(self, cutoff: "int") -> "int":
        """
        removes all entries with time_frame_start older than cutoff.
        Returns the number of evicted entries.
        """
        with self._lock:
            to_remove = [k for k, ts in self._seen.items() if ts < cutoff]
            for k in to_remove:
                del self._seen[k]
            return len(to_remove)
