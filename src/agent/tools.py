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


def get_network_discount(
    *,
    pricing_model: str | None = None,
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
    if not network:
        return {
            "status": "needs_clarification",
            "message": "Which network?",
            "options": [n["id"] for n in (list_networks().get("networks") or [])],
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
    query = (
        client.table("contract_terms")
        .select("*")
        .eq("document_id", document_id)
        .eq("pricing_model_id", pricing_model)
        .eq("network_id", network)
        .eq("drug_type", drug_type)
        .eq("calendar_year", year)
        .eq("term_category", term_category)
    )
    rows = query.execute().data or []
    if not rows:
        return {
            "status": "not_found",
            "message": "No matching discount found in contract data.",
            "query": {
                "pricing_model": pricing_model,
                "network": network,
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
        client.table("contract_terms")
        .select("*")
        .eq("document_id", document_id)
        .in_("term_category", ["ancillary_fee", "allowance"])
        .ilike("source_row_label", f"%{query}%")
        .execute()
        .data
        or []
    )
    if not rows:
        rows = (
            client.table("contract_terms")
            .select("*")
            .eq("document_id", document_id)
            .in_("term_category", ["ancillary_fee", "allowance"])
            .ilike("value_text", f"%{query}%")
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
    request = client.table("included_services").select("*").eq("document_id", document_id)
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

    fee_rows = search_fees(query or category or "eligibility")
    extra_costs = fee_rows.get("results", []) if fee_rows.get("status") == "ok" else []

    return {
        "status": "ok",
        "included_services": rows,
        "related_fees": extra_costs,
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
            "description": "Look up a network discount or dispensing fee from the database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pricing_model": {"type": "string", "enum": ["traditional", "applied_rebates"]},
                    "network": {"type": "string"},
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
            "description": "Search ancillary fees and allowances by service name keyword.",
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
            "description": "List included PBM services and related extra-cost fees.",
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
