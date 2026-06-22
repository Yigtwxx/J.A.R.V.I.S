"""Step 7 — breach check, cross-validation, scoring, GEOINT, psych, predictive."""
from __future__ import annotations

import asyncio
from typing import Any

from app.config import get_settings
from app.schemas.profile import Citation, Claim
from app.services.archive_service import archive_service
from app.services.domain_intel_service import domain_intel_service
from app.services.sanctions_service import sanctions_service
from app.services.scholarly_service import scholarly_service
from app.utils.logger import logger

from .base import PipelineStep
from .context import PipelineContext


def _collect_social_urls(social_profiles: dict, github_data: dict | None) -> list[str]:
    """Flatten discovered public profile URLs (social + GitHub) for archive lookup."""
    urls: list[str] = []
    if github_data and github_data.get('profile_url'):
        urls.append(github_data['profile_url'])
    for items in (social_profiles or {}).values():
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get('url'):
                    urls.append(item['url'])
                elif isinstance(item, str) and item.startswith('http'):
                    urls.append(item)
        elif isinstance(items, str) and items.startswith('http'):
            urls.append(items)
    # de-dup, keep order
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _norm(text: str) -> str:
    import unicodedata
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.lower().split())


def _claim(field: str, value: str, url: str, title: str | None,
           retrieved_at: str | None, confidence: float, corroboration: int = 1) -> dict:
    return Claim(
        field=field,
        value=value,
        corroboration_count=corroboration,
        citations=[Citation(url=url, title=title, retrieved_at=retrieved_at, confidence=confidence)],
    ).model_dump()


def _build_claims(structured_data, company_records, data_breaches,
                  sanctions_hits, scholarly_records, all_issues) -> list[dict]:
    """Build provenance claims for fields that carry a public source URL (Faz 2.2/2.3)."""
    claims: list[dict] = []
    try:
        for rec in (company_records or []):
            url = rec.get("source_url") if isinstance(rec, dict) else None
            name = rec.get("company_name") if isinstance(rec, dict) else None
            if url and name:
                claims.append(_claim(
                    "company", name, url, rec.get("source_name"),
                    rec.get("retrieved_at"), float(rec.get("confidence", 0.6) or 0.6),
                ))
        for hit in (sanctions_hits or []):
            if hit.get("source_url") and hit.get("name"):
                claims.append(_claim(
                    "sanctions", hit["name"], hit["source_url"], hit.get("list_name"),
                    hit.get("retrieved_at"), float(hit.get("match_score", 0.5) or 0.5),
                ))
        for rec in (scholarly_records or []):
            if rec.get("source_url") and rec.get("title"):
                claims.append(_claim(
                    "publication", rec["title"], rec["source_url"], rec.get("venue"),
                    rec.get("retrieved_at"), float(rec.get("confidence", 0.7) or 0.7),
                ))
        for b in (data_breaches or []):
            # paste exposures carry a public URL; XON breaches reference the screening source
            url = b.get("Id") or b.get("url")
            name = b.get("Title") or b.get("Name") or b.get("Source")
            if name and (url or b.get("TargetEmail")):
                claims.append(_claim(
                    "breach", str(name), url or "https://xposedornot.com",
                    b.get("Source"), None, 0.6,
                ))
        # conflict signal (Faz 2.3): lower corroboration when cross-validation flagged issues
        if all_issues:
            for c in claims:
                if c.get("corroboration_count", 1) > 0 and any(
                    _norm(c["value"]) in _norm(str(i)) for i in all_issues
                ):
                    c["corroboration_count"] = 0
    except Exception as exc:  # noqa: BLE001
        logger.log_warning(f"Claim assembly failed (non-critical): {exc}")
    return claims


def _date_key(value: str) -> str:
    """Best-effort sortable key from a date-ish string (ISO date, year, etc.)."""
    s = "".join(ch for ch in (value or "") if ch.isdigit())
    return s[:8].ljust(8, "0") if s else "00000000"


def _build_timeline(github_data, data_breaches, company_records, archive_snapshots) -> list[dict]:
    """Assemble dated public events into a sorted timeline (Faz 2.5)."""
    events: list[dict] = []
    try:
        if github_data and github_data.get("recent_commits"):
            profile = github_data.get("profile_url", "")
            for c in github_data["recent_commits"]:
                if c.get("date"):
                    msg = (c.get("message") or "").splitlines()[0][:60]
                    events.append({
                        "date": c["date"],
                        "event": f"GitHub commit: {msg} ({c.get('repo', '')})",
                        "source_url": profile,
                    })
        for b in (data_breaches or []):
            date = b.get("BreachDate") or b.get("Date")
            name = b.get("Title") or b.get("Name") or b.get("Source")
            if date and name:
                events.append({
                    "date": str(date),
                    "event": f"Data exposure: {name}",
                    "source_url": b.get("Id") or b.get("url") or "https://xposedornot.com",
                })
        for snap in (archive_snapshots or []):
            if snap.get("timestamp"):
                events.append({
                    "date": snap["timestamp"],
                    "event": f"Archive snapshot: {snap.get('url', '')}",
                    "source_url": snap.get("snapshot_url", ""),
                })
        events.sort(key=lambda e: _date_key(e.get("date", "")))
    except Exception as exc:  # noqa: BLE001
        logger.log_warning(f"Timeline assembly failed (non-critical): {exc}")
    return events


def _assess_disambiguation(real_name, raw_sources, structured_data) -> tuple[float | None, list]:
    """Score how well public sources match the subject; surface alternative candidates (Faz 2.4)."""
    try:
        sources = raw_sources or []
        if not sources:
            return None, []
        q_tokens = {t for t in _norm(real_name).split() if len(t) > 1}
        if not q_tokens:
            return None, []

        relevant = 0
        candidate_pool: dict[str, str] = {}
        for s in sources:
            text = _norm(f"{s.get('title', '')} {s.get('snippet', '')}")
            text_tokens = set(text.split())
            if q_tokens <= text_tokens:
                relevant += 1
            else:
                # collect capitalized name-like phrases from the original title as candidates
                title = s.get("title", "") or ""
                words = [w for w in title.split() if w[:1].isupper() and w.isalpha()]
                for i in range(len(words) - 1):
                    cand = f"{words[i]} {words[i + 1]}"
                    if not (q_tokens <= set(_norm(cand).split())) and len(cand) > 5:
                        candidate_pool.setdefault(_norm(cand), s.get("url", ""))

        confidence = round(relevant / len(sources), 2)

        alternatives: list = []
        if confidence < 0.6:
            for norm_name, url in list(candidate_pool.items())[:3]:
                alternatives.append({
                    "name": norm_name.title(),
                    "reason": "Appears in results but does not match the subject name",
                    "source_url": url,
                })
        return confidence, alternatives
    except Exception as exc:  # noqa: BLE001
        logger.log_warning(f"Disambiguation failed (non-critical): {exc}")
        return None, []


def _build_relationships(structured_data, company_records, sanctions_hits) -> list[dict]:
    """Derive typed relationship edges with sources where available (Faz 3.2)."""
    rels: list[dict] = []
    subject = structured_data.get("name") or ""
    try:
        for conn in (structured_data.get("network_connections") or []):
            if isinstance(conn, dict) and conn.get("name"):
                rels.append({
                    "from": subject,
                    "to": conn["name"],
                    "type": conn.get("relation") or conn.get("role") or "associate",
                    "source_url": "",
                })
        for rec in (company_records or []):
            if isinstance(rec, dict) and rec.get("company_name"):
                rels.append({
                    "from": subject,
                    "to": rec["company_name"],
                    "type": rec.get("role") or "affiliation",
                    "source_url": rec.get("source_url", ""),
                })
        for hit in (sanctions_hits or []):
            if hit.get("name"):
                rels.append({
                    "from": subject,
                    "to": hit["name"],
                    "type": f"sanctions:{hit.get('list_name', '')}",
                    "source_url": hit.get("source_url", ""),
                })
    except Exception as exc:  # noqa: BLE001
        logger.log_warning(f"Relationship assembly failed (non-critical): {exc}")
    return rels


class PostAnalysisRunnerStep(PipelineStep):
    def __init__(
        self,
        ai_service: Any,
        breach_orchestrator: Any,
        score_service: Any,
        weather_service: Any,
        darkweb_service: Any = None,
        geoint_service: Any = None,
        psychological_service: Any = None,
        predictive_service: Any = None,
    ) -> None:
        self._ai = ai_service
        self._breach_orch = breach_orchestrator
        self._score = score_service
        self._weather = weather_service
        self._darkweb = darkweb_service
        self._geoint = geoint_service
        self._psych = psychological_service
        self._predictor = predictive_service

    @property
    def name(self) -> str:
        return "post_analysis_runner"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        from app.agents.security_agent import SecurityAgent
        from app.agents.social_media_agent import SocialMediaAgent

        settings = get_settings()
        orch_result = ctx.orch_result
        github_data = ctx.github_data
        social_profiles = orch_result.social_profiles
        wiki_image, web_results, deep_context, raw_sources = ctx.search_results  # type: ignore[misc]

        # Step 1: Extract structured profile data — everything else depends on this
        structured_data = await self._ai.extract_profile_data(ctx.ai_response, ctx.real_name)

        # Step 2: Fast synchronous work (no I/O)
        algo_issues = SecurityAgent.cross_validate(
            github_data or {}, social_profiles, web_results or '', ctx.real_name, ctx.username
        )
        ai_issues = structured_data.get('cross_validation_issues', [])
        if not isinstance(ai_issues, list):
            ai_issues = [str(ai_issues)] if ai_issues else []
        ai_issues = [str(i) for i in ai_issues if i]
        all_issues = list(dict.fromkeys(algo_issues + ai_issues))
        logger.log_action(f"Cross-validation complete: {len(all_issues)} issue(s) detected")

        weather_info = None
        if structured_data.get('capital_city'):
            weather_info = self._weather.get_weather(structured_data['capital_city'])

        logger.log_action("Computing Digital Impact Score...")
        score_result = self._score.calculate_score(
            github_data=github_data,
            social_profiles=social_profiles,
            raw_sources=raw_sources,
            web_results=web_results or '',
        )

        platform_activity = (
            orch_result.platform_activity
            or SocialMediaAgent._compute_platform_activity(github_data, social_profiles)
        )

        # Step 3: Fan-out all slow async I/O concurrently
        async def _run_breach() -> list:
            return await self._breach_orch.run_breach_check(
                emails=structured_data.get('email_addresses', [])
            )

        async def _run_darkweb() -> dict:
            if not self._darkweb:
                return {}
            return await self._darkweb.aggregate_deep_intel(
                emails=structured_data.get('email_addresses', []),
                username=ctx.username,
                real_name=ctx.real_name,
            )

        async def _run_geoint() -> tuple:
            if not self._geoint:
                return [], None
            g_data = await self._geoint.aggregate_locations(
                location_country=structured_data.get('estimated_location'),
                location_city=structured_data.get('capital_city'),
                company_records=orch_result.company_records,
            )
            commit_timestamps = []
            if github_data and github_data.get('recent_commits'):
                commit_timestamps = [
                    c.get('date', '') for c in github_data['recent_commits'] if c.get('date')
                ]
            tz = None
            if commit_timestamps:
                tz = self._geoint.analyze_activity_times(commit_timestamps)
                logger.log_action(
                    f"Timezone analysis: {tz.get('inferred_timezone', 'N/A')}"
                )
            return g_data, tz

        async def _run_psychological() -> Any:
            # Governance gate (Faz 4.1) — enabled by default, toggleable via config.
            if not (self._psych and ctx.context and settings.enable_psychological_analysis):
                return None
            return await self._psych.analyze(
                context=ctx.context,
                deep_context=ctx.deep_context or "",
                sentiment_report=ctx.sentiment_report,
                structured_data=structured_data,
            )

        async def _run_predictive() -> Any:
            # Governance gate (Faz 4.1) — enabled by default, toggleable via config.
            if not (self._predictor and settings.enable_predictive_analysis):
                return None
            return await self._predictor.generate_predictions(
                github_data=github_data,
                social_profiles=social_profiles,
                platform_activity=platform_activity,
                timezone_analysis=None,
                structured_data=structured_data,
                deep_context=ctx.deep_context or "",
            )

        def _derived_domains() -> list:
            return domain_intel_service.derive_domains(
                structured_data.get('email_addresses', []),
                (github_data or {}).get('blog'),
            )

        async def _run_domain() -> list:
            domains = _derived_domains()
            if not domains:
                return []
            return await domain_intel_service.aggregate(domains)

        async def _run_archive() -> list:
            social_urls = _collect_social_urls(social_profiles, github_data)
            urls = archive_service.derive_urls(
                social_urls, (github_data or {}).get('blog'), _derived_domains()
            )
            if not urls:
                return []
            return await archive_service.aggregate(urls)

        async def _run_scholarly() -> list:
            return await scholarly_service.aggregate(ctx.real_name)

        async def _run_sanctions() -> list:
            return await sanctions_service.check(ctx.real_name)

        (
            breach_result, darkweb_result, geoint_result,
            psych_result, pred_result, domain_result,
            archive_result, scholarly_result, sanctions_result,
        ) = await asyncio.gather(
            _run_breach(),
            _run_darkweb(),
            _run_geoint(),
            _run_psychological(),
            _run_predictive(),
            _run_domain(),
            _run_archive(),
            _run_scholarly(),
            _run_sanctions(),
            return_exceptions=True,
        )

        # Unpack breach
        data_breaches: list = []
        if isinstance(breach_result, Exception):
            logger.log_warning(f"Breach check failed (non-critical): {breach_result}")
        elif breach_result:
            data_breaches = breach_result

        # Unpack darkweb
        darkweb_intel: dict = {}
        if isinstance(darkweb_result, Exception):
            logger.log_warning(f"Dark web scan failed (non-critical): {darkweb_result}")
        elif darkweb_result:
            darkweb_intel = darkweb_result
            paste_count = len(darkweb_intel.get('paste_exposures', []))
            leak_count = len(darkweb_intel.get('leak_results', []))
            if paste_count or leak_count:
                logger.log_warning(
                    f"DARK WEB INTEL: {paste_count} paste(s), {leak_count} leak(s) detected"
                )
            else:
                logger.log_success("Dark web scan: No additional exposures detected")

        for paste in darkweb_intel.get('paste_exposures', []):
            data_breaches.append(paste)

        # Unpack geoint
        geoint_data: list = []
        timezone_analysis = None
        if isinstance(geoint_result, Exception):
            logger.log_warning(f"GEOINT aggregation failed (non-critical): {geoint_result}")
        elif geoint_result:
            geoint_data, timezone_analysis = geoint_result
            if geoint_data:
                logger.log_success(f"GEOINT: {len(geoint_data)} location(s) mapped")

        phone_numbers = orch_result.phone_numbers

        # Unpack psychological
        psychological_analysis = None
        if isinstance(psych_result, Exception):
            logger.log_warning(f"Psychological analysis failed (non-critical): {psych_result}")
        else:
            psychological_analysis = psych_result

        # Unpack predictive
        prediction_data = None
        if isinstance(pred_result, Exception):
            logger.log_warning(f"Predictive analysis failed (non-critical): {pred_result}")
        else:
            prediction_data = pred_result

        # Unpack domain intel + derive provenance claims (Citation/Claim foundation)
        domain_intel: list = []
        claims: list = []
        if isinstance(domain_result, Exception):
            logger.log_warning(f"Domain intel failed (non-critical): {domain_result}")
        elif domain_result:
            domain_intel = domain_result
            for rec in domain_intel:
                claims.append(
                    Claim(
                        field="domain",
                        value=rec.get("domain", ""),
                        corroboration_count=1,
                        citations=[
                            Citation(
                                url=rec.get("source_url", ""),
                                title=rec.get("registrar") or rec.get("domain"),
                                retrieved_at=rec.get("retrieved_at"),
                                confidence=rec.get("confidence", 0.8),
                            )
                        ],
                    ).model_dump()
                )
            logger.log_success(f"Domain intel: {len(domain_intel)} domain(s) mapped")

        # Unpack archive snapshots
        archive_snapshots: list = []
        if isinstance(archive_result, Exception):
            logger.log_warning(f"Archive intel failed (non-critical): {archive_result}")
        elif archive_result:
            archive_snapshots = archive_result

        # Unpack scholarly records
        scholarly_records: list = []
        if isinstance(scholarly_result, Exception):
            logger.log_warning(f"Scholarly intel failed (non-critical): {scholarly_result}")
        elif scholarly_result:
            scholarly_records = scholarly_result

        # Unpack sanctions hits
        sanctions_hits: list = []
        if isinstance(sanctions_result, Exception):
            logger.log_warning(f"Sanctions screening failed (non-critical): {sanctions_result}")
        elif sanctions_result:
            sanctions_hits = sanctions_result

        # --- Provenance, timeline, disambiguation, relationships (Faz 2.2–2.5, 3.2) ---
        claims.extend(_build_claims(
            structured_data, orch_result.company_records, data_breaches,
            sanctions_hits, scholarly_records, all_issues,
        ))
        timeline = _build_timeline(
            github_data, data_breaches, orch_result.company_records, archive_snapshots,
        )
        subject_confidence, alternative_candidates = _assess_disambiguation(
            ctx.real_name, raw_sources, structured_data,
        )
        relationships = _build_relationships(
            structured_data, orch_result.company_records, sanctions_hits,
        )

        logger.log_success("Post-analysis complete")

        ctx.post_analysis = {
            'structured_data': structured_data,
            'data_breaches': data_breaches,
            'all_issues': all_issues,
            'weather_info': weather_info,
            'score_result': score_result,
            'phone_numbers': phone_numbers,
            'platform_activity': platform_activity,
            'darkweb_intel': darkweb_intel,
            'geoint_data': geoint_data,
            'timezone_analysis': timezone_analysis,
            'psychological_analysis': psychological_analysis,
            'prediction_data': prediction_data,
            'domain_intel': domain_intel,
            'claims': claims,
            'archive_snapshots': archive_snapshots,
            'scholarly_records': scholarly_records,
            'sanctions_hits': sanctions_hits,
            'timeline': timeline,
            'subject_confidence': subject_confidence,
            'alternative_candidates': alternative_candidates,
            'relationships': relationships,
        }
        return ctx
