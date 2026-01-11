import ollama
from typing import Dict, Any
from app.config import get_settings
import warnings
import json

# Suppress warnings
warnings.filterwarnings('ignore')

settings = get_settings()


class AIService:
    """Service for AI interactions using Ollama"""
    
    def __init__(self):
        self.model = settings.ollama_model
        self.client = ollama
    
    async def generate_response(self, prompt: str, context: Dict[str, Any] = None) -> str:
        """
        Generate AI response using Ollama
        
        Args:
            prompt: User's query
            context: Additional context (search results, profiles, etc.)
        
        Returns:
            AI generated response
        """
        try:
            # Build the full prompt
            full_prompt = self._build_prompt(prompt, context)
            
            # Call Ollama
            response = self.client.generate(
                model=self.model,
                prompt=full_prompt
            )
            
            return response['response']
        
        except Exception as e:
            return f"JARVIS encountered an error: {str(e)}"
    
    def _build_prompt(self, query: str, context: Dict[str, Any] = None) -> str:
        """Build comprehensive prompt for AI"""
        
        system_prompt = """You are JARVIS, an advanced AI assistant inspired by Iron Man's AI.
You are sophisticated, helpful, and provide detailed information.
When searching for people, provide:
1. Their professional background
2. Social media profiles (if found)
3. Notable achievements or projects
4. Similar people in their field

Be concise but informative. Format your response clearly."""
        
        user_prompt = f"\n\nUser Query: {query}"
        
        if context:
            context_str = "\n\nAvailable Context:"
            
            if context.get('github'):
                context_str += f"\n\nGitHub Profile:\n{context['github']}"
            
            if context.get('web_search'):
                context_str += f"\n\nWeb Search Results:\n{context['web_search']}"
            
            if context.get('social_media'):
                context_str += f"\n\nSocial Media Profiles:\n{context['social_media']}"
            
            user_prompt += context_str
        
        return system_prompt + user_prompt
    
    async def extract_profile_data(self, ai_response: str, query: str) -> Dict[str, Any]:
        """
        Extract structured profile data from AI response
        
        Args:
            ai_response: AI's text response
            query: Original query
        
        Returns:
            Structured profile data
        """
        # Ask AI to structure the data
        extraction_prompt = f"""Based on this information about "{query}", 
extract and return ONLY a JSON object with these fields:
- name: string
- description: string (brief summary)
- similar_profiles: array of strings (names of similar people)

Previous Information:
{ai_response}

Return ONLY valid JSON, no other text."""
        
        try:
            response = self.client.generate(
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
                return json.loads(json_str)
            
            # Fallback
            return {
                "name": query,
                "description": ai_response[:500],
                "similar_profiles": []
            }
        
        except Exception as e:
            print(f"Error extracting profile data: {e}")
            return {
                "name": query,
                "description": ai_response[:500] if ai_response else "",
                "similar_profiles": []
            }
