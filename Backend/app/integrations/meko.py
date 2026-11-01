"""
MEKO Shared Memory Adapter.

Uses Meko's hosted MCP server for shared operational memory while keeping
inventory, eligibility, authorization, and transfer decisions in MediFlow.
"""
import json
import logging
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger("mediflow.integrations.meko")


class MekoProtocolError(RuntimeError):
    """Raised when the Meko MCP server returns an invalid or failed response."""


class MekoAdapter:
    """Meko MCP client with an explicit local-memory fallback."""

    _local_store: List[Dict[str, Any]] = []

    def __init__(self, transport: Optional[httpx.BaseTransport] = None):
        self.api_key: Optional[str] = settings.MEKO_API_KEY
        self.datapack_id: Optional[str] = settings.MEKO_DATAPACK_ID
        self.mcp_url = (
            settings.MEKO_MCP_URL.strip().rstrip("/")
            or "https://mcp.mekodata.ai/mcp"
        )
        self._transport = transport
        self._force_unavailable = False
        self._last_request_succeeded: Optional[bool] = None
        self._last_error: Optional[str] = None
        self._conversation_id: Optional[str] = None
        self._session_id = f"mediflow-{uuid.uuid4().hex}"
        self._conversation_lock = threading.Lock()

    @property
    def is_available(self) -> bool:
        import os

        if self._force_unavailable:
            return False
        if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("RUN_LIVE_MEKO_TESTS"):
            return False
        return bool(
            self.api_key
            and self.api_key != "your_meko_api_key_here"
            and not self.api_key.startswith("dev_")
        )

    def set_unavailable_for_testing(self, unavailable: bool = True):
        """Testing utility to simulate Meko being unconfigured or unavailable."""
        self._force_unavailable = unavailable

    def get_status(self) -> Dict[str, Any]:
        configured = self.is_available
        connected = configured and self._last_request_succeeded is True
        return {
            "configured": configured,
            "mcp_url": self.mcp_url,
            "datapack_id": self.datapack_id,
            "mode": "LIVE_MEKO" if connected else "LOCAL_FALLBACK",
            "connection": (
                "CONNECTED"
                if connected
                else "ERROR"
                if self._last_request_succeeded is False
                else "UNVERIFIED"
                if configured
                else "NOT_CONFIGURED"
            ),
            "connection_error": self._last_error,
            "local_records_count": len(self._local_store),
        }

    @staticmethod
    def _describe_error(error: Exception) -> str:
        if isinstance(error, httpx.HTTPStatusError):
            status_code = error.response.status_code
            if status_code in (401, 403):
                return (
                    f"Meko rejected authentication or datapack access (HTTP {status_code}). "
                    "Verify the full active API key and datapack access."
                )
            if status_code == 404:
                return "Meko MCP endpoint or tool was not found (HTTP 404). Verify MEKO_MCP_URL."
            if status_code == 429:
                return "Meko retrieval quota or rate limit was reached (HTTP 429)."
            if status_code >= 500:
                return f"Meko service is temporarily unavailable (HTTP {status_code})."
            return f"Meko rejected the MCP request (HTTP {status_code})."
        if isinstance(error, httpx.TimeoutException):
            return "Meko MCP request timed out; check network access and try again."
        if isinstance(error, httpx.RequestError):
            return "Could not reach the Meko MCP endpoint; check network, proxy, and TLS settings."
        if isinstance(error, MekoProtocolError):
            return str(error)[:300]
        return "Meko MCP request failed; check backend logs for details."

    def _record_error(self, operation: str, error: Exception) -> None:
        self._last_request_succeeded = False
        self._last_error = self._describe_error(error)
        logger.warning(
            "Meko %s failed (%s): %s",
            operation,
            type(error).__name__,
            self._last_error,
        )

    @staticmethod
    def _safe_error_detail(detail: Any) -> str:
        message = str(detail)
        message = re.sub(
            r"(?i)\bmko_tkn_[A-Za-z0-9._~-]+",
            "[redacted API key]",
            message,
        )
        message = re.sub(
            r"(?i)\bBearer\s+\S+",
            "Bearer [redacted]",
            message,
        )
        return message[:300]

    @staticmethod
    def _tool_error_message(tool_result: Dict[str, Any]) -> str:
        structured_content = tool_result.get("structuredContent")
        if isinstance(structured_content, dict):
            detail = structured_content.get("error") or structured_content.get("detail")
            if detail:
                return MekoAdapter._safe_error_detail(detail)

        for item in tool_result.get("content", []):
            if not isinstance(item, dict) or item.get("type") != "text":
                continue
            text_content = item.get("text", "")
            try:
                decoded_content = json.loads(text_content)
            except (TypeError, ValueError):
                return MekoAdapter._safe_error_detail(text_content)
            if isinstance(decoded_content, dict):
                detail = decoded_content.get("error") or decoded_content.get("detail")
                if detail:
                    return MekoAdapter._safe_error_detail(detail)
            return MekoAdapter._safe_error_detail(text_content)
        return "The tool returned an error without diagnostic details."

    @staticmethod
    def _unwrap_tool_result(value: Dict[str, Any]) -> Dict[str, Any]:
        nested_result = value.get("result")
        if set(value) == {"result"} and isinstance(nested_result, str):
            try:
                decoded_result = json.loads(nested_result)
            except ValueError:
                return {"text": nested_result}
            if isinstance(decoded_result, dict):
                return decoded_result
            if isinstance(decoded_result, list):
                return {"results": decoded_result}
            return {"text": nested_result}
        return value

    @staticmethod
    def _decode_response(
        response: httpx.Response,
        request_id: Optional[int],
    ) -> Optional[Dict[str, Any]]:
        if response.status_code == 202 and not response.content:
            return None
        response.raise_for_status()
        if not response.content:
            return None

        if "text/event-stream" in response.headers.get("content-type", "").lower():
            for line in response.text.splitlines():
                if not line.startswith("data:"):
                    continue
                try:
                    message = json.loads(line[5:].strip())
                except ValueError:
                    continue
                if request_id is None or message.get("id") == request_id:
                    return message
            raise MekoProtocolError("Meko MCP stream did not contain the expected response.")

        try:
            message = response.json()
        except ValueError as exc:
            raise MekoProtocolError("Meko MCP returned a non-JSON response.") from exc
        if not isinstance(message, dict):
            raise MekoProtocolError("Meko MCP returned an invalid JSON-RPC response.")
        return message

    def _call_mcp(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key:
            raise MekoProtocolError("Meko API key is not configured.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "MediFlow/1.0",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=20.0, transport=self._transport) as client:
            initialize_response = client.post(
                self.mcp_url,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "mediflow", "version": "1.0.0"},
                    },
                },
            )
            initialize = self._decode_response(initialize_response, 1)
            if not initialize:
                raise MekoProtocolError("Meko MCP did not complete initialization.")
            if "error" in initialize:
                raise MekoProtocolError(
                    "Meko MCP initialization failed: "
                    f"{self._safe_error_detail(initialize['error'])}"
                )
            initialize_result = initialize.get("result")
            protocol_version = (
                initialize_result.get("protocolVersion")
                if isinstance(initialize_result, dict)
                else None
            )
            if not protocol_version:
                raise MekoProtocolError("Meko MCP initialization omitted its protocol version.")

            session_id = initialize_response.headers.get("Mcp-Session-Id")
            if session_id:
                headers["Mcp-Session-Id"] = session_id
            headers["MCP-Protocol-Version"] = protocol_version

            initialized_response = client.post(
                self.mcp_url,
                headers=headers,
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            )
            initialized_response.raise_for_status()

            tool_response = client.post(
                self.mcp_url,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments},
                },
            )
            tool_message = self._decode_response(tool_response, 2)

        if not tool_message:
            raise MekoProtocolError("Meko MCP did not return a tool result.")
        if "error" in tool_message:
            raise MekoProtocolError(
                f"Meko MCP tool call failed: {self._safe_error_detail(tool_message['error'])}"
            )
        tool_result = tool_message.get("result")
        if not isinstance(tool_result, dict):
            raise MekoProtocolError(f"Meko MCP tool {tool_name} returned an error.")
        if tool_result.get("isError"):
            diagnostic = self._tool_error_message(tool_result)
            raise MekoProtocolError(
                f"Meko MCP tool {tool_name} failed: {diagnostic[:300]}"
            )

        structured_content = tool_result.get("structuredContent")
        if isinstance(structured_content, dict):
            normalized_content = self._unwrap_tool_result(structured_content)
            error_detail = normalized_content.get("error") or normalized_content.get("detail")
            if error_detail:
                raise MekoProtocolError(
                    f"Meko MCP tool {tool_name} failed: {self._safe_error_detail(error_detail)}"
                )
            self._last_request_succeeded = True
            self._last_error = None
            return normalized_content

        text_content = [
            item.get("text", "")
            for item in tool_result.get("content", [])
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        if len(text_content) == 1:
            try:
                decoded_content = json.loads(text_content[0])
            except ValueError:
                return {"text": text_content[0]}
            if isinstance(decoded_content, dict):
                return decoded_content
            if isinstance(decoded_content, list):
                decoded_content = self._unwrap_tool_result(decoded_content)
                error_detail = decoded_content.get("error") or decoded_content.get("detail")
                if error_detail:
                    raise MekoProtocolError(
                        f"Meko MCP tool {tool_name} failed: "
                        f"{self._safe_error_detail(error_detail)}"
                    )
                self._last_request_succeeded = True
                self._last_error = None
                return {"results": decoded_content}
            self._last_request_succeeded = True
            self._last_error = None
            return {"text": text_content[0]}
        self._last_request_succeeded = True
        self._last_error = None
        return {"text": "\n".join(text_content)}

    def _ensure_conversation_id(self) -> str:
        if self._conversation_id:
            return self._conversation_id

        with self._conversation_lock:
            if self._conversation_id:
                return self._conversation_id

            arguments: Dict[str, Any] = {
                "agent_id": "mediflow",
                "session_id": self._session_id,
                "title": "MediFlow operational context",
            }
            if self.datapack_id:
                arguments["datapack_id"] = self.datapack_id
            result = self._call_mcp("conversation_create", arguments)
            conversation_id = (
                result.get("conversation_id")
                or result.get("id")
                or (result.get("conversation") or {}).get("id")
            )
            if not isinstance(conversation_id, str) or not conversation_id:
                raise MekoProtocolError(
                    "Meko conversation_create did not return a conversation ID."
                )
            self._conversation_id = conversation_id
            return conversation_id

    @staticmethod
    def _sanitize_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Strip accidental PII or patient identifiers before storage."""
        pii_patterns = re.compile(
            r"(patient|mrn|ssn|dob|birth|name_first|name_last)",
            re.IGNORECASE,
        )
        sanitized = {}
        for key, value in data.items():
            if pii_patterns.search(key):
                continue
            if isinstance(value, dict):
                sanitized[key] = MekoAdapter._sanitize_data(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    MekoAdapter._sanitize_data(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                sanitized[key] = value
        return sanitized

    def store_context(
        self,
        summary: str,
        facility_id: Optional[str] = None,
        product_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Stores a non-sensitive operational summary in Meko or local memory."""
        now = datetime.now(timezone.utc)
        ref_id = f"meko_mem_{len(self._local_store) + 1}_{int(now.timestamp())}"
        clean_meta = self._sanitize_data(metadata or {})
        record = {
            "ref_id": ref_id,
            "summary": summary,
            "facility_id": facility_id,
            "product_id": product_id,
            "tags": tags or ["operational_planning"],
            "metadata": clean_meta,
            "created_at": now.isoformat(),
            "provenance": "LOCAL_MEMORY_FALLBACK",
        }

        if self.is_available:
            try:
                arguments: Dict[str, Any] = {
                    "text": summary,
                    "conversation_id": self._ensure_conversation_id(),
                    "agent_id": "mediflow",
                    "metadata": json.dumps({
                        **clean_meta,
                        "facility_id": facility_id,
                        "product_id": product_id,
                        "tags": tags or ["operational_planning"],
                    }),
                }
                if self.datapack_id:
                    arguments["datapack_id"] = self.datapack_id
                cloud_data = self._call_mcp("memory_add", arguments)
            except (httpx.HTTPError, MekoProtocolError, ValueError) as exc:
                self._record_error("memory_add", exc)
            else:
                record["cloud_id"] = (
                    cloud_data.get("memory_id")
                    or cloud_data.get("id")
                    or ref_id
                )
                record["provenance"] = "LIVE_MEKO"

        self._local_store.append(record)
        return record

    def retrieve_context(
        self,
        facility_id: Optional[str] = None,
        product_id: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Retrieves relevant operational summaries with source provenance."""
        limit = max(1, min(limit, 100))
        results: List[Dict[str, Any]] = []

        if self.is_available:
            try:
                arguments: Dict[str, Any] = {
                    "query": query or "MediFlow operational planning and coordination context",
                    "conversation_id": self._ensure_conversation_id(),
                    "agent_id": "mediflow",
                    "limit": limit,
                }
                if self.datapack_id:
                    arguments["datapack_id"] = self.datapack_id
                cloud_data = self._call_mcp("memory_search", arguments)
            except (httpx.HTTPError, MekoProtocolError, ValueError) as exc:
                self._record_error("memory_search", exc)
            else:
                items = (
                    cloud_data.get("results")
                    or cloud_data.get("memories")
                    or cloud_data.get("items")
                    or []
                )
                if isinstance(items, list):
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        metadata = item.get("metadata") or {}
                        if not isinstance(metadata, dict):
                            metadata = {}
                        record_facility_id = metadata.get("facility_id")
                        record_product_id = metadata.get("product_id")
                        if facility_id and record_facility_id and record_facility_id != facility_id:
                            continue
                        if product_id and record_product_id and record_product_id != product_id:
                            continue
                        summary = item.get("text") or item.get("summary") or item.get("content")
                        if not summary:
                            continue
                        results.append({
                            "ref_id": item.get("memory_id") or item.get("id"),
                            "summary": summary,
                            "facility_id": record_facility_id,
                            "retrieved_at": datetime.now(timezone.utc).isoformat(),
                            "provenance": "LIVE_MEKO",
                        })
                if results:
                    return results[:limit]

        filtered = self._local_store
        if facility_id:
            filtered = [
                record
                for record in filtered
                if record.get("facility_id") == facility_id or record.get("facility_id") is None
            ]
        if product_id:
            filtered = [
                record
                for record in filtered
                if record.get("product_id") == product_id or record.get("product_id") is None
            ]

        for record in reversed(filtered[-limit:]):
            results.append({
                "ref_id": record["ref_id"],
                "summary": record["summary"],
                "facility_id": record.get("facility_id"),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "provenance": "LOCAL_MEMORY_FALLBACK",
            })

        if (
            not results
            and self.is_available
            and self._last_request_succeeded is True
        ):
            return []

        if not results:
            now = datetime.now(timezone.utc)
            default_summary = (
                "Synthetic operational baseline: Regional hub prioritizes emergency care "
                "and maintains a 7-day buffer for critical antibiotics. Regular transfer "
                "windows are Tuesdays and Thursdays."
            )
            seeded = {
                "ref_id": f"meko_mem_{len(self._local_store) + 1}_{int(now.timestamp())}",
                "summary": default_summary,
                "facility_id": facility_id,
                "product_id": product_id,
                "tags": ["baseline_policy"],
                "metadata": {},
                "created_at": now.isoformat(),
                "provenance": "LOCAL_MEMORY_FALLBACK",
            }
            self._local_store.append(seeded)
            results.append({
                "ref_id": seeded["ref_id"],
                "summary": default_summary,
                "facility_id": facility_id,
                "retrieved_at": now.isoformat(),
                "provenance": seeded["provenance"],
            })

        return results[:limit]

    def record_decision_trace(self, trace: Dict[str, Any]) -> Dict[str, Any]:
        """Stores a privacy-sanitized decision summary in shared or local memory."""
        clean = self._sanitize_data(trace)
        record = self.store_context(
            summary=f"Action: {clean.get('action', 'CYCLE')} | Status: {clean.get('status', 'OK')}",
            tags=["decision_trace"],
            metadata=clean,
        )
        record["trace_details"] = clean
        return record


meko_adapter = MekoAdapter()
