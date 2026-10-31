"""MEKO Shared Memory Adapter.
Provides MCP / REST client interface with clean local fallback when credentials are absent.
"""
import logging
from typing import Optional, Dict, Any
from app.core.config import settings

logger = logging.getLogger("mediflow.integrations.meko")


class MekoAdapter:
    def __init__(self):
        self.api_key: Optional[str] = settings.MEKO_API_KEY
        self.base_url: str = settings.MEKO_BASE_URL
        self.mcp_url: Optional[str] = settings.MEKO_MCP_URL
        self.datapack_id: Optional[str] = settings.MEKO_DATAPACK_ID
        self._is_available: bool = bool(self.api_key and self.api_key != "your_meko_api_key_here")

    @property
    def is_available(self) -> bool:
        return self._is_available

    def get_status(self) -> Dict[str, Any]:
        return {
            "configured": self.is_available,
            "base_url": self.base_url,
            "mcp_url": self.mcp_url,
            "datapack_id": self.datapack_id,
            "mode": "live" if self.is_available else "simulation_fallback"
        }


meko_adapter = MekoAdapter()
