"""Typed database query tools for the Q&A agent."""

from __future__ import annotations

import math
import re
from typing import Any

from db.client import get_supabase_client

_SERVICE_MATCH_FIELDS = ("service_name", "category", "value_text", "cost_summary")


def _latest_document_id() -> str:
    client = get_supabase_client()
    response = (
        client.table("documents")
        .select("id, source_filename, extracted_at")
        .order("extracted_at", desc=True)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise RuntimeError("No documents found in database. Run extraction first.")
    return response.data[0]["id"]


def _serialize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            key: (value.value if hasattr(value, "value") else value)
            for key, value in row.items()
            if key not in {"created_at"}
        }
        for row in rows
    ]


def _normalize_text(text: str) -> str:
    normalized = text.lower()
    normalized = re.sub(r"[—–\-]+", " ", normalized)
    normalized = re.sub(r"[^\w\s%$./]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _query_tokens(query: str) -> list[str]:
    return [token for token in _normalize_text(query).split() if token]


def _row_matches_query(row: dict[str, Any], query: str) -> bool:
    tokens = _query_tokens(query)
    if not tokens:
        return True
    haystack = " ".join(_normalize_text(str(row.get(field) or "")) for field in _SERVICE_MATCH_FIELDS)
    return all(token in haystack for token in tokens)


def _filter_rows_by_query(rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    if not query:
        return rows
    return [row for row in rows if _row_matches_query(row, query)]


def _row_haystack(row: dict[str, Any]) -> str:
    return " ".join(_normalize_text(str(row.get(field) or "")) for field in _SERVICE_MATCH_FIELDS)


def _row_token_score(row: dict[str, Any], query: str) -> int:
    tokens = _query_tokens(query)
    if not tokens:
        return 0
    haystack = _row_haystack(row)
    return sum(1 for token in tokens if token in haystack)


def _min_suggestion_score(token_count: int) -> int:
    if token_count <= 1:
        return 1
    return max(2, math.ceil(token_count * 0.4))


def _suggest_rows_by_query(rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    tokens = _query_tokens(query)
    if not tokens:
        return []
    min_score = _min_suggestion_score(len(tokens))
    return [row for row in rows if _row_token_score(row, query) >= min_score]


def _fee_clarification_options(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "service_name": str(row.get("service_name") or ""),
            "value_text": str(row.get("value_text") or row.get("cost_summary") or ""),
        }
        for row in rows
    ]


def _fetch_allowance_fee_rows(document_id: str) -> list[dict[str, Any]]:
    client = get_supabase_client()
    return (
        client.table("included_services")
        .select("*")
        .eq("document_id", document_id)
        .eq("source_section", "allowances_fees")
        .execute()
        .data
        or []
    )


def _fee_search_response(rows: list[dict[str, Any]], query: str) -> dict[str, Any]:
    if not rows:
        return {"status": "not_found", "message": f"No fees matched '{query}'."}
    if len(rows) > 1:
        return {
            "status": "needs_clarification",
            "message": "Multiple fees matched. Which service do you need?",
            "options": _fee_clarification_options(rows),
        }
    return {"status": "ok", "results": _serialize_rows(rows)}


def list_pricing_models() -> dict[str, Any]:
    client = get_supabase_client()
    models = client.table("pricing_models").select("*").execute().data or []
    return {
        "status": "ok",
        "pricing_models": models,
        "note": "Ask the user which model applies if not specified.",
    }


def list_networks() -> dict[str, Any]:
    client = get_supabase_client()
    networks = client.table("networks").select("*").execute().data or []
    return {"status": "ok", "networks": networks}


# Retail 30/90 are column headers under the Broad National grid in the PDF.
# Extraction stores them in contract_terms.channel, not network_id.
_RETAIL_CHANNELS = frozenset({"retail_30", "retail_90"})
_STANDALONE_NETWORKS = frozenset(
    {"mail", "retail_specialty", "exclusive_specialty", "northwind_direct_specialty"}
)


def _resolve_discount_location(
    *,
    network: str | None,
    channel: str | None,
) -> tuple[str | None, str | None]:
    """Map user-facing network/channel to DB filters (network_id, channel)."""
    if channel in _RETAIL_CHANNELS:
        return None, channel
    if network in _RETAIL_CHANNELS:
        return None, network
    if network in _STANDALONE_NETWORKS or network == "broad_national":
        return network, channel if channel in _RETAIL_CHANNELS else None
    if channel in _STANDALONE_NETWORKS:
        return channel, None
    return network, channel


def get_network_discount(
    *,
    pricing_model: str | None = None,
    channel: str | None = None,
    network: str | None = None,
    drug_type: str | None = None,
    year: int | None = None,
    metric: str = "discount",
) -> dict[str, Any]:
    if not pricing_model:
        return {
            "status": "needs_clarification",
            "message": "Which pricing model? Traditional or Applied Rebates?",
            "options": ["traditional", "applied_rebates"],
        }

    network_id, channel_id = _resolve_discount_location(network=network, channel=channel)
    if not network_id and not channel_id:
        return {
            "status": "needs_clarification",
            "message": (
                "Which pharmacy network or retail channel? "
                "Use retail_30 or retail_90 for retail discounts; "
                "mail, retail_specialty, or exclusive_specialty for other networks."
            ),
            "options": ["retail_30", "retail_90", "mail", "retail_specialty", "exclusive_specialty"],
        }
    if network_id == "broad_national" and not channel_id:
        return {
            "status": "needs_clarification",
            "message": "Broad National has separate Retail 30 and Retail 90 discounts. Which channel?",
            "options": ["retail_30", "retail_90"],
        }

    if not drug_type:
        return {
            "status": "needs_clarification",
            "message": "Which drug type?",
            "options": ["brand", "generic", "ldd", "new_to_market"],
        }
    if not year:
        return {
            "status": "needs_clarification",
            "message": "Which calendar year?",
            "options": [2024, 2025, 2026, 2027],
        }

    term_category = "dispensing_fee" if metric == "dispensing_fee" else "network_discount"
    document_id = _latest_document_id()
    client = get_supabase_client()

    def _base_discount_query():
        return (
            client.table("contract_terms")
            .select("*")
            .eq("document_id", document_id)
            .eq("pricing_model_id", pricing_model)
            .eq("drug_type", drug_type)
            .eq("calendar_year", year)
            .eq("term_category", term_category)
        )

    rows: list[dict[str, Any]] = []
    if channel_id and not network_id:
        rows = _base_discount_query().eq("channel", channel_id).execute().data or []
        if not rows:
            rows = _base_discount_query().eq("network_id", channel_id).execute().data or []
    elif network_id:
        query = _base_discount_query().eq("network_id", network_id)
        if channel_id:
            query = query.eq("channel", channel_id)
        rows = query.execute().data or []
    if not rows:
        return {
            "status": "not_found",
            "message": "No matching discount found in contract data.",
            "query": {
                "pricing_model": pricing_model,
                "network_id": network_id,
                "channel": channel_id,
                "drug_type": drug_type,
                "year": year,
                "metric": metric,
            },
        }
    return {"status": "ok", "results": _serialize_rows(rows)}


def get_rebate_guarantee(
    *,
    payment_schedule: str | None = None,
    channel: str | None = None,
    year: int | None = None,
) -> dict[str, Any]:
    if not payment_schedule:
        return {
            "status": "needs_clarification",
            "message": "Which rebate payment schedule?",
            "options": [
                {"id": "quarterly_150d", "label": "150 days after the quarter"},
                {"id": "monthly_60d", "label": "60 days after the month"},
            ],
        }
    if not channel:
        return {
            "status": "needs_clarification",
            "message": "Which rebate channel?",
            "options": ["retail_30", "retail_90", "mail", "specialty"],
        }
    if not year:
        return {
            "status": "needs_clarification",
            "message": "Which calendar year?",
            "options": [2025, 2026, 2027],
        }

    document_id = _latest_document_id()
    client = get_supabase_client()
    rows = (
        client.table("contract_terms")
        .select("*")
        .eq("document_id", document_id)
        .eq("term_category", "rebate")
        .eq("payment_schedule", payment_schedule)
        .eq("channel", channel)
        .eq("calendar_year", year)
        .execute()
        .data
        or []
    )
    if not rows:
        return {"status": "not_found", "message": "No matching rebate guarantee found."}
    return {"status": "ok", "results": _serialize_rows(rows)}


def search_fees(query: str) -> dict[str, Any]:
    document_id = _latest_document_id()
    all_rows = _fetch_allowance_fee_rows(document_id)
    rows = _filter_rows_by_query(all_rows, query)
    if not rows:
        rows = _suggest_rows_by_query(all_rows, query)
    return _fee_search_response(rows, query)


def get_included_services(
    category: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    document_id = _latest_document_id()
    client = get_supabase_client()
    request = (
        client.table("included_services")
        .select("*")
        .eq("document_id", document_id)
        .eq("source_section", "included_services")
    )
    if category:
        request = request.ilike("category", f"%{category}%")
    rows = request.execute().data or []
    if query:
        rows = _filter_rows_by_query(rows, query)

    fee_request = (
        client.table("included_services")
        .select("*")
        .eq("document_id", document_id)
        .eq("source_section", "allowances_fees")
    )
    if category:
        fee_request = fee_request.ilike("category", f"%{category}%")
    fee_rows = fee_request.execute().data or []
    if query:
        fee_rows = _filter_rows_by_query(fee_rows, query)

    if query and rows and fee_rows:
        return {
            "status": "needs_clarification",
            "message": (
                "This topic appears both as an included service and as a priced fee. "
                "Are you asking whether it is included, or how much the fee costs?"
            ),
            "options": {
                "included_services": _serialize_rows(rows),
                "related_fees": _serialize_rows(fee_rows),
            },
        }

    if query and not rows and not fee_rows:
        all_fees = _fetch_allowance_fee_rows(document_id)
        suggested_fees = _suggest_rows_by_query(all_fees, query)
        if suggested_fees:
            return _fee_search_response(suggested_fees, query)
        return {
            "status": "not_found",
            "message": f"No included services or fees matched '{query}'.",
        }

    return {
        "status": "ok",
        "included_services": _serialize_rows(rows),
        "related_fees": _serialize_rows(fee_rows),
        "note": "Compare included_services vs related_fees for included vs extra-cost.",
    }


def get_assumptions(category: str | None = None) -> dict[str, Any]:
    document_id = _latest_document_id()
    client = get_supabase_client()
    request = client.table("assumptions").select("*").eq("document_id", document_id)
    if category:
        request = request.ilike("category", f"%{category}%")
    rows = request.execute().data or []
    if not rows:
        return {"status": "not_found", "message": "No assumptions found for that category."}
    return {"status": "ok", "assumptions": rows}


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_pricing_models",
            "description": "List available pricing models (Traditional vs Applied Rebates).",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_networks",
            "description": "List pharmacy networks/channels in the contract.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_network_discount",
            "description": (
                "Look up a network discount or dispensing fee from pricing grids. "
                "For Retail 30 or Retail 90, pass network='retail_30' or network='retail_90'. "
                "Do not pass pricing_model until the user has chosen Traditional or Applied Rebates. "
                "Do not use for ancillary service fees, prior authorization costs, or eligibility maintenance."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pricing_model": {
                        "type": "string",
                        "enum": ["traditional", "applied_rebates"],
                        "description": (
                            "Omit unless the user explicitly stated Traditional or Applied Rebates "
                            "in the conversation. If omitted, the tool asks which model applies."
                        ),
                    },
                    "network": {
                        "type": "string",
                        "description": (
                            "Retail channel (retail_30, retail_90) or standalone network "
                            "(mail, retail_specialty, exclusive_specialty)."
                        ),
                    },
                    "channel": {
                        "type": "string",
                        "enum": ["retail_30", "retail_90"],
                        "description": "Optional alias when the user names Retail 30/90 explicitly.",
                    },
                    "drug_type": {
                        "type": "string",
                        "enum": ["brand", "generic", "ldd", "new_to_market"],
                    },
                    "year": {"type": "integer"},
                    "metric": {
                        "type": "string",
                        "enum": ["discount", "dispensing_fee"],
                        "default": "discount",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_rebate_guarantee",
            "description": (
                "Look up rebate guarantee dollars and payment timing from pricing grids. "
                "Do not use for service fees or prior authorization costs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "payment_schedule": {
                        "type": "string",
                        "enum": ["quarterly_150d", "monthly_60d"],
                    },
                    "channel": {
                        "type": "string",
                        "enum": ["retail_30", "retail_90", "mail", "specialty"],
                    },
                    "year": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_fees",
            "description": (
                "Search priced ancillary fees and allowances (Allowances and Ancillary Charges). "
                "Use when the user asks how much something costs: prior authorization, eligibility "
                "maintenance, audits, appeals, PMPM program fees. Pass 2-4 keywords from the question."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_included_services",
            "description": (
                "Compare included PBM services vs related extra-cost fees. "
                "Use for 'is X included', 'included vs extra-cost', or eligibility maintenance "
                "inclusion questions. Not the first choice for 'how much does X cost' — use search_fees."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "query": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_assumptions",
            "description": "Retrieve contract assumptions and caveats.",
            "parameters": {
                "type": "object",
                "properties": {"category": {"type": "string"}},
                "additionalProperties": False,
            },
        },
    },
]


def dispatch_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "list_pricing_models":
        return list_pricing_models()
    if name == "list_networks":
        return list_networks()
    if name == "get_network_discount":
        return get_network_discount(**arguments)
    if name == "get_rebate_guarantee":
        return get_rebate_guarantee(**arguments)
    if name == "search_fees":
        return search_fees(**arguments)
    if name == "get_included_services":
        return get_included_services(**arguments)
    if name == "get_assumptions":
        return get_assumptions(**arguments)
    return {"status": "error", "message": f"Unknown tool: {name}"}
