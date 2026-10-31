"""MediFlow Agent Architecture State definitions."""
from typing import TypedDict, List, Dict, Any, Optional


class AgentState(TypedDict, total=False):
    facility_id: Optional[str]
    organization_id: Optional[str]
    risks_detected: List[Dict[str, Any]]
    surplus_candidates: List[Dict[str, Any]]
    proposed_transfers: List[Dict[str, Any]]
    meko_context: Dict[str, Any]
    status: str
    errors: List[str]
