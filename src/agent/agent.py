"""OpenAI function-calling agent loop."""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from agent.prompts import SYSTEM_PROMPT
from agent.tools import TOOL_DEFINITIONS, dispatch_tool


class ContractAgent:
    def __init__(self) -> None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required")
        self.client = OpenAI(api_key=api_key)
        self.model = os.environ.get("OPENAI_MODEL", "gpt-4o")
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    def ask(self, question: str) -> str:
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
                result = dispatch_tool(call.function.name, args)
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, default=str),
                    }
                )
        return "I couldn't complete the answer within the tool call limit."
