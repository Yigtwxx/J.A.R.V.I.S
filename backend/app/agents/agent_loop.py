"""Agentic Loop — LLM decides which tools to call, executes them, and iterates until done."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import ollama

from app.agents.tool_registry import ToolRegistry
from app.config import get_settings
from app.utils.logger import logger

settings = get_settings()


class AgentLoop:
    """Core agentic loop: message -> LLM (with tools) -> tool_calls -> execute -> loop."""

    def __init__(
        self,
        registry: ToolRegistry,
        model: str | None = None,
        max_iterations: int = 10,
    ) -> None:
        self.registry = registry
        self.model = model or settings.ollama_model
        self.client = ollama.AsyncClient()
        self.max_iterations = max_iterations

    @staticmethod
    def _strip_thinking(text: str) -> str:
        return re.sub(r"<think>[\s\S]*?</think>", "", text).strip()

    async def run(
        self,
        user_message: str,
        system_prompt: str | None = None,
        conversation_history: list[dict] | None = None,
    ) -> str:
        """Run the full agent loop until the LLM produces a final text response.

        Returns the final text response from the LLM.
        """
        if system_prompt is None:
            system_prompt = self._default_system_prompt()

        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

        if conversation_history:
            messages.extend(conversation_history)

        messages.append({"role": "user", "content": user_message})

        tools = self.registry.get_ollama_schemas()
        tool_calls_log: list[dict] = []

        for iteration in range(self.max_iterations):
            logger.log_thought(f"Agent iteration {iteration + 1}/{self.max_iterations}")

            try:
                response = await self.client.chat(
                    model=self.model,
                    messages=messages,
                    tools=tools if iteration < self.max_iterations - 1 else [],  # No tools on last iteration
                    options={"temperature": 0.3, "top_p": 0.7},
                )
            except Exception as exc:
                logger.log_error(f"Agent LLM call failed: {exc}")
                return f"Agent error: {exc}"

            msg = response.get("message", {})
            tool_calls = msg.get("tool_calls")

            if not tool_calls:
                # No tool calls — LLM produced a final response
                final_text = self._strip_thinking(msg.get("content", ""))

                # If we have gathered tool data, append a reflection pass
                if tool_calls_log and iteration > 0:
                    final_text = await self._reflect(messages, final_text, tool_calls_log)

                return final_text

            # Process tool calls (parallel if multiple)
            messages.append(msg)

            tasks = []
            for call in tool_calls:
                func = call.get("function", {})
                tool_name = func.get("name", "")
                arguments = func.get("arguments", {})
                logger.log_action(f"Agent calling tool: {tool_name}", target=json.dumps(arguments, ensure_ascii=False)[:100])
                tasks.append(self._execute_tool(tool_name, arguments))

            results = await asyncio.gather(*tasks)

            for call, result in zip(tool_calls, results):
                func = call.get("function", {})
                tool_calls_log.append({
                    "tool": func.get("name", ""),
                    "args": func.get("arguments", {}),
                    "result_preview": result[:200],
                })
                messages.append({"role": "tool", "content": result})

        # Max iterations reached
        last_content = messages[-1].get("content", "") if messages else ""
        return self._strip_thinking(last_content) or "Agent reached maximum iterations without a final response."

    async def run_streaming(
        self,
        user_message: str,
        system_prompt: str | None = None,
        conversation_history: list[dict] | None = None,
    ):
        """Run the agent loop and stream the final response token by token.

        Yields tokens as they come from the LLM for the final response.
        Tool-calling iterations run non-streaming; only the last response streams.
        """
        if system_prompt is None:
            system_prompt = self._default_system_prompt()

        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_message})

        tools = self.registry.get_ollama_schemas()
        tool_calls_log: list[dict] = []

        for iteration in range(self.max_iterations):
            is_last = iteration == self.max_iterations - 1

            try:
                response = await self.client.chat(
                    model=self.model,
                    messages=messages,
                    tools=tools if not is_last else [],
                    options={"temperature": 0.3, "top_p": 0.7},
                )
            except Exception as exc:
                yield f"\n[Agent Error: {exc}]"
                return

            msg = response.get("message", {})
            tool_calls = msg.get("tool_calls")

            if not tool_calls:
                # Final response — now stream it
                reflection_prompt = ""
                if tool_calls_log:
                    reflection_prompt = (
                        "\n\nBefore answering, briefly reflect: Are there gaps in the gathered data? "
                        "Any contradictions? Rate your confidence."
                    )

                # Re-run as streaming for the final answer
                messages.append({"role": "user", "content": f"Now provide your final comprehensive response.{reflection_prompt}"})

                in_thinking = False
                stream = await self.client.chat(
                    model=self.model,
                    messages=messages,
                    stream=True,
                    options={"temperature": 0.3, "top_p": 0.7},
                )
                async for chunk in stream:
                    if "message" in chunk and "content" in chunk["message"]:
                        token = chunk["message"]["content"]
                        if "<think>" in token:
                            in_thinking = True
                        if not in_thinking:
                            yield token
                        if "</think>" in token:
                            in_thinking = False
                return

            # Execute tools
            messages.append(msg)
            tasks = []
            for call in tool_calls:
                func = call.get("function", {})
                tasks.append(self._execute_tool(func.get("name", ""), func.get("arguments", {})))

            results = await asyncio.gather(*tasks)
            for call, result in zip(tool_calls, results):
                func = call.get("function", {})
                tool_calls_log.append({"tool": func.get("name", ""), "args": func.get("arguments", {})})
                messages.append({"role": "tool", "content": result})

        yield "\n[Agent reached maximum iterations]"

    async def _execute_tool(self, name: str, arguments: dict) -> str:
        return await self.registry.execute(name, arguments)

    async def _reflect(self, messages: list[dict], draft: str, tool_calls_log: list[dict]) -> str:
        """Run a reflection pass: evaluate completeness and confidence."""
        tools_used = ", ".join(set(t["tool"] for t in tool_calls_log))
        reflection_prompt = (
            f"You just used these tools: {tools_used}. "
            f"Your draft response:\n\n{draft}\n\n"
            "Briefly evaluate: Are there gaps? Contradictions? "
            "Rate confidence (LOW/MEDIUM/HIGH). Then provide your refined final answer."
        )
        try:
            resp = await self.client.chat(
                model=self.model,
                messages=messages + [{"role": "user", "content": reflection_prompt}],
                options={"temperature": 0.2, "top_p": 0.5},
            )
            reflected = self._strip_thinking(resp.get("message", {}).get("content", ""))
            return reflected if reflected else draft
        except Exception as e:
            logger.log_warning(f"Agent reflection failed, using draft: {e}")
            return draft

    @staticmethod
    def _default_system_prompt() -> str:
        return """You are J.A.R.V.I.S., an advanced OSINT (Open Source Intelligence) AI agent.

You have access to various intelligence-gathering tools. For each user request, decide which tools to call to gather the necessary information. You can call multiple tools in sequence.

RULES:
1. Think carefully about which tools are most relevant before calling them.
2. Do NOT call tools unnecessarily — only use what is needed to answer the query.
3. After gathering data, synthesize the results into a clear, professional intelligence briefing.
4. If a tool returns an error or no data, note it and move on — do not retry excessively.
5. Be objective, analytical, and precise in your final response.
6. Format your response as a structured intelligence report with clear sections."""
