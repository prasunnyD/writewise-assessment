"""Typed database query tools for the Q&A agent."""

from __future__ import annotations

from typing import Any

from db.client import get_supabase_client


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

    def _base_query():
        query = (
            client.table("contract_terms")
            .select("*")
            .eq("document_id", document_id)
            .eq("pricing_model_id", pricing_model)
            .eq("drug_type", drug_type)
            .eq("calendar_year", year)
            .eq("term_category", term_category)
        )
        if channel_id:
            query = query.eq("channel", channel_id)
        if network_id:
            query = query.eq("network_id", network_id)
        return query

    rows = _base_query().execute().data or []
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
    client = get_supabase_client()
    rows = (
        client.table("included_services")
        .select("*")
        .eq("document_id", document_id)
        .eq("source_section", "allowances_fees")
        .ilike("service_name", f"%{query}%")
        .execute()
        .data
        or []
    )
    if not rows:
        rows = (
            client.table("included_services")
            .select("*")
            .eq("document_id", document_id)
            .eq("source_section", "allowances_fees")
            .ilike("value_text", f"%{query}%")
            .execute()
            .data
            or []
        )
    if not rows:
        rows = (
            client.table("included_services")
            .select("*")
            .eq("document_id", document_id)
            .eq("source_section", "allowances_fees")
            .ilike("cost_summary", f"%{query}%")
            .execute()
            .data
            or []
        )
    if not rows:
        return {"status": "not_found", "message": f"No fees matched '{query}'."}
    return {"status": "ok", "results": _serialize_rows(rows)}


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
        q = query.lower()
        rows = [
            row
            for row in rows
            if q in row.get("service_name", "").lower()
            or q in row.get("category", "").lower()
            or q in (row.get("cost_summary") or "").lower()
        ]

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
        q = query.lower()
        fee_rows = [
            row
            for row in fee_rows
            if q in row.get("service_name", "").lower()
            or q in row.get("category", "").lower()
            or q in (row.get("value_text") or "").lower()
            or q in (row.get("cost_summary") or "").lower()
        ]

    return {
        "status": "ok",
        "included_services": rows,
        "related_fees": fee_rows,
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
                "Look up a network discount or dispensing fee. "
                "For Retail 30 or Retail 90, pass network='retail_30' or network='retail_90' "
                "(stored as channel under broad_national — do not ask the user for broad_national). "
                "For Mail, Retail Specialty, or Exclusive Specialty, pass network='mail', etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pricing_model": {"type": "string", "enum": ["traditional", "applied_rebates"]},
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
            "description": "Look up rebate guarantee dollars and payment timing.",
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
            "description": "Search ancillary fees and allowances from Allowances and Ancillary Charges by keyword.",
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
                "List included PBM services (Included Services section) and related "
                "extra-cost fees (Allowances and Ancillary Charges)."
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
