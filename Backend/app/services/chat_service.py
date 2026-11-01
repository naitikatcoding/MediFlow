import hashlib
import logging
import math
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.core import database
from app.core.config import settings
from app.integrations.meko import meko_adapter
from app.models.inventory import FacilityBatchInventory
from app.models.organization import Facility
from app.models.product import Batch, Product

logger = logging.getLogger("mediflow.chat")

EMBEDDING_DIMENSIONS = 768
_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{1,}", re.IGNORECASE)
_STOP_WORDS = {
    "about", "available", "can", "could", "current", "does", "for", "from",
    "give", "have", "help", "how", "inventory", "is", "left", "me", "much",
    "of", "our", "please", "quantity", "remaining", "show", "stock", "tell",
    "the", "there", "this", "total", "what", "which", "with", "you",
}

KNOWLEDGE_CHUNKS = [
    {
        "id": "inventory-quantity",
        "title": "How inventory quantities are calculated",
        "content": (
            "MediFlow records on-hand, reserved, quarantined, and damaged quantities for "
            "each medicine batch at each facility. Ledger-usable quantity is the on-hand "
            "quantity minus reserved, quarantined, and damaged quantities, never below zero. "
            "A batch may still be blocked from transfer if it is expired or its quality "
            "status is not RELEASED. Live quantities must be read from the operational "
            "inventory database, not inferred from memory or old summaries."
        ),
    },
    {
        "id": "expiry-fefo",
        "title": "Expiry and FEFO handling",
        "content": (
            "MediFlow tracks expiry dates per manufacturer batch and orders eligible batches "
            "using FEFO: first expiry, first out. Expired, recalled, quarantined, damaged, "
            "and otherwise blocked batches must not be presented as transferable stock. "
            "Expiry-risk summaries are operational alerts, not clinical advice."
        ),
    },
    {
        "id": "forecast-risk",
        "title": "Demand forecasts and stockout risk",
        "content": (
            "MediFlow estimates medicine demand from historical facility consumption and "
            "uses deterministic rules to identify low days of cover, stockout risk, expiry "
            "risk, and surplus. Risk calculations are operational planning signals and do "
            "not replace staff review or clinical judgement."
        ),
    },
    {
        "id": "redistribution",
        "title": "Safe redistribution matching",
        "content": (
            "MediFlow compares facility surplus with another facility's forecast need. A "
            "candidate transfer is checked for protected source stock, destination need, "
            "batch shelf life, product policy, and storage compatibility such as cold-chain "
            "requirements. A match is a recommendation, not an executed transfer."
        ),
    },
    {
        "id": "approvals-transfer",
        "title": "Human approvals and transfer tracking",
        "content": (
            "A proposed redistribution requires human review and the required source and "
            "destination approvals before reservation and movement. Transfers are tracked "
            "through dispatch and receipt using serialized QR labels and auditable ledger "
            "events. The chatbot cannot approve, reserve, adjust, dispatch, or receive stock."
        ),
    },
    {
        "id": "facilities-products",
        "title": "Facilities, medicines, batches, and storage",
        "content": (
            "MediFlow models healthcare facilities, medicine products, manufacturer batches, "
            "facility batch balances, consumption history, proposals, approvals, and transfers. "
            "Products include generic name, strength, dosage form, base unit, storage "
            "requirements, and transfer policy. Medicine quantities are reported in their "
            "recorded units."
        ),
    },
    {
        "id": "data-sources",
        "title": "Operational data and assistant sources",
        "content": (
            "MediFlow uses YugabyteDB YSQL as the configured operational database when it is "
            "available, with a local SQLite development fallback. Live inventory answers are "
            "read from the current operational database. MEKO can supply relevant shared "
            "operational memory; otherwise the assistant searches its YugabyteDB pgvector "
            "knowledge index, then the local SQLite knowledge index."
        ),
    },
    {
        "id": "assistant-scope",
        "title": "Assistant scope and privacy",
        "content": (
            "The MediFlow assistant answers operational questions about medicines, inventory, "
            "facilities, forecasts, risks, transfers, and how the platform works. It is not a "
            "clinical decision tool and cannot provide patient-specific diagnosis, treatment, "
            "or dosing advice. Do not enter patient identifiers or other sensitive personal "
            "information. Chat transcripts are not saved by the chat API."
        ),
    },
]


def _sanitize_prompt_text(value: str) -> str:
    value = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[redacted email]", value)
    value = re.sub(r"\b(?:MRN|SSN|patient\s*id)\s*[:#-]?\s*[\w-]+\b", "[redacted identifier]", value, flags=re.I)
    phone_candidate = re.compile(r"\+?\d[\d\s().-]{7,}\d")
    value = phone_candidate.sub(
        lambda match: "[redacted phone]"
        if 10 <= sum(character.isdigit() for character in match.group()) <= 15
        else match.group(),
        value,
    )
    return value.strip()


def _lexical_embedding(content: str) -> List[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    tokens = [token.lower() for token in _TOKEN_PATTERN.findall(content)]
    for token in tokens:
        for feature in (token, f"^ {token} $"):
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            index = value % EMBEDDING_DIMENSIONS
            vector[index] += 1.0 if value & (1 << 8) else -1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


def _get_embeddings(contents: Sequence[str]) -> Tuple[str, List[List[float]]]:
    if settings.is_gemini_active:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(
                api_key=settings.GEMINI_API_KEY,
                http_options=types.HttpOptions(timeout=12000),
            )
            response = client.models.embed_content(
                model=settings.CHAT_EMBEDDING_MODEL,
                contents=list(contents),
                config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSIONS),
            )
            embeddings = [list(item.values or []) for item in (response.embeddings or [])]
            if len(embeddings) == len(contents) and all(
                len(embedding) == EMBEDDING_DIMENSIONS for embedding in embeddings
            ):
                return (
                    f"gemini:{settings.CHAT_EMBEDDING_MODEL}:{EMBEDDING_DIMENSIONS}",
                    embeddings,
                )
            logger.warning("Gemini returned an unexpected embedding shape; using local embeddings.")
        except Exception as exc:
            logger.warning(
                "Gemini embedding request failed (%s); using local lexical embeddings.",
                type(exc).__name__,
            )

    return "local-hash-768-v1", [_lexical_embedding(content) for content in contents]


def _format_vector(vector: Sequence[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


def _retrieve_yugabyte_chunks(question: str, limit: int = 5) -> List[Dict[str, str]]:
    if not database.is_yugabyte_active():
        return []

    model_name, embeddings = _get_embeddings(
        [question, *[chunk["content"] for chunk in KNOWLEDGE_CHUNKS]]
    )
    engine = database.get_engine()
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
            connection.exec_driver_sql(
                """
                CREATE TABLE IF NOT EXISTS mediflow_rag_chunks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    embedding vector NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            for chunk, embedding in zip(KNOWLEDGE_CHUNKS, embeddings[1:]):
                connection.execute(
                    text(
                        """
                        INSERT INTO mediflow_rag_chunks
                            (id, title, content, embedding_model, embedding, updated_at)
                        VALUES
                            (:id, :title, :content, :model, CAST(:embedding AS vector), now())
                        ON CONFLICT (id) DO UPDATE SET
                            title = EXCLUDED.title,
                            content = EXCLUDED.content,
                            embedding_model = EXCLUDED.embedding_model,
                            embedding = EXCLUDED.embedding,
                            updated_at = now()
                        """
                    ),
                    {
                        "id": chunk["id"],
                        "title": chunk["title"],
                        "content": chunk["content"],
                        "model": model_name,
                        "embedding": _format_vector(embedding),
                    },
                )
            matches = connection.execute(
                text(
                    """
                    SELECT id, title, content
                    FROM mediflow_rag_chunks
                    WHERE embedding_model = :model
                    ORDER BY embedding <=> CAST(:embedding AS vector)
                    LIMIT :limit
                    """
                ),
                {
                    "model": model_name,
                    "embedding": _format_vector(embeddings[0]),
                    "limit": limit,
                },
            ).mappings().all()
        return [
            {"id": row["id"], "title": row["title"], "content": row["content"]}
            for row in matches
        ]
    except Exception as exc:
        logger.warning(
            "YugabyteDB pgvector retrieval unavailable (%s); trying local SQLite knowledge.",
            type(exc).__name__,
        )
        return []


def _tokenize(value: str) -> List[str]:
    return [
        token.lower()
        for token in _TOKEN_PATTERN.findall(value)
        if token.lower() not in _STOP_WORDS
    ]


def _retrieve_local_chunks(question: str, limit: int = 5) -> List[Dict[str, str]]:
    engine = database.get_local_knowledge_engine()
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS mediflow_rag_chunks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        for chunk in KNOWLEDGE_CHUNKS:
            connection.execute(
                text(
                    """
                    INSERT INTO mediflow_rag_chunks (id, title, content, updated_at)
                    VALUES (:id, :title, :content, :updated_at)
                    ON CONFLICT(id) DO UPDATE SET
                        title = excluded.title,
                        content = excluded.content,
                        updated_at = excluded.updated_at
                    """
                ),
                {
                    **chunk,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        rows = connection.execute(
            text("SELECT id, title, content FROM mediflow_rag_chunks")
        ).mappings().all()

    query_tokens = set(_tokenize(question))
    scored = []
    for row in rows:
        content_tokens = _tokenize(f"{row['title']} {row['content']}")
        token_counts: Dict[str, int] = {}
        for token in content_tokens:
            token_counts[token] = token_counts.get(token, 0) + 1
        score = sum(
            min(3, token_counts.get(token, 0)) / max(1, len(content_tokens) ** 0.5)
            for token in query_tokens
        )
        if query_tokens and score > 0:
            scored.append((score, row))

    if not scored:
        scored = [(0.0, row) for row in rows if row["id"] in {"inventory-quantity", "assistant-scope"}]
    scored.sort(key=lambda item: (-item[0], item[1]["title"]))
    return [
        {"id": row["id"], "title": row["title"], "content": row["content"]}
        for _, row in scored[:limit]
    ]


def _retrieve_context(question: str, facility_id: Optional[str]) -> Tuple[str, List[Dict[str, str]]]:
    safe_question = _sanitize_prompt_text(question)
    if meko_adapter.is_available:
        meko_records = meko_adapter.retrieve_context(
            query=safe_question,
            facility_id=facility_id,
            limit=5,
        )
        live_records = [
            record for record in meko_records
            if record.get("provenance") == "LIVE_MEKO" and record.get("summary")
        ]
        if live_records:
            chunks = [
                {
                    "id": record.get("ref_id", "meko-memory"),
                    "title": "MEKO operational memory",
                    "content": str(record["summary"]),
                }
                for record in live_records
            ]
            return "meko", chunks

    if database.is_yugabyte_active():
        try:
            vector_chunks = _retrieve_yugabyte_chunks(safe_question)
            if vector_chunks:
                return "yugabyte_pgvector", vector_chunks
        except Exception:
            logger.exception("Unexpected error retrieving context from YugabyteDB pgvector.")

    local_chunks = _retrieve_local_chunks(safe_question)
    return "local_sqlite", local_chunks


def _live_inventory_context(
    db: Session,
    question: str,
    facility_id: Optional[str],
) -> Tuple[str, List[Dict[str, str]]]:
    terms = _tokenize(question)
    products: List[Product] = []
    if terms:
        conditions = []
        for term in terms[:8]:
            pattern = f"%{term}%"
            conditions.extend(
                (
                    Product.name.ilike(pattern),
                    Product.generic_name.ilike(pattern),
                    Product.internal_code.ilike(pattern),
                    Product.brand_name.ilike(pattern),
                )
            )
        products = (
            db.query(Product)
            .filter(Product.status == "ACTIVE", or_(*conditions))
            .order_by(Product.name.asc())
            .limit(5)
            .all()
        )

    now = datetime.now(timezone.utc)
    network_wide = any(
        phrase in question.lower()
        for phrase in ("all facilities", "across facilities", "network-wide", "entire network")
    )
    if network_wide:
        facility_id = None
    else:
        question_tokens = set(_tokenize(question))
        active_facilities = db.query(Facility).filter(Facility.status == "ACTIVE").all()
        mentioned_facility = next(
            (
                site
                for site in active_facilities
                if (
                    site.name.lower() in question.lower()
                    or (
                        len(_tokenize(site.name)) >= 2
                        and all(term in question_tokens for term in _tokenize(site.name))
                    )
                )
            ),
            None,
        )
        if mentioned_facility:
            facility_id = mentioned_facility.id
    facility = db.query(Facility).filter(Facility.id == facility_id).first() if facility_id else None
    context_lines = [
        f"Live database snapshot time: {now.isoformat()}.",
        f"Selected facility: {facility.name if facility else 'All network facilities'}.",
    ]
    sources: List[Dict[str, str]] = []

    if not products:
        product_count = db.query(Product).filter(Product.status == "ACTIVE").count()
        facility_count = db.query(Facility).filter(Facility.status == "ACTIVE").count()
        context_lines.append(
            f"The active operational database contains {product_count} active medicines "
            f"across {facility_count} active facilities. No specific medicine was confidently "
            "matched to the question; ask the user to clarify the medicine name or product code."
        )
    else:
        product_ids = [product.id for product in products]
        query = (
            db.query(FacilityBatchInventory, Batch, Product, Facility)
            .join(Batch, FacilityBatchInventory.batch_id == Batch.id)
            .join(Product, Batch.product_id == Product.id)
            .join(Facility, FacilityBatchInventory.facility_id == Facility.id)
            .filter(
                Product.id.in_(product_ids),
                Facility.status == "ACTIVE",
            )
        )
        if facility_id:
            query = query.filter(Facility.id == facility_id)
        inventory_rows = query.order_by(Product.name.asc(), Facility.name.asc(), Batch.expiry_date.asc()).limit(100).all()

        if not inventory_rows:
            names = ", ".join(product.name for product in products)
            context_lines.append(f"No recorded batch inventory was found for: {names}.")

        totals: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for inventory, batch, product, site in inventory_rows:
            key = (product.id, site.id)
            totals.setdefault(
                key,
                {
                    "product": product,
                    "facility": site,
                    "on_hand": 0,
                    "reserved": 0,
                    "quarantined": 0,
                    "damaged": 0,
                    "ledger_usable": 0,
                    "eligible": 0,
                    "batches": [],
                },
            )
            summary = totals[key]
            ledger_usable = max(
                0,
                inventory.on_hand_quantity
                - inventory.reserved_quantity
                - inventory.quarantined_quantity
                - inventory.damaged_quantity,
            )
            days_to_expiry = (batch.expiry_date - date.today()).days
            eligible = (
                ledger_usable
                if batch.quality_status == "RELEASED" and days_to_expiry >= 0
                else 0
            )
            summary["on_hand"] += inventory.on_hand_quantity
            summary["reserved"] += inventory.reserved_quantity
            summary["quarantined"] += inventory.quarantined_quantity
            summary["damaged"] += inventory.damaged_quantity
            summary["ledger_usable"] += ledger_usable
            summary["eligible"] += eligible
            summary["batches"].append(
                {
                    "lot": batch.manufacturer_lot_number,
                    "expiry": batch.expiry_date.isoformat(),
                    "days_to_expiry": days_to_expiry,
                    "quality_status": batch.quality_status,
                    "eligible": eligible,
                    "unit": inventory.unit,
                }
            )

        for summary in totals.values():
            product = summary["product"]
            site = summary["facility"]
            context_lines.append(
                f"{product.name} ({product.internal_code}) at {site.name}: "
                f"on hand {summary['on_hand']} {product.base_unit}; "
                f"reserved {summary['reserved']}; quarantined {summary['quarantined']}; "
                f"damaged {summary['damaged']}; ledger-usable {summary['ledger_usable']}; "
                f"eligible non-expired released stock {summary['eligible']}."
            )
            for batch in summary["batches"][:8]:
                context_lines.append(
                    f"  Batch {batch['lot']}: expires {batch['expiry']} "
                    f"({batch['days_to_expiry']} days), quality {batch['quality_status']}, "
                    f"eligible {batch['eligible']} {batch['unit']}."
                )
        sources.append(
            {
                "title": "Live inventory records",
                "source": "Operational database",
            }
        )

    return "\n".join(context_lines), sources


def _grounded_answer(
    question: str,
    inventory_context: str,
    chunks: Sequence[Dict[str, str]],
) -> str:
    normalized = question.lower()
    if any(term in normalized for term in ("dose", "dosage", "treat", "diagnos", "prescri")):
        return (
            "I can help with MediFlow inventory and operational information, but I can’t "
            "provide diagnosis, treatment, or dosing advice. Please consult an appropriately "
            "qualified clinician for patient-care decisions."
        )

    if "No specific medicine was confidently matched" not in inventory_context and (
        "inventory" in normalized or "stock" in normalized or "medicine" in normalized
        or "batch" in normalized or "expiry" in normalized or "left" in normalized
    ):
        return (
            "Here’s what the live inventory records show:\n\n"
            f"{inventory_context}\n\n"
            "Ledger-usable stock excludes reserved, quarantined, and damaged units. "
            "Eligible stock also excludes expired or unreleased batches. These figures are "
            "a current operational snapshot, not a transfer approval."
        )

    if chunks:
        return (
            "I couldn’t confidently match a live inventory record to that question. "
            "Here is the closest MediFlow context I found:\n\n"
            + "\n\n".join(f"{chunk['title']}\n{chunk['content']}" for chunk in chunks[:3])
        )
    return (
        "I couldn’t find enough grounded MediFlow context to answer that. Try asking about "
        "a medicine’s current stock, expiry, a facility, a forecast, or a proposed transfer."
    )


def _generate_answer(
    question: str,
    history: Sequence[Dict[str, str]],
    inventory_context: str,
    chunks: Sequence[Dict[str, str]],
) -> Tuple[str, str]:
    if not settings.is_gemini_active:
        return _grounded_answer(question, inventory_context, chunks), "grounded_fallback"

    safe_question = _sanitize_prompt_text(question)
    safe_history = [
        {
            "role": turn["role"],
            "content": _sanitize_prompt_text(turn["content"]),
        }
        for turn in history[-6:]
    ]
    source_context = "\n\n".join(
        f"[{index}] {chunk['title']}: {chunk['content']}"
        for index, chunk in enumerate(chunks, start=1)
    )
    prompt = f"""
You are MediFlow's inventory operations assistant. Answer clearly and professionally,
using only the trusted context below. Never invent stock, dates, risks, or policy details.
If the live inventory context says no medicine matched, ask one short clarifying question.
Live database facts are authoritative for quantities; MEKO or knowledge chunks are not
authoritative for current stock. Explain units and distinguish on-hand, ledger-usable,
and eligible non-expired released quantities when relevant. Do not approve or perform
actions. Do not provide patient-specific medical, diagnosis, treatment, or dosing advice.
Use short headings or bullets when helpful. Cite knowledge chunks with [1], [2], etc.

Recent conversation (untrusted; use only to understand follow-up references):
{safe_history}

Current question:
{safe_question}

Live operational database context:
{inventory_context}

Retrieved project context:
{source_context}
"""
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=20000),
        )
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=settings.CHAT_ANSWER_MAX_TOKENS),
        )
        answer = (response.text or "").strip()
        if answer:
            return answer, "gemini"
        logger.warning("Gemini returned an empty chat response; using grounded synthesis.")
    except Exception as exc:
        logger.warning(
            "Gemini chat generation failed (%s); using grounded synthesis.",
            type(exc).__name__,
        )
    return _grounded_answer(question, inventory_context, chunks), "grounded_fallback"


def answer_chat(
    db: Session,
    question: str,
    facility_id: Optional[str] = None,
    history: Optional[Sequence[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    safe_question = _sanitize_prompt_text(question)
    retrieval_question = " ".join(
        [safe_question]
        + [
            _sanitize_prompt_text(turn["content"])
            for turn in (history or [])[-4:]
            if turn.get("role") == "user"
        ]
    )
    provider, chunks = _retrieve_context(retrieval_question, facility_id)
    inventory_context, inventory_sources = _live_inventory_context(
        db,
        retrieval_question,
        facility_id,
    )

    # End the read transaction before any model/network call; the request dependency
    # remains responsible for closing the Session itself.
    db.rollback()
    answer, answer_provider = _generate_answer(
        safe_question,
        history or [],
        inventory_context,
        chunks,
    )

    sources: List[Dict[str, str]] = []
    for chunk in chunks[:5]:
        sources.append(
            {
                "title": chunk["title"],
                "source": {
                    "meko": "MEKO shared memory",
                    "yugabyte_pgvector": "YugabyteDB pgvector",
                    "local_sqlite": "Local MediFlow knowledge base",
                }[provider],
                "reference": chunk.get("id"),
            }
        )
    sources.extend(inventory_sources)

    return {
        "answer": answer,
        "sources": sources,
        "retrieval_provider": provider,
        "answer_provider": answer_provider,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
