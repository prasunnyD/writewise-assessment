"""OpenAI function-calling agent loop."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import typer
from openai import OpenAI

from agent.prompts import SYSTEM_PROMPT
from agent.tools import DOCUMENT_SCOPED_TOOLS, TOOL_DEFINITIONS, dispatch_tool, list_documents

_PRICING_MODEL_PATTERN = re.compile(
    r"\btraditional\b|\bapplied[\s_-]*rebates?\b",
    re.IGNORECASE,
)
_DRUG_TYPE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("new_to_market", re.compile(r"\bnew[\s_-]+to[\s_-]+market\b", re.IGNORECASE)),
    ("generic", re.compile(r"\bgenerics?\b", re.IGNORECASE)),
    ("brand", re.compile(r"\bbrands?\b", re.IGNORECASE)),
    ("ldd", re.compile(r"\bldd\b", re.IGNORECASE)),
]
_YEAR_PATTERN = re.compile(r"\b(202[4-7])\b")
_RETAIL_90_PATTERN = re.compile(r"\bretail[\s_-]*90\b", re.IGNORECASE)
_RETAIL_30_PATTERN = re.compile(r"\bretail[\s_-]*30\b", re.IGNORECASE)


def _user_messages(messages: list[dict[str, Any]]) -> list[str]:
    """Return content strings from user-role messages in the conversation."""
    return [
        message.get("content") or ""
        for message in messages
        if message.get("role") == "user"
    ]


def _user_specified_pricing_model(messages: list[dict[str, Any]]) -> bool:
    """Return True if the user mentioned Traditional or Applied Rebates pricing."""
    for content in _user_messages(messages):
        if _PRICING_MODEL_PATTERN.search(content):
            return True
    return False


def _user_specified_drug_type(messages: list[dict[str, Any]]) -> str | None:
    """Return the most recently mentioned drug type slug, if any."""
    for content in reversed(_user_messages(messages)):
        for drug_type, pattern in _DRUG_TYPE_PATTERNS:
            if pattern.search(content):
                return drug_type
    return None


def _user_specified_year(messages: list[dict[str, Any]]) -> int | None:
    """Return the most recently mentioned contract year (2024–2027), if any."""
    for content in reversed(_user_messages(messages)):
        match = _YEAR_PATTERN.search(content)
        if match:
            return int(match.group(1))
    return None


def _user_specified_retail_network(messages: list[dict[str, Any]]) -> str | None:
    """Return retail_30 or retail_90 when the user names a retail channel."""
    for content in reversed(_user_messages(messages)):
        if _RETAIL_90_PATTERN.search(content):
            return "retail_90"
        if _RETAIL_30_PATTERN.search(content):
            return "retail_30"
    return None


def _enrich_network_discount_args(
    args: dict[str, Any],
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    """Fill get_network_discount args from user messages; strip unstated pricing_model."""
    if not _user_specified_pricing_model(messages):
        args.pop("pricing_model", None)
    if not args.get("drug_type"):
        drug_type = _user_specified_drug_type(messages)
        if drug_type:
            args["drug_type"] = drug_type
    if not args.get("year"):
        year = _user_specified_year(messages)
        if year:
            args["year"] = year
    if not args.get("network") and not args.get("channel"):
        network = _user_specified_retail_network(messages)
        if network:
            args["network"] = network
    return args


def _resolve_document_choice(choice: str, documents: list[dict[str, Any]]) -> str | None:
    """Map a numeric index or filename substring to a document UUID."""
    choice = choice.strip()
    if choice.isdigit():
        index = int(choice) - 1
        if 0 <= index < len(documents):
            return documents[index]["id"]
    choice_lower = choice.lower()
    matches = [
        document
        for document in documents
        if choice_lower in (document.get("source_filename") or "").lower()
    ]
    if len(matches) == 1:
        return matches[0]["id"]
    return None


class ContractAgent:
    """OpenAI tool-calling agent for contract Q&A over Supabase data."""

    def __init__(self) -> None:
        """Initialize the OpenAI client and conversation state."""
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required")
        self.client = OpenAI(api_key=api_key)
        self.model = os.environ.get("OPENAI_MODEL", "gpt-4o")
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.selected_document_id: str | None = None

    def prompt_for_document(self) -> None:
        """Interactively select which extracted contract to query."""
        result = list_documents()
        if result["status"] == "not_found":
            typer.echo(result["message"])
            raise typer.Exit(1)

        documents = result["documents"]
        typer.echo("Which contract would you like to query?")
        for index, document in enumerate(documents, 1):
            typer.echo(f"  {index}. {document['label']}")

        while True:
            try:
                choice = typer.prompt("Contract")
            except (EOFError, KeyboardInterrupt):
                typer.echo("\nGoodbye.")
                raise typer.Exit(0) from None

            document_id = _resolve_document_choice(choice, documents)
            if document_id:
                self.selected_document_id = document_id
                selected = next(doc for doc in documents if doc["id"] == document_id)
                typer.echo(f"\nQuerying: {selected['source_filename']}\n")
                return

            typer.echo("Invalid choice. Enter a number or part of the filename.")

    def ask(self, question: str) -> str:
        """Run the tool-calling loop for a user question and return the final answer."""
        self.messages.append({"role": "user", "content": question})
        for _ in range(8):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
                temperature=0,
            )
            message = response.choices[0].message
            assistant_payload: dict[str, Any] = {
                "role": "assistant",
                "content": message.content,
            }
            if message.tool_calls:
                assistant_payload["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in message.tool_calls
                ]
            self.messages.append(assistant_payload)

            if not message.tool_calls:
                return message.content or "I could not generate an answer."

            for call in message.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                if call.function.name == "get_network_discount":
                    args = _enrich_network_discount_args(args, self.messages)
                if (
                    call.function.name in DOCUMENT_SCOPED_TOOLS
                    and not args.get("document_id")
                    and self.selected_document_id
                ):
                    args["document_id"] = self.selected_document_id
                result = dispatch_tool(call.function.name, args)
                if (
                    result.get("status") == "ok"
                    and call.function.name in DOCUMENT_SCOPED_TOOLS
                    and args.get("document_id")
                ):
                    self.selected_document_id = args["document_id"]
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, default=str),
                    }
                )
        return "I couldn't complete the answer within the tool call limit."
