from __future__ import annotations

import asyncio
import traceback
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

StatusCallback = Callable[[str], None]


@dataclass
class AgentResult:
    # SocialMediaAgent
    social_profiles: dict[str, list] = field(default_factory=dict)
    phone_numbers: list[str] = field(default_factory=list)
    platform_activity: dict[str, int] = field(default_factory=dict)
    # LegalRecordsAgent
    company_records: list[dict[str, Any]] = field(default_factory=list)
    academic_context: str = ""
    patent_context: str = ""
    registry_context: str = ""
    # SecurityAgent
    data_breaches: list[dict[str, Any]] = field(default_factory=list)
    cross_validation_issues: list[str] = field(default_factory=list)
    # Metadata
    agent_name: str = ""
    success: bool = True
    error: str | None = None


class BaseAgent(ABC):
    def __init__(self, status_callback: StatusCallback, loop: asyncio.AbstractEventLoop) -> None:
        self._status = status_callback
        self._loop = loop

    async def run(self) -> AgentResult:
        try:
            return await self.run_async()
        except Exception as exc:
            self._broadcast(f"[WARN] {self.agent_name} failed: {exc}")
            return AgentResult(agent_name=self.agent_name, success=False, error=traceback.format_exc())

    @abstractmethod
    async def run_async(self) -> AgentResult: ...

    @property
    @abstractmethod
    def agent_name(self) -> str: ...

    def _broadcast(self, message: str) -> None:
        self._status(message)

    async def _run_sync(self, fn: Callable, *args: Any) -> Any:
        return await self._loop.run_in_executor(None, fn, *args)
