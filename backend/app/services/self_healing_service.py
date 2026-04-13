"""
Self-Healing Service — monitors service health and attempts automatic recovery.

Runs as a background asyncio task that periodically checks all dependent
services (Ollama, ChromaDB, Database) and attempts reconnection on failure.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import text

from app.config import get_settings
from app.utils.logger import logger

settings = get_settings()

# Maximum log entries kept in memory
_MAX_LOG_SIZE = 200


class SelfHealingService:
    """Monitors service health and attempts automatic recovery."""

    def __init__(self):
        self._health_log: deque[dict[str, Any]] = deque(maxlen=_MAX_LOG_SIZE)
        self._recovery_attempts: dict[str, int] = {}
        self._is_running = False
        self._start_time = time.time()
        self._last_status: dict[str, dict[str, Any]] = {}

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self._start_time

    # -- Background Monitoring ------------------------------------------------

    async def start_monitoring(self, interval_seconds: int = 30):
        """Background coroutine that periodically checks and recovers services."""
        self._is_running = True
        logger.log_action("Self-healing monitoring system activated")
        while self._is_running:
            try:
                await self._check_and_heal()
            except Exception as e:
                self._log_event("monitor", "error", f"Health check loop error: {e}")
            await asyncio.sleep(interval_seconds)

    def stop(self):
        """Signal the monitoring loop to stop."""
        self._is_running = False
        logger.log_action("Self-healing monitoring system deactivated")

    # -- Core Health Check & Recovery -----------------------------------------

    async def _check_and_heal(self):
        """Run health checks and attempt recovery for failed services."""
        status: dict[str, dict[str, Any]] = {}

        # 1. Ollama
        status["ollama"] = await self._check_ollama()
        if status["ollama"]["status"] == "unhealthy":
            await self._recover_ollama()

        # 2. Database
        status["database"] = self._check_database()

        # 4. System resources
        status["system"] = self._check_system_resources()

        self._last_status = status

        # Log only if something changed or is unhealthy
        unhealthy = [k for k, v in status.items() if v.get("status") == "unhealthy"]
        if unhealthy:
            self._log_event("health_check", "warning", f"Unhealthy: {', '.join(unhealthy)}")
        elif any(
            self._last_status.get(k, {}).get("status") != v.get("status")
            for k, v in status.items()
        ):
            self._log_event("health_check", "info", "All services healthy")

    # -- Individual Service Checks -------------------------------------------

    async def _check_ollama(self) -> dict[str, Any]:
        """Check Ollama connectivity."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{settings.ollama_url}/api/tags", timeout=5.0)
                models = [m["name"] for m in resp.json().get("models", [])]
                return {"status": "healthy", "models": models, "url": settings.ollama_url}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e), "url": settings.ollama_url}

    def _check_database(self) -> dict[str, Any]:
        """Check SQLite database connectivity."""
        try:
            from app.database import SessionLocal
            db = SessionLocal()
            db.execute(text("SELECT 1"))
            db.close()
            return {"status": "healthy", "type": "SQLite"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def _check_system_resources(self) -> dict[str, Any]:
        """Check system resource usage (best-effort)."""
        import os
        try:
            import shutil
            total, used, free = shutil.disk_usage(".")
            disk_pct = used / total * 100
            result: dict[str, Any] = {
                "status": "healthy" if disk_pct < 90 else "warning",
                "disk_used_pct": round(disk_pct, 1),
                "disk_free_gb": round(free / (1024**3), 2),
            }
            # Try to get memory info (psutil optional)
            try:
                import psutil
                mem = psutil.virtual_memory()
                result["memory_used_pct"] = round(mem.percent, 1)
                result["memory_available_gb"] = round(mem.available / (1024**3), 2)
                cpu = psutil.cpu_percent(interval=0.1)
                result["cpu_percent"] = cpu
            except ImportError:
                pass
            return result
        except Exception as e:
            return {"status": "unknown", "error": str(e)}

    # -- Recovery Actions ----------------------------------------------------

    async def _recover_ollama(self):
        """Attempt to reconnect to Ollama."""
        service = "ollama"
        self._recovery_attempts[service] = self._recovery_attempts.get(service, 0) + 1
        attempt = self._recovery_attempts[service]

        self._log_event(service, "recovery", f"Recovery attempt #{attempt}")
        logger.log_warning(f"Ollama connection lost — recovery attempt #{attempt}")

        # Wait with exponential backoff (max 60s)
        wait = min(2 ** attempt, 60)
        await asyncio.sleep(wait)

        # Re-check
        check = await self._check_ollama()
        if check["status"] == "healthy":
            self._recovery_attempts[service] = 0
            self._log_event(service, "recovered", "Ollama connection restored")
            logger.log_success("Ollama connection restored")
        else:
            self._log_event(service, "failed", f"Recovery failed (attempt #{attempt})")

    # -- Status & Log Access --------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return current service status snapshot."""
        return {
            "services": self._last_status,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "is_monitoring": self._is_running,
            "recovery_attempts": dict(self._recovery_attempts),
        }

    def get_health_log(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent health events."""
        entries = list(self._health_log)
        entries.reverse()  # Newest first
        return entries[:limit]

    def get_full_health_check(self) -> dict[str, Any]:
        """Synchronous full health check for the /health endpoint."""
        return {
            "status": "healthy" if all(
                s.get("status") == "healthy" for s in self._last_status.values()
            ) else "degraded",
            "services": self._last_status,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "is_monitoring": self._is_running,
        }

    # -- Internal Logging -----------------------------------------------------

    def _log_event(self, service: str, event_type: str, message: str):
        self._health_log.append({
            "timestamp": datetime.now(UTC).isoformat(),
            "service": service,
            "type": event_type,
            "message": message,
        })


# Singleton
self_healing_service = SelfHealingService()
