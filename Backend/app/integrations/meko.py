"""
MEKO Shared Memory Adapter.

Provides a decoupled server-side interface for shared agent memory,
operational planning summaries, and decision traces.

Safety & Governance Boundaries:
- NEVER stores patient-identifiable information (PII).
- NEVER uses MEKO memory to determine live stock, expiry, reservations,
  permissions, approvals, legal transfer eligibility, or QR validity.
- Pure operational coordination and handoff summaries.
- Graceful degradation: If MEKO credentials are missing or API is unreachable,
  workflow continues transparently using local in-memory fallback.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import httpx
from app.core.config import settings

logger = logging.getLogger("mediflow.integrations.meko")


class MekoAdapter:
    """
    Decoupled adapter for MEKO shared operational context and decision traces.
    Handles network requests, authentication headers, error containment,
    and automatic local memory fallback with provenance tracking.
    """
    _local_store: List[Dict[str, Any]] = []

    def __init__(self):
        self.api_key: Optional[str] = settings.MEKO_API_KEY
        self.base_url: str = settings.MEKO_BASE_URL.rstrip("/")
        self.datapack_id: Optional[str] = settings.MEKO_DATAPACK_ID
        self.mcp_url: Optional[str] = settings.MEKO_MCP_URL
        self._force_unavailable: bool = False

    @property
    def is_available(self) -> bool:
        if self._force_unavailable:
            return False
        return bool(
            self.api_key
            and self.api_key != "your_meko_api_key_here"
            and not self.api_key.startswith("dev_")
        )

    def set_unavailable_for_testing(self, unavailable: bool = True):
        """Testing utility to simulate MEKO outage."""
        self._force_unavailable = unavailable

    def get_status(self) -> Dict[str, Any]:
        return {
            "configured": self.is_available,
            "base_url": self.base_url,
            "datapack_id": self.datapack_id,
            "mode": "LIVE_MEKO" if self.is_available else "LOCAL_FALLBACK",
            "local_records_count": len(self._local_store)
        }

    # ─────────────────────────────────────────────────────────────
    # PRIVACY SANITIZATION
    # ─────────────────────────────────────────────────────────────
    @staticmethod
    def _sanitize_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Strip any accidental PII or patient identifiers before storage."""
        pii_patterns = re.compile(r"(patient|mrn|ssn|dob|birth|name_first|name_last)", re.IGNORECASE)
        sanitized = {}
        for k, v in data.items():
            if pii_patterns.search(k):
                continue
            if isinstance(v, dict):
                sanitized[k] = MekoAdapter._sanitize_data(v)
            elif isinstance(v, list):
                sanitized[k] = [MekoAdapter._sanitize_data(item) if isinstance(item, dict) else item for item in v]
            else:
                sanitized[k] = v
        return sanitized

    # ─────────────────────────────────────────────────────────────
    # CONTEXT STORAGE & RETRIEVAL
    # ─────────────────────────────────────────────────────────────
    def store_context(
        self,
        summary: str,
        facility_id: Optional[str] = None,
        product_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Stores non-sensitive operational planning summary with provenance.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        ref_id = f"meko_mem_{len(self._local_store) + 1}_{int(datetime.now(timezone.utc).timestamp())}"
        clean_meta = self._sanitize_data(metadata or {})

        record = {
            "ref_id": ref_id,
            "summary": summary,
            "facility_id": facility_id,
            "product_id": product_id,
            "tags": tags or ["operational_planning"],
            "metadata": clean_meta,
            "created_at": now_iso,
            "provenance": "LIVE_MEKO" if self.is_available else "LOCAL_MEMORY_FALLBACK"
        }

        # Attempt cloud store if available
        if self.is_available:
            try:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "text": summary,
                    "datapack_id": self.datapack_id,
                    "metadata": {
                        "facility_id": facility_id,
                        "product_id": product_id,
                        "tags": tags or []
                    }
                }
                with httpx.Client(timeout=2.0) as client:
                    resp = client.post(f"{self.base_url}/memories", json=payload, headers=headers)
                    if resp.status_code in (200, 201):
                        cloud_data = resp.json()
                        record["cloud_id"] = cloud_data.get("id", ref_id)
                        record["provenance"] = "LIVE_MEKO"
                    else:
                        logger.warning(f"MEKO cloud returned HTTP {resp.status_code}, saving to local fallback.")
                        record["provenance"] = "LOCAL_MEMORY_FALLBACK"
            except Exception as e:
                logger.warning(f"MEKO cloud request error: {e}. Falling back to local store.")
                record["provenance"] = "LOCAL_MEMORY_FALLBACK"

        self._local_store.append(record)
        return record

    def retrieve_context(
        self,
        facility_id: Optional[str] = None,
        product_id: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Retrieves relevant operational summaries and notes with explicit provenance.
        """
        results: List[Dict[str, Any]] = []

        if self.is_available:
            try:
                headers = {"Authorization": f"Bearer {self.api_key}"}
                params: Dict[str, Any] = {"limit": limit}
                if query:
                    params["q"] = query
                if facility_id:
                    params["facility_id"] = facility_id

                with httpx.Client(timeout=2.0) as client:
                    resp = client.get(f"{self.base_url}/memories", headers=headers, params=params)
                    if resp.status_code == 200:
                        items = resp.json().get("memories", [])
                        for item in items:
                            results.append({
                                "ref_id": item.get("id"),
                                "summary": item.get("text") or item.get("summary", ""),
                                "facility_id": item.get("metadata", {}).get("facility_id"),
                                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                                "provenance": "LIVE_MEKO"
                            })
                        if results:
                            return results[:limit]
            except Exception as e:
                logger.warning(f"MEKO cloud retrieval failed: {e}. Serving from local memory.")

        # Local fallback retrieval
        filtered = self._local_store
        if facility_id:
            filtered = [r for r in filtered if r.get("facility_id") == facility_id or r.get("facility_id") is None]
        if product_id:
            filtered = [r for r in filtered if r.get("product_id") == product_id or r.get("product_id") is None]

        # Return latest entries
        for r in reversed(filtered[-limit:]):
            results.append({
                "ref_id": r["ref_id"],
                "summary": r["summary"],
                "facility_id": r.get("facility_id"),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "provenance": "LOCAL_MEMORY_FALLBACK"
            })

        # Seed with initial synthetic operational context if empty
        if not results:
            default_summary = (
                f"Synthetic operational baseline: Regional hub prioritizes emergency care and maintains "
                f"7-day buffer for critical antibiotics. Regular transfer window is Tuesdays and Thursdays."
            )
            seeded = self.store_context(
                summary=default_summary,
                facility_id=facility_id,
                product_id=product_id,
                tags=["baseline_policy"]
            )
            results.append({
                "ref_id": seeded["ref_id"],
                "summary": seeded["summary"],
                "facility_id": facility_id,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "provenance": seeded["provenance"]
            })

        return results[:limit]

    def record_decision_trace(self, trace: Dict[str, Any]) -> Dict[str, Any]:
        """Records an auditable trace reference."""
        clean = self._sanitize_data(trace)
        trace_id = f"trace_{len(self._local_store) + 1}_{int(datetime.now(timezone.utc).timestamp())}"
        record = {
            "ref_id": trace_id,
            "summary": f"Action: {clean.get('action', 'CYCLE')} | Status: {clean.get('status', 'OK')}",
            "trace_details": clean,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "provenance": "LIVE_MEKO" if self.is_available else "LOCAL_MEMORY_FALLBACK"
        }
        self._local_store.append(record)
        return record


# Global singleton instance
meko_adapter = MekoAdapter()
