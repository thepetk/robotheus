import asyncio

import httpx
import structlog

from robotheus.models import CostRecord, UsageRecord

logger = structlog.get_logger()

OPENAI_BASE_URL = "https://api.openai.com/v1/organization"

# each tuple is (url_path, human-readable_name, group_by)
USAGE_ENDPOINTS: "list[tuple[str, str, str]]" = [
    ("completions", "completions", "project_id,api_key_id,model"),
    ("embeddings", "embeddings", "project_id,api_key_id,model"),
    ("moderations", "moderations", "project_id,api_key_id,model"),
    ("images", "images", "project_id,api_key_id,model"),
    ("audio_speeches", "audio_speeches", "project_id,api_key_id,model"),
    ("audio_transcriptions", "audio_transcriptions", "project_id,api_key_id,model"),
    ("vector_stores", "vector_stores", "project_id"),
]


class OpenAIProvider:
    """
    OpenAIProvider implements the AIProvider protocol for OpenAI's API. It fetches
    usage and cost data from OpenAI's usage and costs endpoints, handling pagination
    and caching project names for better readability in the records.
    """

    def __init__(self, api_key: "str", org_id: "str" = "") -> "None":
        self._api_key = api_key
        self._org_id = org_id
        headers: "dict[str, str]" = {"Authorization": f"Bearer {api_key}"}
        if org_id:
            headers["OpenAI-Organization"] = org_id
        self._client: "httpx.AsyncClient" = httpx.AsyncClient(
            timeout=10.0,
            headers=headers,
        )
        # caches: project_id -> project_name
        self._project_names: "dict[str, str]" = {}
        self._project_lock: "asyncio.Lock" = asyncio.Lock()

    @property
    def name(self) -> "str":
        return "openai"

    async def close(self) -> "None":
        """
        closes the underlying HTTP client.
        """
        await self._client.aclose()

    async def fetch_usage(
        self,
        start_time: "int",
        end_time: "int",
    ) -> "list[UsageRecord]":
        """
        fetches usage from all OpenAI endpoints concurrently.
        """
        tasks = [
            self._fetch_endpoint_usage(path, name, group_by, start_time, end_time)
            for path, name, group_by in USAGE_ENDPOINTS
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        records: "list[UsageRecord]" = []

        for result in results:
            if isinstance(result, BaseException):
                logger.error("openai_usage_endpoint_error", error=str(result))
                continue

            records.extend(result)

        return records

    async def _fetch_endpoint_usage(
        self,
        path: "str",
        endpoint_name: "str",
        group_by: "str",
        start_time: "int",
        end_time: "int",
    ) -> "list[UsageRecord]":
        """
        Fetch usage for a specific OpenAI endpoint, handling pagination.
        """
        records: "list[UsageRecord]" = []
        next_page = ""

        # while structure to handle pagination until no more
        # pages are available
        while True:
            url = (
                f"{OPENAI_BASE_URL}/usage/{path}"
                f"?start_time={start_time}&end_time={end_time}"
                f"&bucket_width=1m&limit=1440"
                f"&group_by={group_by}"
            )

            if next_page:
                url += f"&page={next_page}"

            logger.debug("openai_fetch_usage", url=url)
            resp = await self._client.get(url)

            if resp.status_code == 403:
                logger.debug(
                    "openai_endpoint_forbidden",
                    endpoint=endpoint_name,
                )
                return records
            resp.raise_for_status()

            data = resp.json()

            for bucket in data.get("data", []):
                for result in bucket.get("results", []):
                    project_id = result.get("project_id") or "unknown"
                    project_name = await self._resolve_project_name(project_id)
                    api_key_id = result.get("api_key_id") or "unknown"

                    records.append(
                        UsageRecord(
                            provider="openai",
                            model=result.get("model") or "unknown",
                            project=project_name,
                            api_key_id=api_key_id,
                            input_tokens=result.get("input_tokens", 0),
                            output_tokens=result.get("output_tokens", 0),
                            request_count=result.get("num_model_requests", 0),
                            time_frame_start=bucket["start_time"],
                            time_frame_end=bucket["end_time"],
                        )
                    )

            # break if there are no more pages to fetch
            if not data.get("has_more"):
                break

            next_page = data.get("next_page", "")

        logger.debug(
            "openai_usage_endpoint_done",
            endpoint=endpoint_name,
            record_count=len(records),
        )
        return records

    async def fetch_costs(
        self,
        start_time: "int",
        end_time: "int",
    ) -> "list[CostRecord]":
        """
        fetches cost data from the OpenAI Costs API.
        """
        records: "list[CostRecord]" = []
        next_page = ""

        # same pattern to avoid recursion and handle pagination
        while True:
            url = (
                f"{OPENAI_BASE_URL}/costs"
                f"?start_time={start_time}&end_time={end_time}"
                f"&bucket_width=1d&group_by=project_id"
            )
            if next_page:
                url += f"&page={next_page}"

            logger.debug("openai_fetch_costs", url=url)
            resp = await self._client.get(url)

            if resp.status_code == 403:
                logger.debug("openai_costs_forbidden")
                return records

            resp.raise_for_status()
            data = resp.json()

            for bucket in data.get("data", []):
                for result in bucket.get("results", []):
                    project_id = result.get("project_id") or "unknown"
                    project_name = await self._resolve_project_name(project_id)
                    amount = result.get("amount", {})

                    records.append(
                        CostRecord(
                            provider="openai",
                            project=project_name,
                            amount_usd=amount.get("value", 0.0),
                            time_frame_start=bucket["start_time"],
                            time_frame_end=bucket["end_time"],
                        )
                    )

            # break if there are no more pages to fetch
            if not data.get("has_more"):
                break

            next_page = data.get("next_page", "")

        logger.debug("openai_costs_done", record_count=len(records))
        return records

    async def _resolve_project_name(self, project_id: "str") -> "str":
        """
        resolves project ID to human-readable name, with caching.
        Uses a lock to prevent duplicate HTTP calls when multiple
        concurrent endpoints encounter the same project_id.
        """
        if project_id in ("", "unknown"):
            return "unknown"

        # fast path: check cache without lock
        if project_id in self._project_names:
            return self._project_names[project_id]

        async with self._project_lock:
            # re-check after acquiring lock (another task may have resolved it)
            if project_id in self._project_names:
                return self._project_names[project_id]

            try:
                resp = await self._client.get(
                    f"{OPENAI_BASE_URL}/projects/{project_id}"
                )

                if resp.status_code != 200:
                    return "unknown"

                name = str(resp.json().get("name", "unknown"))
                self._project_names[project_id] = name
                return name

            except Exception:
                logger.warning("openai_project_resolve_failed", project_id=project_id)
                return "unknown"
