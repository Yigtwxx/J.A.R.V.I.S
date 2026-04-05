"""Example Shodan IoT scanner plugin.

Requires a Shodan API key set via the SHODAN_API_KEY environment variable.
If the key is missing the plugin will still load but return an error message
when executed, so the rest of the system is never affected.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from .base_plugin import BasePlugin


class ShodanPlugin(BasePlugin):
    name = "shodan"
    display_name = "Shodan IoT Scanner"
    version = "1.0.0"
    description = "Search Shodan for internet-connected devices, open ports, and services associated with a target IP or domain."

    def __init__(self) -> None:
        self.api_key = os.getenv("SHODAN_API_KEY", "")
        self.base_url = "https://api.shodan.io"

    async def search(self, query: str, **kwargs: Any) -> dict[str, Any]:
        if not self.api_key:
            return {
                "source": self.name,
                "error": "SHODAN_API_KEY not configured",
                "results": [],
            }

        results: list[dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=15) as client:
            # Try host lookup first (if query looks like an IP)
            try:
                resp = await client.get(
                    f"{self.base_url}/shodan/host/{query}",
                    params={"key": self.api_key, "minify": "true"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results.append({
                        "type": "host",
                        "ip": data.get("ip_str"),
                        "os": data.get("os"),
                        "ports": data.get("ports", []),
                        "hostnames": data.get("hostnames", []),
                        "city": data.get("city"),
                        "country": data.get("country_name"),
                        "org": data.get("org"),
                        "isp": data.get("isp"),
                        "vulns": data.get("vulns", []),
                    })
            except Exception:
                pass

            # Also run a general search
            try:
                resp = await client.get(
                    f"{self.base_url}/shodan/host/search",
                    params={"key": self.api_key, "query": query, "page": 1},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for match in data.get("matches", [])[:5]:
                        results.append({
                            "type": "search_match",
                            "ip": match.get("ip_str"),
                            "port": match.get("port"),
                            "org": match.get("org"),
                            "product": match.get("product"),
                            "version": match.get("version"),
                            "os": match.get("os"),
                        })
            except Exception:
                pass

        return {
            "source": self.name,
            "results": results,
            "total": len(results),
        }
