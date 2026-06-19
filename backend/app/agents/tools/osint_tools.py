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
    from app.services.company_service import company_service
    loop = asyncio.get_running_loop()
    try:
        records = await loop.run_in_executor(None, company_service.search_companies, name)
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


async def get_location_cameras(place: str) -> str:
    """Find PUBLIC live webcams near a place — returns latest frames + watch links.

    Public, publisher-streamed cameras only (traffic / tourism / weather / harbor
    cams via Windy Webcams or public live-cam pages). Never private/exposed cameras.
    """
    from app.services.webcam_service import webcam_service
    try:
        data = await webcam_service.find_public_webcams(place)
        cams = data.get("webcams", [])
        if not cams:
            return f"No public webcams found near '{place}'."

        lines = [
            f"### Public live cameras near {data.get('place', place)}  "
            f"(source: {data.get('source', 'web')})",
            "",
        ]
        for c in cams[:12]:
            title = c.get("title", "Webcam")
            page = c.get("page_url", "")
            img = c.get("image_current") or c.get("image_daylight") or ""
            if img:
                lines.append(f"**{title}**")
                lines.append(f"![{title}]({img})")
                if page:
                    lines.append(f"[▶ Watch live]({page})")
            elif page:
                lines.append(f"- **{title}** — [▶ Watch live]({page})")
            lines.append("")
        return _truncate("\n".join(lines), 6000)
    except Exception as exc:
        return f"Location camera lookup error: {exc}"


async def get_latest_images(query: str, analyze: bool = False) -> str:
    """Fetch the most recent publicly published images for a person or place."""
    loop = asyncio.get_running_loop()
    try:
        images = await loop.run_in_executor(None, _search.search_images, query)
        if not images:
            return f"No public images found for '{query}'."

        lines = [f"### Latest public images for {query}", ""]
        for im in images[:8]:
            url = im.get("image_url", "")
            src = im.get("source_url", "")
            title = im.get("title") or query
            if url:
                lines.append(f"![{title}]({url})")
                if src:
                    lines.append(f"[source]({src})")
                lines.append("")

        if analyze and images:
            from app.services.vision_service import vision_service
            try:
                caption = await vision_service.analyze_image(
                    images[0]["image_url"],
                    "Briefly describe this image and any location or identity clues.",
                )
                lines.append(f"**Vision analysis (top image):** {caption}")
            except Exception as exc:  # noqa: BLE001 — vision is optional enrichment
                logger.log_warning(f"Optional vision analysis skipped: {exc}")

        return _truncate("\n".join(lines), 6000)
    except Exception as exc:
        return f"Latest images error: {exc}"


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
        name="get_location_cameras",
        description=(
            "Find PUBLIC live webcams near a location (city, landmark, or address) and return "
            "their latest camera frames plus 'watch live' links. Use this when the user asks "
            "what a place looks like right now or wants live/recent camera views of a PLACE. "
            "Public, publisher-streamed cameras only."
        ),
        parameters={
            "type": "object",
            "properties": {"place": {"type": "string", "description": "Place name, city, landmark, or address"}},
            "required": ["place"],
        },
        handler=get_location_cameras,
    ))

    registry.register(Tool(
        name="get_latest_images",
        description=(
            "Fetch the most recent publicly published images/photos for a person or place via "
            "web image search. Use when the user wants the latest pictures or a visual of a subject. "
            "Set analyze=true to also describe the top image with the vision model."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Person name or place to fetch recent public images for"},
                "analyze": {"type": "boolean", "description": "If true, run the top image through the vision model for a description"},
            },
            "required": ["query"],
        },
        handler=get_latest_images,
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
