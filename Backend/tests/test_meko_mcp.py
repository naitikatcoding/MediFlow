import json

import httpx

from app.integrations.meko import MekoAdapter


def make_mock_adapter(monkeypatch, tool_result):
    monkeypatch.setenv("RUN_LIVE_MEKO_TESTS", "1")
    requests = []

    def handle_request(request):
        body = json.loads(request.content)
        requests.append((request, body))
        if body["method"] == "initialize":
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "application/json",
                    "Mcp-Session-Id": "test-session",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "serverInfo": {"name": "meko", "version": "test"},
                    },
                },
            )
        if body["method"] == "notifications/initialized":
            return httpx.Response(202)
        if body["params"]["name"] == "conversation_create":
            result = {
                "result": json.dumps({"id": "conversation-123"}),
            }
        else:
            result = tool_result
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {"structuredContent": result},
            },
        )

    adapter = MekoAdapter(transport=httpx.MockTransport(handle_request))
    adapter.api_key = "mko_tkn_test"
    adapter.mcp_url = "https://mcp.mekodata.ai/mcp"
    adapter._local_store = []
    return adapter, requests


def test_store_context_uses_documented_meko_mcp_auth_and_memory_tool(monkeypatch):
    adapter, requests = make_mock_adapter(monkeypatch, {"memory_id": "memory-123"})

    result = adapter.store_context(
        summary="Apex has a 7-day critical medicine buffer.",
        facility_id="facility-1",
        tags=["baseline_policy"],
    )

    assert result["provenance"] == "LIVE_MEKO"
    assert result["cloud_id"] == "memory-123"
    assert adapter.get_status()["connection"] == "CONNECTED"

    request_headers = [request.headers for request, _ in requests]
    assert all(header["Authorization"] == "Bearer mko_tkn_test" for header in request_headers)
    assert all(header["User-Agent"] for header in request_headers)

    tool_call = next(
        body for _, body in requests
        if body["method"] == "tools/call" and body["params"]["name"] == "memory_add"
    )
    assert tool_call["params"]["name"] == "memory_add"
    assert tool_call["params"]["arguments"]["text"] == "Apex has a 7-day critical medicine buffer."
    assert tool_call["params"]["arguments"]["conversation_id"] == "conversation-123"
    metadata = json.loads(tool_call["params"]["arguments"]["metadata"])
    assert metadata["facility_id"] == "facility-1"
    memory_request = next(
        request for request, body in requests
        if body["method"] == "tools/call" and body["params"]["name"] == "memory_add"
    )
    assert memory_request.headers["Mcp-Session-Id"] == "test-session"
    assert memory_request.headers["MCP-Protocol-Version"] == "2025-03-26"


def test_retrieve_context_uses_meko_memory_search(monkeypatch):
    adapter, requests = make_mock_adapter(
        monkeypatch,
        {
            "results": [
                {
                    "memory_id": "memory-456",
                    "text": "Transfers are planned on Tuesdays.",
                    "metadata": {"facility_id": "facility-1"},
                }
            ]
        },
    )

    result = adapter.retrieve_context(
        facility_id="facility-1",
        query="transfer schedule",
        limit=3,
    )

    assert result[0]["ref_id"] == "memory-456"
    assert result[0]["summary"] == "Transfers are planned on Tuesdays."
    assert result[0]["provenance"] == "LIVE_MEKO"
    tool_call = next(
        body for _, body in requests
        if body["method"] == "tools/call" and body["params"]["name"] == "memory_search"
    )
    assert tool_call["params"]["name"] == "memory_search"
    assert tool_call["params"]["arguments"]["query"] == "transfer schedule"
    assert tool_call["params"]["arguments"]["limit"] == 3
    assert tool_call["params"]["arguments"]["conversation_id"] == "conversation-123"


def test_empty_live_search_does_not_invent_cloud_context(monkeypatch):
    adapter, _ = make_mock_adapter(monkeypatch, {"results": []})

    assert adapter.retrieve_context() == []
    assert adapter.get_status()["connection"] == "CONNECTED"


def test_meko_connection_errors_are_reported_and_fall_back_locally(monkeypatch):
    monkeypatch.setenv("RUN_LIVE_MEKO_TESTS", "1")

    def reject_request(_request):
        return httpx.Response(401)

    adapter = MekoAdapter(transport=httpx.MockTransport(reject_request))
    adapter.api_key = "mko_tkn_test"
    adapter._local_store = []

    result = adapter.store_context(summary="A synthetic local note.")

    assert result["provenance"] == "LOCAL_MEMORY_FALLBACK"
    assert adapter.get_status()["connection"] == "ERROR"
    assert "authentication or datapack access" in adapter.get_status()["connection_error"]
