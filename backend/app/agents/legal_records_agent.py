from __future__ import annotations
from typing import Any
import asyncio

from .base_agent import BaseAgent, AgentResult, StatusCallback


class LegalRecordsAgent(BaseAgent):
    def __init__(
        self,
        company_service: Any,
        search_service: Any,
        name: str,
        status_callback: StatusCallback,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        super().__init__(status_callback, loop)
        self._company = company_service
        self._search  = search_service
        self._name    = name

    @property
    def agent_name(self) -> str:
        return "LegalRecordsAgent"

    async def run_async(self) -> AgentResult:
        self._broadcast(f"[SYS] LegalRecordsAgent: scanning records for {self._name}")

        company_records, academic_context, patent_context, registry_context = await asyncio.gather(
            self._run_sync(self._company.search_companies, self._name),
            self._run_sync(self._search.search_academic_publications, self._name),
            self._run_sync(self._search.search_patents, self._name),
            self._run_sync(self._search.search_official_registries, self._name),
        )

        self._broadcast(
            f"[OK] LegalRecordsAgent: {len(company_records or [])} company record(s) found"
        )

        return AgentResult(
            agent_name=self.agent_name,
            company_records=company_records or [],
            academic_context=academic_context or "",
            patent_context=patent_context or "",
            registry_context=registry_context or "",
        )
