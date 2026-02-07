import threading


class DeduplicationStore:
    """
    DeduplicationStore: Is a thread-safe store for tracking
    processed usage buckets.

    Prevents double-counting buckets by maintaining a set of
    keys taken from the bucket's metadata. Only completed
    buckets (bucket_end <= now) should be checked against this
    store.
    """

    def __init__(self) -> "None":
        self._lock: "threading.Lock" = threading.Lock()
        self._seen: "set[str]" = set()

    @staticmethod
    def make_key(
        provider: "str",
        model: "str",
        project: "str",
        api_key: "str",
        bucket_start: "int",
    ) -> "str":
        """
        constructs a unique key for a usage bucket based on its metadata.
        """
        return f"{provider}|{model}|{project}|{api_key}|{bucket_start}"

    def is_new(
        self,
        provider: "str",
        model: "str",
        project: "str",
        api_key: "str",
        bucket_start: "int",
    ) -> "bool":
        """
        checks if the given bucket is new. If so, mark it as seen
        and returns True.
        """
        key = self.make_key(provider, model, project, api_key, bucket_start)
        # lock to ensure thread-safety since multiple collection threads
        with self._lock:
            if key in self._seen:
                return False

            self._seen.add(key)
            return True
