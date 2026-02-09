import httpx
import pytest
import respx

from robotheus.provider.openai import OPENAI_BASE_URL, OpenAIProvider


class TestOpenAIProviderFetchUsage:
    @pytest.mark.asyncio
    @respx.mock
    async def test_fetches_and_parses_usage(self) -> "None":
        # mock a single completions endpoint response
        respx.get(f"{OPENAI_BASE_URL}/usage/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "start_time": 1000,
                            "end_time": 1060,
                            "results": [
                                {
                                    "project_id": "proj-1",
                                    "api_key_id": "key-1",
                                    "model": "gpt-4o",
                                    "input_tokens": 100,
                                    "output_tokens": 50,
                                    "num_model_requests": 2,
                                }
                            ],
                        }
                    ],
                    "has_more": False,
                },
            )
        )
        # mock the remaining 6 endpoints with empty data
        for endpoint in [
            "embeddings",
            "moderations",
            "images",
            "audio_speeches",
            "audio_transcriptions",
            "vector_stores",
        ]:
            respx.get(f"{OPENAI_BASE_URL}/usage/{endpoint}").mock(
                return_value=httpx.Response(
                    200,
                    json={"data": [], "has_more": False},
                )
            )

        # mock project name resolution
        respx.get(f"{OPENAI_BASE_URL}/projects/proj-1").mock(
            return_value=httpx.Response(
                200,
                json={"name": "My Project"},
            )
        )

        provider = OpenAIProvider(api_key="sk-test")
        records = await provider.fetch_usage(1000, 1060)

        assert len(records) == 1
        record = records[0]
        assert record.provider == "openai"
        assert record.model == "gpt-4o"
        assert record.project == "My Project"
        assert record.api_key_id == "key-1"
        assert record.input_tokens == 100
        assert record.output_tokens == 50
        assert record.request_count == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_handles_pagination(self) -> "None":
        # first page
        respx.get(f"{OPENAI_BASE_URL}/usage/completions").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "data": [
                            {
                                "start_time": 1000,
                                "end_time": 1060,
                                "results": [
                                    {
                                        "project_id": "proj-1",
                                        "model": "gpt-4o",
                                        "input_tokens": 10,
                                        "output_tokens": 5,
                                        "num_model_requests": 1,
                                    }
                                ],
                            }
                        ],
                        "has_more": True,
                        "next_page": "page2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "data": [
                            {
                                "start_time": 1060,
                                "end_time": 1120,
                                "results": [
                                    {
                                        "project_id": "proj-1",
                                        "model": "gpt-4o",
                                        "input_tokens": 20,
                                        "output_tokens": 10,
                                        "num_model_requests": 1,
                                    }
                                ],
                            }
                        ],
                        "has_more": False,
                    },
                ),
            ]
        )

        # mock empty responses for other endpoints
        for endpoint in [
            "embeddings",
            "moderations",
            "images",
            "audio_speeches",
            "audio_transcriptions",
            "vector_stores",
        ]:
            respx.get(f"{OPENAI_BASE_URL}/usage/{endpoint}").mock(
                return_value=httpx.Response(
                    200,
                    json={"data": [], "has_more": False},
                )
            )

        respx.get(f"{OPENAI_BASE_URL}/projects/proj-1").mock(
            return_value=httpx.Response(
                200,
                json={"name": "My Project"},
            )
        )

        provider = OpenAIProvider(api_key="sk-test")
        records = await provider.fetch_usage(1000, 1120)

        assert len(records) == 2
        assert records[0].input_tokens == 10
        assert records[1].input_tokens == 20


class TestOpenAIProviderFetchCosts:
    @pytest.mark.asyncio
    @respx.mock
    async def test_fetches_and_parses_costs(self) -> "None":
        respx.get(f"{OPENAI_BASE_URL}/costs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "start_time": 1000,
                            "end_time": 1060,
                            "results": [
                                {
                                    "project_id": "proj-1",
                                    "amount": {
                                        "value": 0.05,
                                        "currency": "usd",
                                    },
                                }
                            ],
                        }
                    ],
                    "has_more": False,
                },
            )
        )

        respx.get(f"{OPENAI_BASE_URL}/projects/proj-1").mock(
            return_value=httpx.Response(
                200,
                json={"name": "My Project"},
            )
        )

        provider = OpenAIProvider(api_key="sk-test")
        records = await provider.fetch_costs(1000, 1060)

        assert len(records) == 1
        assert records[0].provider == "openai"
        assert records[0].project == "My Project"
        assert records[0].amount_usd == 0.05


class TestOpenAIProviderProjectNameCache:
    @pytest.mark.asyncio
    @respx.mock
    async def test_caches_project_name(self) -> "None":
        # the endpoint should only be called once
        route = respx.get(f"{OPENAI_BASE_URL}/projects/proj-1").mock(
            return_value=httpx.Response(
                200,
                json={"name": "Cached Project"},
            )
        )

        provider = OpenAIProvider(api_key="sk-test")
        name1 = await provider._resolve_project_name("proj-1")
        name2 = await provider._resolve_project_name("proj-1")

        assert name1 == "Cached Project"
        assert name2 == "Cached Project"
        assert route.call_count == 1

    @pytest.mark.asyncio
    async def test_returns_unknown_for_empty_id(self) -> "None":
        provider = OpenAIProvider(api_key="sk-test")
        assert await provider._resolve_project_name("") == "unknown"
        assert await provider._resolve_project_name("unknown") == "unknown"
