"""
Psychological Analysis Service
Generates psychological profiles, vulnerability assessments, and tactical recommendations
from real gathered OSINT data. Never uses mock data.
"""

import json
import re

import ollama

from app.config import get_settings
from app.utils.logger import logger

settings = get_settings()


class PsychologicalAnalysisService:
    """Produces psychological warfare intelligence from real OSINT data."""

    def __init__(self):
        self.client = ollama.AsyncClient()
        self.model = settings.ollama_model

    @staticmethod
    def _strip_thinking(text: str) -> str:
        return re.sub(r"<think>[\s\S]*?</think>", "", text).strip()

    def _build_evidence_block(
        self,
        context: dict,
        deep_context: str,
        sentiment_report: dict | None,
        structured_data: dict | None,
    ) -> str:
        """Compile all available real data into a single evidence block for the prompt."""
        parts: list[str] = []

        # Social media presence
        social = context.get("social_media", "")
        if social:
            parts.append(f"=== SOCIAL MEDIA PRESENCE ===\n{social[:3000]}")

        # Deep-scraped web content (writing style, topics, opinions)
        if deep_context:
            parts.append(f"=== DEEP WEB CONTENT ===\n{deep_context[:4000]}")

        # GitHub behaviour
        github = context.get("github", "")
        if github:
            parts.append(f"=== GITHUB ACTIVITY ===\n{github[:2000]}")

        # Sentiment baseline
        if sentiment_report:
            parts.append(
                f"=== SENTIMENT BASELINE ===\n"
                f"Positive: {sentiment_report.get('positive')}%  "
                f"Neutral: {sentiment_report.get('neutral')}%  "
                f"Negative: {sentiment_report.get('negative')}%\n"
                f"Dominant emotion: {sentiment_report.get('dominant_emotion')}\n"
                f"Summary: {sentiment_report.get('summary')}"
            )

        # Structured data (network, emails, breaches, cross-validation)
        if structured_data:
            if structured_data.get("network_connections"):
                conns = json.dumps(structured_data["network_connections"][:10], ensure_ascii=False)
                parts.append(f"=== NETWORK CONNECTIONS ===\n{conns}")
            if structured_data.get("email_addresses"):
                parts.append(f"=== EXPOSED EMAILS ===\n{', '.join(structured_data['email_addresses'])}")
            if structured_data.get("cross_validation_issues"):
                parts.append(
                    f"=== CROSS-VALIDATION ISSUES ===\n"
                    + "\n".join(structured_data["cross_validation_issues"])
                )
            if structured_data.get("data_breaches"):
                breach_names = [b.get("Name", "unknown") for b in structured_data["data_breaches"][:10]]
                parts.append(f"=== DATA BREACHES ===\n{', '.join(breach_names)}")

        return "\n\n".join(parts)

    async def analyze(
        self,
        context: dict,
        deep_context: str,
        sentiment_report: dict | None = None,
        structured_data: dict | None = None,
    ) -> dict | None:
        """
        Generate a psychological vulnerability analysis from real OSINT data.

        Returns dict matching PsychologicalAnalysis schema, or None on failure.
        """
        evidence = self._build_evidence_block(context, deep_context, sentiment_report, structured_data)

        if len(evidence.strip()) < 100:
            logger.log_warning("Psychological analysis skipped: insufficient evidence")
            return None

        prompt = f"""You are J.A.R.V.I.S., an elite intelligence analyst specializing in psychological profiling and human vulnerability assessment.

Based EXCLUSIVELY on the real gathered intelligence below, produce a psychological warfare analysis of the target.

RULES:
- Use ONLY the evidence provided. Do NOT fabricate, assume, or hallucinate information.
- If a section cannot be determined from the data, say "Insufficient data" rather than guessing.
- Write in English.
- Be specific and actionable in tactical recommendations.
- Output ONLY a valid JSON object, no markdown formatting.

Required JSON Structure:
{{
  "psychological_profile": "<string: 2-4 sentence narrative of personality type, communication style, emotional patterns based on evidence>",
  "strengths": ["<string: each a specific psychological strength observed in the data>"],
  "weaknesses": ["<string: each a specific psychological vulnerability or exploitable trait>"],
  "tactical_recommendations": ["<string: each a concrete tactic for gaining psychological advantage over this person>"],
  "social_engineering_vectors": [
    {{
      "vector": "<string: the attack surface, e.g. 'Public email exposure'>",
      "approach": "<string: how to exploit it>",
      "risk_level": "<low|medium|high>"
    }}
  ],
  "manipulation_resistance_score": <integer 1-100, higher = more resistant>,
  "confidence_level": <float 0.0-1.0, based on how much data you had>
}}

Provide at least 3 items for strengths, weaknesses, and tactical_recommendations when data allows.
Do NOT include ```json tags.

=== GATHERED INTELLIGENCE ===
{evidence}
"""

        try:
            logger.log_action("Initiating psychological warfare analysis...")

            response = await self.client.generate(
                model=self.model,
                prompt=prompt,
                options={"temperature": 0.3, "top_p": 0.4},
            )

            response_text = self._strip_thinking(response["response"])

            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}") + 1

            if start_idx == -1 or end_idx <= start_idx:
                logger.log_error("Psychological analysis: no JSON in response")
                return None

            parsed = json.loads(response_text[start_idx:end_idx])

            # Validate and clamp fields
            result = {
                "psychological_profile": str(parsed.get("psychological_profile", "Insufficient data")),
                "strengths": [str(s) for s in parsed.get("strengths", [])],
                "weaknesses": [str(w) for w in parsed.get("weaknesses", [])],
                "tactical_recommendations": [str(t) for t in parsed.get("tactical_recommendations", [])],
                "social_engineering_vectors": [],
                "manipulation_resistance_score": max(1, min(100, int(parsed.get("manipulation_resistance_score", 50)))),
                "confidence_level": max(0.0, min(1.0, float(parsed.get("confidence_level", 0.5)))),
            }

            for vec in parsed.get("social_engineering_vectors", []):
                if isinstance(vec, dict) and "vector" in vec:
                    result["social_engineering_vectors"].append({
                        "vector": str(vec.get("vector", "")),
                        "approach": str(vec.get("approach", "")),
                        "risk_level": str(vec.get("risk_level", "medium")).lower(),
                    })

            logger.log_success("Psychological warfare analysis complete")
            return result

        except json.JSONDecodeError as e:
            logger.log_error(f"Psychological analysis JSON parse failure: {e}")
        except Exception as e:
            logger.log_error(f"Psychological analysis failed: {e}")

        return None


psychological_analysis_service = PsychologicalAnalysisService()
