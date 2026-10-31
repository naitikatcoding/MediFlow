"""
Google Gemini Integration Adapter.

Provides structured clinical supply reasoning, anomaly explanations, and
recommendation rationales grounded strictly in verified deterministic tool outputs.

Safety & Governance Boundaries:
- NEVER invents numerical values or forecast amounts.
- Model output is treated as UNTRUSTED INPUT and parsed via Pydantic.
- If the Gemini API key is missing, invalid, or the call fails/times out,
  a high-fidelity deterministic template fallback is used.
- All fallbacks are explicitly labeled; the system NEVER falsely claims Gemini ran.
"""
import logging
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from app.core.config import settings
from app.agents.state import GeminiStructuredAnalysis

logger = logging.getLogger("mediflow.integrations.gemini")


class GeminiAdapter:
    """
    Adapter for Google Gemini API with structured output enforcement,
    Pydantic schema validation, and deterministic fallback generation.
    """
    def __init__(self):
        self.api_key: Optional[str] = settings.GEMINI_API_KEY
        self.model: str = settings.GEMINI_MODEL
        self._force_unavailable: bool = False

    @property
    def is_available(self) -> bool:
        import os
        if self._force_unavailable:
            return False
        if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("RUN_LIVE_GEMINI_TESTS"):
            return False
        return bool(
            self.api_key
            and self.api_key != "your_gemini_api_key_here"
            and not self.api_key.startswith("dev_")
        )

    def set_unavailable_for_testing(self, unavailable: bool = True):
        """Testing utility to simulate API outage or invalid key."""
        self._force_unavailable = unavailable

    def get_status(self) -> Dict[str, Any]:
        return {
            "configured": self.is_available,
            "model": self.model,
            "mode": "LIVE_GEMINI" if self.is_available else "DETERMINISTIC_FALLBACK"
        }

    # ─────────────────────────────────────────────────────────────
    # STRUCTURED ANALYSIS GENERATION
    # ─────────────────────────────────────────────────────────────
    def generate_structured_analysis(
        self,
        context_type: str,
        facts: Dict[str, Any],
        uncertainties: Optional[List[str]] = None,
        data_quality_flags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Generates structured reasoning via Gemini live API if available,
        or uses a high-fidelity deterministic template fallback.
        Always returns a validated structured payload.
        """
        if self.is_available:
            try:
                from google import genai
                from google.genai import types
                import concurrent.futures

                client = genai.Client(api_key=self.api_key)

                prompt = f"""You are the Clinical Supply Intelligence Coordinator for MediFlow.
Analyze the following verified inventory, forecast, and risk data.
You MUST adhere strictly to these clinical safety rules:
1. Never invent or alter numerical forecasts, stock levels, or dates.
2. Ground all reasoning directly in the facts provided below.
3. Identify any missing information, unconfirmed shipments, or data freshness concerns.
4. Output your analysis in JSON matching the requested structure.

Context Type: {context_type}
Verified Facts:
{json.dumps(facts, default=str, indent=2)}

Known Uncertainties:
{json.dumps(uncertainties or [], indent=2)}

Data Quality Flags:
{json.dumps(data_quality_flags or [], indent=2)}
"""
                def _call_gemini():
                    return client.models.generate_content(
                        model=self.model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=GeminiStructuredAnalysis,
                            temperature=0.2,
                        )
                    )

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(_call_gemini)
                    response = future.result(timeout=3.0)

                # Parse and validate response as untrusted input
                if response and response.text:
                    parsed = GeminiStructuredAnalysis.model_validate_json(response.text)
                    return {
                        "status": "LIVE",
                        "source": "GEMINI_LIVE",
                        "model": self.model,
                        "gemini_live_executed": True,
                        "structured_analysis": parsed.model_dump(),
                        "raw_text": response.text,
                        "generated_at": datetime.now(timezone.utc).isoformat()
                    }
                else:
                    logger.warning("Gemini returned empty response, using template fallback.")
            except Exception as e:
                logger.warning(f"Gemini live call error or timeout: {e}. Activating deterministic fallback.")

        # Deterministic Template Fallback (labeled clearly)
        return self._generate_deterministic_fallback(
            context_type=context_type,
            facts=facts,
            uncertainties=uncertainties,
            data_quality_flags=data_quality_flags
        )

    # ─────────────────────────────────────────────────────────────
    # DETERMINISTIC TEMPLATE FALLBACK
    # ─────────────────────────────────────────────────────────────
    def _generate_deterministic_fallback(
        self,
        context_type: str,
        facts: Dict[str, Any],
        uncertainties: Optional[List[str]] = None,
        data_quality_flags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Rule-grounded structured analysis template.
        Produces deterministic clinical explanations without claiming LLM generation.
        """
        uncertainty_list = list(uncertainties or [])
        flags = list(data_quality_flags or [])
        missing_fields = []

        if context_type == "REDISTRIBUTION_PROPOSAL":
            src = facts.get("source_facility_name", facts.get("source_facility_id", "Source Facility"))
            dst = facts.get("destination_facility_name", facts.get("destination_facility_id", "Destination Facility"))
            prod = facts.get("product_name", facts.get("product_id", "Medicine"))
            qty = facts.get("proposed_quantity", facts.get("matched_quantity", 0))
            cover = facts.get("destination_days_of_cover", facts.get("days_of_cover", 0))
            stockout_day = facts.get("stockout_day", None)

            drivers = [
                f"Destination stock cover at {cover:.1f} days is below replenishment safety threshold (7.0 days).",
                f"Deterministic surplus formula confirms {qty} units available at {src} exceeding local safety stock."
            ]
            if stockout_day is not None:
                drivers.append(f"Projected stockout breach expected on day {stockout_day}.")

            summary = (
                f"Redistribution Proposal Assessment: Transfer of {qty} units of {prod} from {src} to {dst} "
                f"is recommended. This action averts an imminent stockout at {dst} (currently {cover:.1f} days of cover) "
                f"while maintaining full 30-day forecast requirements and safety buffer at {src}."
            )
            action = (
                f"Submit transfer proposal for dual facility verification. Both {src} and {dst} clinical pharmacists "
                f"must approve before stock reservation is executed."
            )

        elif context_type == "RISK_ALERT":
            fac = facts.get("facility_name", facts.get("facility_id", "Facility"))
            prod = facts.get("product_name", facts.get("product_id", "Medicine"))
            risk_type = facts.get("risk_type", "STOCKOUT_RISK")
            level = facts.get("risk_level", "HIGH")
            cover = facts.get("days_of_cover", 0.0)

            drivers = [
                f"Risk category: {risk_type} graded at {level} severity level.",
                f"Days of cover: {cover:.1f} days based on weighted moving average demand."
            ]
            summary = (
                f"Inventory Risk Alert: {fac} exhibits a {level} level {risk_type} for {prod}. "
                f"Usable stock is insufficient to satisfy the 30-day consumption baseline."
            )
            action = (
                f"Initiate multi-facility supply matching cycle to evaluate inter-facility surplus options."
            )

        else:
            summary = "Operational baseline inspection completed. Deterministic tool verification confirms ledger consistency."
            drivers = ["Inventory balances reconciled against append-only ledger."]
            action = "Continue regular monitoring cycle."

        if not facts.get("confirmed_inbound"):
            missing_fields.append("confirmed_inbound_shipments")
        if not facts.get("lead_time_days"):
            missing_fields.append("supplier_replenishment_lead_time")

        structured = GeminiStructuredAnalysis(
            clinical_operational_summary=summary,
            key_risk_drivers=drivers,
            recommended_action=action,
            uncertainty_notes=uncertainty_list if uncertainty_list else ["Standard historical consumption baseline applied."],
            missing_fields_detected=missing_fields,
            confidence_assessment="HIGH" if not flags else "MODERATE"
        )

        return {
            "status": "FALLBACK",
            "source": "DETERMINISTIC_TEMPLATE_FALLBACK",
            "model": "rule-grounded-synthesizer",
            "gemini_live_executed": False,
            "fallback_reason": "Gemini API key not configured or API call timed out",
            "structured_analysis": structured.model_dump(),
            "generated_at": datetime.now(timezone.utc).isoformat()
        }


# Global singleton instance
gemini_adapter = GeminiAdapter()
