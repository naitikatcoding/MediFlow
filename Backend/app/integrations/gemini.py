"""Gemini API Integration Adapter.
Provides client configuration and graceful fallback when credentials are not configured.
"""
import logging
from typing import Optional, Dict, Any
from app.core.config import settings

logger = logging.getLogger("mediflow.integrations.gemini")


class GeminiAdapter:
    def __init__(self):
        self.api_key: Optional[str] = settings.GEMINI_API_KEY
        self.model: str = settings.GEMINI_MODEL
        self._is_available: bool = bool(self.api_key and self.api_key != "your_gemini_api_key_here")

    @property
    def is_available(self) -> bool:
        return self._is_available

    def get_status(self) -> Dict[str, Any]:
        return {
            "configured": self.is_available,
            "model": self.model,
            "mode": "live" if self.is_available else "simulation_fallback"
        }


gemini_adapter = GeminiAdapter()
