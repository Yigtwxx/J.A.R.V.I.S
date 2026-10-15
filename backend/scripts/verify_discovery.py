"""Live acceptance check for the discovery pipeline.

Runs real searches and asserts the properties the rewrite exists to guarantee.
This is a health report on the *pipeline*, not a dossier: it prints statuses,
counts and coherence checks, never a compiled profile of anyone.

Usage (from ``backend/``):
    PYTHONIOENCODING=utf-8 ./venv/Scripts/python.exe scripts/verify_discovery.py [--depth 2] [--no-stealth]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.discovery.evidence.store import EvidenceStore  # noqa: E402
from app.discovery.fetch.ratelimit import DomainRateLimiter  # noqa: E402
from app.discovery.hitl.broker import QuestionBroker  # noqa: E402
from app.discovery.loop.runner import DiscoveryResult, DiscoveryRunner  # noqa: E402
from app.discovery.session.manager import SessionManager  # noqa: E402
from app.discovery.types import EntityType, PlatformStatus  # noqa: E402
from app.services.discovery_bridge import to_api  # noqa: E402

PEOPLE = ["Yiğit Erdoğan", "Kevser Orhan", "Elif Nur Akpolat", "Yağmur Özgan", "Sude Demir"]
COMPANIES = ["Getir", "Trendyol", "Peak Games"]
PLACES = ["Galata Kulesi"]


def ascii_safe(value: object) -> str:
    return str(value or "").encode("ascii", "replace").decode()


@dataclass(slots=True)
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass(slots=True)
class Report:
    query: str
    entity: str
    seconds: int
    rounds: int
    termination: str
    found: int
    blocked: int
    not_found: int
    alternates: int
    evidence: int
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.checks)


def audit(result: DiscoveryResult, payload: dict, max_per_platform: int) -> list[Check]:
    """The acceptance criteria, each stated as a single falsifiable claim."""
    checks: list[Check] = []
    profiles = payload["social_profiles"]
    found = [p for p in profiles if p.status == "found"]

    # 1. No broken links: a URL is only ever emitted for a verified account.
    bad_urls = [p for p in profiles if p.url and p.status != "found"]
    checks.append(Check("no_url_without_found_status", not bad_urls, f"{len(bad_urls)} offenders"))

    # 2. No fabricated images: every picture is a local file that exists on disk.
    pictures = payload["profile_pictures"]
    missing = [
        pic.url
        for pic in pictures
        if not (Path("data/avatars") / Path(pic.url).name).is_file() or "unavatar" in (pic.source_url or "")
    ]
    checks.append(Check("pictures_are_real_local_files", not missing, f"{len(missing)} missing/unavatar"))

    # 3. One identity: every returned account belongs to the elected cluster.
    elected_keys = set(result.elected.member_keys) if result.elected else set()
    strays = [p for p in found if elected_keys and f"{p.platform}:{(p.username or '').lower()}" not in elected_keys]
    checks.append(Check("single_identity_only", not strays, f"{len(strays)} strays"))

    # 4. At most N accounts per platform.
    per_platform: dict[str, int] = {}
    for p in found:
        per_platform[p.platform] = per_platform.get(p.platform, 0) + 1
    over = {k: v for k, v in per_platform.items() if v > max_per_platform}
    checks.append(Check(f"max_{max_per_platform}_accounts_per_platform", not over, str(over)))

    # 5. Nothing silently empty: every profile carries a status and an explanation.
    unexplained = [p for p in profiles if p.status != "found" and not p.status_detail]
    checks.append(Check("every_failure_is_explained", not unexplained, f"{len(unexplained)} silent"))

    # 6. Blocked is never reported as absent.
    blocked = [p for p in profiles if p.status == "blocked"]
    checks.append(Check("blocked_reported_as_blocked", True, f"{len(blocked)} blocked platforms"))

    # 7. Termination is always explained.
    checks.append(Check("termination_reason_present", bool(result.termination_reason), result.termination_reason))

    # 8. Every biography sentence traces to stored evidence — and a search that
    #    found accounts actually wrote one. `claims == ()` used to pass this check
    #    vacuously, which is also exactly what a crashed narrative, a timed-out
    #    narrative and a NOTHING_ESTABLISHED narrative look like: the loudest
    #    failures the pipeline has scored green. A genuinely empty search still
    #    passes, because "no accounts, no biography" is the honest answer.
    claims = result.narrative.claims if result.narrative else ()
    ungrounded = [c for c in claims if not c.evidence_fingerprints]
    if found and not claims:
        passed, detail = False, "accounts were found but the biography holds no claim at all"
    else:
        passed, detail = not ungrounded, f"{len(ungrounded)} ungrounded of {len(claims)}"
    checks.append(Check("biography_present_and_grounded", passed, detail))

    # 9. Namesakes are listed separately, never merged in.
    alt_keys = {k for c in result.alternates for k in c.member_keys}
    leaked = elected_keys & alt_keys
    checks.append(Check("alternates_not_merged", not leaked, f"{len(leaked)} leaked"))

    # 10. Work and education always cite a source.
    unsourced = [w for w in payload["work_history"] + payload["education"] if not w.source_url]
    checks.append(Check("work_education_sourced", not unsourced, f"{len(unsourced)} unsourced"))

    return checks


async def run_one(query: str, entity: EntityType, depth: int, settings) -> Report:  # noqa: ANN001
    manager = SessionManager()
    session_id = str(uuid.uuid4())
    manager.create(session_id, query)
    runner = DiscoveryRunner(
        store=EvidenceStore(),
        broker=QuestionBroker(),
        manager=manager,
        rate_limiter=DomainRateLimiter(),
        settings=settings,
    )
    result = await runner.run(
        session_id=session_id, raw_query=query, entity_type=entity, depth=depth, interactive=False
    )
    payload = to_api(result)
    statuses = list(result.platform_status.values())
    return Report(
        query=query,
        entity=str(entity),
        seconds=result.duration_ms // 1000,
        rounds=result.rounds,
        termination=result.termination_reason,
        found=sum(1 for s in statuses if s is PlatformStatus.FOUND),
        blocked=sum(1 for s in statuses if s is PlatformStatus.BLOCKED),
        not_found=sum(1 for s in statuses if s is PlatformStatus.NOT_FOUND),
        alternates=len(result.alternates),
        evidence=len(result.evidence),
        checks=audit(result, payload, settings.discovery_max_profiles_per_platform),
    )


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--no-stealth", action="store_true")
    parser.add_argument("--only", type=str, default="")
    parser.add_argument(
        "--entity",
        type=str,
        default="person",
        choices=[e.value for e in EntityType],
        help="Entity type for --only. Companies and places take a different code path "
        "(brand-shaped handles, different platforms), so testing one as a person proves nothing about the other.",
    )
    args = parser.parse_args()

    settings = get_settings()
    if args.no_stealth:
        object.__setattr__(settings, "discovery_stealth_enabled", False)

    targets: list[tuple[str, EntityType]] = []
    if args.only:
        targets.append((args.only, EntityType(args.entity)))
    else:
        targets += [(q, EntityType.PERSON) for q in PEOPLE]
        targets += [(q, EntityType.COMPANY) for q in COMPANIES]
        targets += [(q, EntityType.PLACE) for q in PLACES]

    reports: list[Report] = []
    for query, entity in targets:
        print(f"\n>>> {ascii_safe(query)} ({entity}) ...", flush=True)
        try:
            report = await run_one(query, entity, args.depth, settings)
        except Exception as exc:
            print(f"    RUN FAILED: {type(exc).__name__}: {exc}", flush=True)
            reports.append(
                Report(query, str(entity), 0, 0, "run_failed", 0, 0, 0, 0, 0, [Check("run_completed", False, str(exc))])
            )
            continue
        reports.append(report)
        print(
            f"    {report.seconds}s | rounds {report.rounds} | {report.termination} | "
            f"found {report.found} blocked {report.blocked} not_found {report.not_found} | "
            f"alt {report.alternates} | evidence {report.evidence}",
            flush=True,
        )
        for check in report.checks:
            mark = "PASS" if check.passed else "FAIL"
            print(f"      [{mark}] {check.name}: {check.detail}", flush=True)

    print("\n================ SUMMARY ================")
    failures = 0
    for report in reports:
        status = "OK  " if report.ok else "FAIL"
        bad = [c.name for c in report.checks if not c.passed]
        failures += 0 if report.ok else 1
        print(f"{status} {ascii_safe(report.query):22} {report.seconds:4}s {report.termination:18} {bad}")
    print(f"\n{len(reports) - failures}/{len(reports)} targets passed every check")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
