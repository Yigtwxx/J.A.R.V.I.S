"""
Predictive Analysis Service
Generates probabilistic forecasts from temporal OSINT data patterns.
Uses gathered activity timestamps, platform presence, and behavioral indicators.
"""

import json
import re

import ollama

from app.config import get_settings
from app.utils.logger import logger

settings = get_settings()


class PredictiveAnalysisService:
    """Generates predictive forecasts from real temporal OSINT data."""

    def __init__(self):
        self.client = ollama.AsyncClient()
        self.model = settings.ollama_model

    @staticmethod
    def _strip_thinking(text: str) -> str:
        return re.sub(r"<think>[\s\S]*?</think>", "", text).strip()

    def _build_temporal_evidence(
        self,
        github_data: dict | None,
        social_profiles: dict,
        platform_activity: dict | None,
        timezone_analysis: dict | None,
        structured_data: dict | None,
        deep_context: str,
    ) -> str:
        """Compile temporal and behavioral data into an evidence block."""
        parts: list[str] = []

        # GitHub commit patterns
        if github_data:
            if github_data.get("recent_commits"):
                commits = github_data["recent_commits"][:20]
                commit_lines = []
                for c in commits:
                    date = c.get("date", "unknown")
                    msg = c.get("message", "")[:80]
                    commit_lines.append(f"  {date}: {msg}")
                parts.append(f"=== GITHUB COMMIT TIMELINE ===\n" + "\n".join(commit_lines))

            if github_data.get("public_repos"):
                parts.append(f"Public repos: {github_data['public_repos']}")
            if github_data.get("followers"):
                parts.append(f"Followers: {github_data['followers']}")
            if github_data.get("created_at"):
                parts.append(f"GitHub account created: {github_data['created_at']}")

        # Platform activity scores
        if platform_activity:
            activity_lines = [f"  {k}: {v}" for k, v in platform_activity.items() if v]
            if activity_lines:
                parts.append(f"=== PLATFORM ACTIVITY ===\n" + "\n".join(activity_lines))

        # Timezone and activity pattern
        if timezone_analysis:
            tz_info = (
                f"Inferred timezone: {timezone_analysis.get('inferred_timezone', 'N/A')}\n"
                f"Peak hours: {timezone_analysis.get('peak_hours', [])}\n"
                f"Activity pattern: {timezone_analysis.get('activity_pattern', 'N/A')}"
            )
            hourly = timezone_analysis.get("hourly_distribution", {})
            if hourly:
                tz_info += f"\nHourly distribution: {json.dumps(hourly)}"
            parts.append(f"=== TIMEZONE & ACTIVITY ANALYSIS ===\n{tz_info}")

        # Social profile presence
        active_platforms = [p for p, data in social_profiles.items() if data]
        if active_platforms:
            parts.append(f"=== ACTIVE PLATFORMS ===\n{', '.join(active_platforms)}")

        # Structured data signals
        if structured_data:
            if structured_data.get("email_addresses"):
                parts.append(f"Exposed emails: {len(structured_data['email_addresses'])}")
            if structured_data.get("data_breaches"):
                breach_dates = [
                    b.get("BreachDate", "unknown")
                    for b in structured_data["data_breaches"][:10]
                    if isinstance(b, dict)
                ]
                if breach_dates:
                    parts.append(f"=== BREACH TIMELINE ===\n{', '.join(breach_dates)}")
            if structured_data.get("network_connections"):
                parts.append(f"Known connections: {len(structured_data['network_connections'])}")

        # Deep context temporal mentions
        if deep_context:
            temporal_snippet = deep_context[:3000]
            parts.append(f"=== CONTEXTUAL CONTENT (temporal clues) ===\n{temporal_snippet}")

        return "\n\n".join(parts)

    async def generate_predictions(
        self,
        github_data: dict | None = None,
        social_profiles: dict | None = None,
        platform_activity: dict | None = None,
        timezone_analysis: dict | None = None,
        structured_data: dict | None = None,
        deep_context: str = "",
    ) -> dict | None:
        """
        Generate predictive forecasts from temporal OSINT data.

        Returns dict matching PredictiveAnalysis schema, or None on failure.
        """
        evidence = self._build_temporal_evidence(
            github_data, social_profiles or {}, platform_activity,
            timezone_analysis, structured_data, deep_context,
        )

        if len(evidence.strip()) < 80:
            logger.log_warning("Predictive analysis skipped: insufficient temporal data")
            return None

        prompt = f"""You are J.A.R.V.I.S., an elite intelligence analyst specializing in behavioral prediction and pattern analysis.

Based EXCLUSIVELY on the temporal and behavioral data below, generate probabilistic forecasts about the target.

RULES:
- Use ONLY the evidence provided. Do NOT fabricate data points.
- Express all probabilities as floats between 0.0 and 1.0.
- Be specific about timeframes and supporting evidence.
- Output ONLY a valid JSON object, no markdown formatting.

Required JSON Structure:
{{
  "predictions": [
    {{
      "category": "<activity|behavioral|security|financial>",
      "prediction": "<string: specific, actionable prediction>",
      "probability": <float 0.0-1.0>,
      "timeframe": "<24h|7d|30d|90d>",
      "supporting_evidence": ["<string: what data supports this prediction>"]
    }}
  ],
  "activity_pattern": {{
    "most_active_hours": [<integers 0-23>],
    "most_active_days": ["<day names>"],
    "posting_frequency": "<daily|weekly|monthly|sporadic|unknown>"
  }},
  "trend_direction": "<increasing|stable|decreasing|erratic>",
  "data_sufficiency": <float 0.0-1.0, how much data you had to work with>
}}

Generate 3-6 predictions across different categories when data allows.
For each prediction, provide at least 1 supporting evidence item.
Do NOT include ```json tags.

=== TEMPORAL & BEHAVIORAL INTELLIGENCE ===
{evidence}
"""

        try:
            logger.log_action("Running predictive analytics engine...")

            response = await self.client.generate(
                model=self.model,
                prompt=prompt,
                options={"temperature": 0.3, "top_p": 0.4},
            )

            response_text = self._strip_thinking(response["response"])

            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}") + 1

            if start_idx == -1 or end_idx <= start_idx:
                logger.log_error("Predictive analysis: no JSON in response")
                return None

            parsed = json.loads(response_text[start_idx:end_idx])

            # Build validated result
            predictions = []
            for p in parsed.get("predictions", []):
                if isinstance(p, dict) and "prediction" in p:
                    predictions.append({
                        "category": str(p.get("category", "behavioral")),
                        "prediction": str(p.get("prediction", "")),
                        "probability": max(0.0, min(1.0, float(p.get("probability", 0.5)))),
                        "timeframe": str(p.get("timeframe", "30d")),
                        "supporting_evidence": [str(e) for e in p.get("supporting_evidence", [])],
                    })

            result = {
                "predictions": predictions,
                "activity_pattern": parsed.get("activity_pattern"),
                "trend_direction": str(parsed.get("trend_direction", "stable")),
                "data_sufficiency": max(0.0, min(1.0, float(parsed.get("data_sufficiency", 0.5)))),
            }

            logger.log_success(f"Predictive analytics complete: {len(predictions)} forecast(s)")
            return result

        except json.JSONDecodeError as e:
            logger.log_error(f"Predictive analysis JSON parse failure: {e}")
        except Exception as e:
            logger.log_error(f"Predictive analysis failed: {e}")

        return None


predictive_analysis_service = PredictiveAnalysisService()
