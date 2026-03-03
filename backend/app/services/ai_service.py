import ollama
from typing import Dict, Any
from app.config import get_settings
from app.jarvis_logger import logger
import warnings
import json

# Suppress warnings
warnings.filterwarnings('ignore')

settings = get_settings()


class AIService:
    """Service for AI interactions using Ollama"""
    
    def __init__(self):
        self.model = settings.ollama_model
        self.client = ollama.AsyncClient()
    
    async def generate_response(self, prompt: str, context: Dict[str, Any] = None) -> str:
        """
        Generate AI response using Ollama
        """
        try:
            logger.log_thought(f"Constructing optimal search matrix and contextual parameters for query...")
            # Build the full prompt
            full_prompt = self._build_prompt(prompt, context)
            
            logger.log_action("Interrogating local AI models", target=self.model)
            # Call Ollama with streaming enabled
            stream = await self.client.generate(
                model=self.model,
                prompt=full_prompt,
                stream=True
            )
            
            full_response = ""
            async for chunk in stream:
                token = chunk['response']
                full_response += token
                # Stream directly to the frontend HUD
                logger.stream_token(token)
            
            logger.log_success("Model response synthesized.")
            return full_response
        
        except Exception as e:
            logger.log_error(f"Core failure during model synthesis: {str(e)}")
            return f"JARVIS encountered an error: {str(e)}"
    
    def _build_prompt(self, query: str, context: Dict[str, Any] = None) -> str:
        """Build comprehensive prompt for AI"""
        
        system_prompt = """You are JARVIS, an Elite Strategic Intelligence Analyst and advanced AI assistant.
 Your analysis is NEVER superficial. You produce DEEP, multi-paragraph intelligence dossiers.
You write like a seasoned intelligence analyst preparing a classified briefing for a high-ranking official.
Every section must be 3-5 detailed paragraphs minimum. Use analytical language ("Data suggests...", "Pattern analysis reveals...", "Cross-referencing indicates...").

CRITICAL IDENTITY CORRELATION RULES:
1. **EXACT MATCH PRIORITY**: You MUST ONLY analyze the specific identity requested: '{query}'.
2. **FAMOUS ENTITY DISCRIMINATION**: If the requested name is similar to a world-famous figure (e.g., 'Yiğit Erdoğan' vs 'Recep Tayyip Erdoğan' OR 'John Smith' vs 'John Smith (Celebrity)'), you MUST check the context for specific differentiators (age, location, job).
3. **HALLUCINATION BLOCK**: If the search context predominantly discusses the famous figure and NOT the specific target, you MUST DISCARD that context. It is better to state 'Insufficient verified intelligence' than to provide a profile of the wrong person.
4. **FALLBACK PROTOCOL**: If traditional biographical data (Wikipedia, News) is missing for the target, but Social Media profiles (GitHub, Twitter, LinkedIn) with bios are present, you MUST prioritize these social bios to build the profile. Social Media bios are the most reliable 'fallback' when a person isn't widely famous.

Format the intelligence dossier into ALL of these sections using **ALL CAPS BOLD** headers:

1. **STRATEGIC BIOGRAPHY**: Write 3-5 paragraphs. Cover their full life arc: early life and upbringing, education, pivotal career decisions, major turning points, and current position. Analyze WHY they made key decisions, what drove their ambition, and how their background shaped their trajectory. Include specific dates, institutions, and milestones.

2. **PSYCHOLOGICAL PROFILE & PUBLIC PERSONA**: Write 2-3 paragraphs analyzing their communication style, leadership approach, public image management, and personality patterns observable from interviews and public appearances. What motivates them? What patterns emerge in their decision-making?

3. **DIGITAL FOOTPRINT & MEDIA PRESENCE**: Write 2-3 paragraphs evaluating their cross-platform activity, social media strategy, branding consistency, audience engagement patterns, and online influence metrics. How do they present themselves digitally vs. in traditional media?

4. **NOTABLE ACHIEVEMENTS & MILESTONES**: Write 2-3 paragraphs detailing their most significant accomplishments with specific context — awards, records, breakthrough moments, landmark deals, publications, or innovations. Explain the IMPACT of each achievement.

5. **CONTROVERSIES & CRITICAL ANALYSIS**: Write 2-3 paragraphs covering any public controversies, criticisms, legal issues, or polarizing decisions. Analyze both sides objectively. What patterns emerge from these incidents?

6. **FIELD INFLUENCE & PROFESSIONAL NETWORK**: Write 2-3 paragraphs mapping their influence within their industry. Who are their key allies, mentors, proteges? What organizations, boards, or movements are they connected to? How have they shaped their field?

7. **PROTOTYPICAL RIVALS & COMPARABLE FIGURES**: Write 2-3 paragraphs identifying direct competitors, rivals, or comparable figures in their domain. Explain the nature of each relationship and what distinguishes the subject from these peers.

8. **TIMELINE OF KEY EVENTS**: Provide a chronological bullet list of 8-15 major life/career events with dates.

9. **FUTURE TRAJECTORY ANALYSIS**: Write 1-2 paragraphs with predictive analysis based on current patterns — where is this person likely headed? What upcoming projects, roles, or shifts can be anticipated?

10. **SOCIAL NODES**: Verified links formatted as clickable markdown: `[Platform Name](URL)`.

CRITICAL RULES:
- NEVER write single-sentence sections. Each section must be DEEPLY analytical with multiple paragraphs.
- Your total response should be at least 1500 words. Short responses are UNACCEPTABLE.
- Use ALL available context data to enrich your analysis. Cross-reference sources.
- If information is limited, state what is known and provide analytical hypotheses.
- Do not use excessive blank lines. Format clearly and compactly."""
        
        user_prompt = f"\n\nUser Query: {query}"
        user_prompt += f"\n\nCRITICAL RESTRICTION: You MUST ONLY write about the exact requested person: '{query}'. If the search context is about a CLEARLY DIFFERENT person (with a completely different name), you MUST IGNORE that context entirely. Do not invent information. If there is limited or no information about the specific requested person '{query}', simply state: 'Insufficient verified intelligence available for this individual.' Do NOT substitute another similar-sounding person."
        
        if context:
            context_str = "\n\nAvailable Context:"
            
            if context.get('github'):
                context_str += f"\n\nGitHub Profile:\n{context['github']}"
            
            if context.get('web_search'):
                context_str += f"\n\nWeb Search Results:\n{context['web_search']}"
            
            if context.get('social_media'):
                context_str += f"\n\nSocial Media Profiles:\n{context['social_media']}"
            
            if context.get('deep_context'):
                context_str += f"\n\nAdditional Intelligence (Deep Context):\n{context['deep_context']}"
            
            user_prompt += context_str
        
        return system_prompt.replace('{query}', query) + user_prompt
    
    async def extract_profile_data(self, ai_response: str, query: str) -> Dict[str, Any]:
        """
        Extract structured profile data from AI response
        """
        # Ask AI to structure the data
        extraction_prompt = f"""Based on this information about "{query}", 
extract and return ONLY a JSON object with these fields:
- name: string
- description: string (brief summary)
- similar_profiles: array of strings (names of similar people)
- estimated_location: string (guessed country)
- capital_city: string (capital of that country)
- social_media_score: integer (0-100, estimate based on number of linked accounts and recency of posts/activity)
- last_activity_summary: string (brief 2-4 word summary of when they were last active, e.g., "Active today", "Active last week", "No recent activity")
- cross_validation_issues: array of strings (Identify any significant inconsistencies across different data sources. E.g., 'GitHub location is Turkey but LinkedIn says USA' or 'Web results indicate doctor, GitHub indicates programmer'. If all sources match and refer to the same person, return an empty array [])

Previous Information:
{ai_response}

Return ONLY valid JSON, no other text."""
        
        try:
            logger.log_thought("Attempting to parse bio-data and network nodes from unstructured text...")
            response = await self.client.generate(
                model=self.model,
                prompt=extraction_prompt
            )
            
            # Try to parse JSON from response
            import json
            response_text = response['response'].strip()
            
            # Find JSON in response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx != -1 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                parsed_data = json.loads(json_str)
                logger.log_success("Bio-data nodes successfully extracted.")
                return parsed_data
            
            # Fallback
            logger.log_warning("Failed to locate clean JSON structure. Initiating fallback protocol.")
            return {
                "name": query,
                "description": ai_response[:500],
                "similar_profiles": [],
                "cross_validation_issues": []
            }
        
        except Exception as e:
            logger.log_error(f"Data extraction node failed: {e}")
            return {
                "name": query,
                "description": ai_response[:500] if ai_response else "",
                "similar_profiles": [],
                "cross_validation_issues": []
            }
