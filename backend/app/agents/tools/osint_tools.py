"""OSINT tool wrappers — expose existing services as callable tools for the agent loop."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from app.agents.tool_registry import Tool, ToolRegistry
from app.plugins import plugin_manager
from app.services.breach_service import BreachService
from app.services.darkweb_service import DarkWebService
from app.services.github_service import GitHubService
from app.services.scraper_service import ScraperService
from app.services.search_service import SearchService
from app.utils.logger import logger

_github = GitHubService()
_search = SearchService()
_scraper = ScraperService()
_breach = BreachService()
_darkweb = DarkWebService()


def _truncate(text: str, limit: int = 4000) -> str:
    if len(text) > limit:
        return text[:limit] + "\n... [TRUNCATED]"
    return text


# ------------------------------------------------------------------
# Tool handler implementations
# ------------------------------------------------------------------

async def search_person(name: str) -> str:
    """Web search for a person — returns wiki image, web results, deep context."""
    loop = asyncio.get_running_loop()
    try:
        wiki_img, web_results, deep_ctx, sources = await loop.run_in_executor(
            None, _search.search_person, name
        )
        output = {"wiki_image": wiki_img, "web_results_count": len(sources), "deep_context": deep_ctx}
        return _truncate(json.dumps(output, ensure_ascii=False, indent=1))
    except Exception as exc:
        return f"Search error: {exc}"


async def github_lookup(username: str) -> str:
    """Look up a GitHub user profile."""
    loop = asyncio.get_running_loop()
    try:
        data = await loop.run_in_executor(None, _github.search_user, username)
        if not data:
            return f"No GitHub profile found for '{username}'."
        return _truncate(json.dumps(data, ensure_ascii=False, indent=1))
    except Exception as exc:
        return f"GitHub lookup error: {exc}"


async def check_breaches(email: str) -> str:
    """Check if an email appears in known data breaches."""
    try:
        results = await _breach.check_breaches([email])
        if not results:
            return f"No breaches found for '{email}'."
        return _truncate(json.dumps(results, ensure_ascii=False, indent=1))
    except Exception as exc:
        return f"Breach check error: {exc}"


async def scan_darkweb(query: str) -> str:
    """Scan paste sites and leak databases for mentions of a query."""
    try:
        results = await _darkweb.aggregate_deep_intel(
            emails=[query] if "@" in query else [],
            username=query if "@" not in query else "",
            real_name=query,
        )
        return _truncate(json.dumps(results, ensure_ascii=False, indent=1))
    except Exception as exc:
        return f"Dark web scan error: {exc}"


async def scrape_social(username: str) -> str:
    """Find social media profiles for a username across platforms."""
    loop = asyncio.get_running_loop()
    try:
        profiles = await loop.run_in_executor(None, _scraper.find_profiles_by_username, username)
        found = {k: v for k, v in profiles.items() if v}
        if not found:
            return f"No social media profiles found for '{username}'."
        summary = {platform: len(items) for platform, items in found.items()}
        return json.dumps({"platforms_found": summary, "details": found}, ensure_ascii=False, indent=1)
    except Exception as exc:
        return f"Social scraping error: {exc}"


async def search_companies(name: str) -> str:
    """Search for company/corporate registrations associated with a name."""
    from app.services.company_service import CompanyService
    loop = asyncio.get_running_loop()
    try:
        svc = CompanyService()
        records = await loop.run_in_executor(None, svc.search_companies, name)
        if not records:
            return f"No company records found for '{name}'."
        return _truncate(json.dumps(records, ensure_ascii=False, indent=1))
    except Exception as exc:
        return f"Company search error: {exc}"


async def analyze_image(image_url: str, prompt: str = "Describe this image in detail.") -> str:
    """Analyze an image using the vision model."""
    from app.services.vision_service import vision_service
    try:
        result = await vision_service.analyze_image(image_url, prompt)
        return _truncate(result)
    except Exception as exc:
        return f"Vision analysis error: {exc}"


async def run_plugin(plugin_name: str, query: str) -> str:
    """Run a specific OSINT plugin by name."""
    try:
        result = await plugin_manager.run_plugin(plugin_name, query)
        return _truncate(json.dumps(result, ensure_ascii=False, indent=1))
    except Exception as exc:
        return f"Plugin error: {exc}"


# ------------------------------------------------------------------
# Registry builder
# ------------------------------------------------------------------

def build_osint_registry() -> ToolRegistry:
    """Create and return a ToolRegistry populated with all OSINT tools."""
    registry = ToolRegistry()

    registry.register(Tool(
        name="search_person",
        description="Search the web for information about a person by their full name. Returns web results and deep context.",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Full name of the person to search"}},
            "required": ["name"],
        },
        handler=search_person,
    ))

    registry.register(Tool(
        name="github_lookup",
        description="Look up a GitHub user profile by username. Returns repos, bio, location, social links.",
        parameters={
            "type": "object",
            "properties": {"username": {"type": "string", "description": "GitHub username"}},
            "required": ["username"],
        },
        handler=github_lookup,
    ))

    registry.register(Tool(
        name="check_breaches",
        description="Check if an email address appears in known data breaches (HaveIBeenPwned).",
        parameters={
            "type": "object",
            "properties": {"email": {"type": "string", "description": "Email address to check"}},
            "required": ["email"],
        },
        handler=check_breaches,
    ))

    registry.register(Tool(
        name="scan_darkweb",
        description="Scan paste sites and leak databases for mentions of a name, username, or email.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Name, username, or email to search"}},
            "required": ["query"],
        },
        handler=scan_darkweb,
    ))

    registry.register(Tool(
        name="scrape_social",
        description="Find social media profiles (Instagram, Twitter, LinkedIn, etc.) for a username.",
        parameters={
            "type": "object",
            "properties": {"username": {"type": "string", "description": "Username to search across social platforms"}},
            "required": ["username"],
        },
        handler=scrape_social,
    ))

    registry.register(Tool(
        name="search_companies",
        description="Search for company registrations, directorships, and corporate ties for a person.",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Person or company name to search"}},
            "required": ["name"],
        },
        handler=search_companies,
    ))

    registry.register(Tool(
        name="analyze_image",
        description="Analyze an image using the vision AI model. Useful for extracting intelligence from photos, screenshots, and social media images.",
        parameters={
            "type": "object",
            "properties": {
                "image_url": {"type": "string", "description": "URL of the image to analyze"},
                "prompt": {"type": "string", "description": "Optional specific question about the image"},
            },
            "required": ["image_url"],
        },
        handler=analyze_image,
    ))

    registry.register(Tool(
        name="run_plugin",
        description="Run a specific OSINT plugin (e.g. shodan, censys) with a query.",
        parameters={
            "type": "object",
            "properties": {
                "plugin_name": {"type": "string", "description": "Name of the plugin to run"},
                "query": {"type": "string", "description": "Search query for the plugin"},
            },
            "required": ["plugin_name", "query"],
        },
        handler=run_plugin,
    ))

    # Add any enabled plugin tools dynamically
    for schema in plugin_manager.get_tool_schemas():
        func_info = schema.get("function", {})
        pname = func_info.get("name", "")
        if pname and pname not in registry.list_tools():
            actual_plugin_name = pname.replace("plugin_", "", 1)

            async def _plugin_handler(query: str, _pn: str = actual_plugin_name) -> str:
                return await run_plugin(_pn, query)

            registry.register(Tool(
                name=pname,
                description=func_info.get("description", ""),
                parameters=func_info.get("parameters", {}),
                handler=_plugin_handler,
            ))

    logger.log_action(f"OSINT Tool Registry built: {len(registry.list_tools())} tools registered")
    return registry
