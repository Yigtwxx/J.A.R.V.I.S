import requests
from typing import Optional, Dict, Any
from app.utils.logger import logger

class WeatherService:
    """Service for fetching weather data using Open-Meteo (Free, no API key needed)"""
    
    def __init__(self):
        self.geo_url = "https://geocoding-api.open-meteo.com/v1/search"
        self.weather_url = "https://api.open-meteo.com/v1/forecast"
        self.session = requests.Session()
    
    def get_weather(self, city: str) -> Optional[Dict[str, Any]]:
        """
        Fetch current weather for a city
        Returns dict with temp, description, and windspeed
        """
        try:
            if not city:
                return None
                
            logger.log_thought(f"Scanning atmospheric conditions for metropolitan hub: {city}")
            
            # Sanitize the city name
            search_city = city.split(',')[0].strip()
            search_city = search_city.replace(' D.C.', '').replace(' D.C', '')
            
            geo_params = {
                "name": search_city,
                "count": 1,
                "language": "en",
                "format": "json"
            }
            
            geo_res = self.session.get(self.geo_url, params=geo_params, timeout=5)
            geo_data = geo_res.json()
            
            if not geo_data.get('results'):
                logger.log_warning(f"Metropolitan hub {city} (search: {search_city}) not found in global coordinate grid.")
                return None
                
            location = geo_data['results'][0]
            lat = location['latitude']
            lon = location['longitude']
            country = location.get('country', 'Unknown')
            
            # 2. Weather: Get current weather for lat/long
            weather_params = {
                "latitude": lat,
                "longitude": lon,
                "current_weather": "true",
                "timezone": "auto"
            }
            
            weather_res = self.session.get(self.weather_url, params=weather_params, timeout=5)
            weather_data = weather_res.json()
            
            if 'current_weather' not in weather_data:
                logger.log_warning(f"Atmospheric sensor failure for coordinates: {lat}, {lon}")
                return None
                
            current = weather_data['current_weather']
            
            # Map weather codes to descriptions
            # Simplified WMO Weather interpretation codes
            weather_codes = {
                0: "Clear sky",
                1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
                45: "Fog", 48: "Depositing rime fog",
                51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
                61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
                71: "Slight snow fall", 73: "Moderate snow fall", 75: "Heavy snow fall",
                80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
                95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail"
            }
            
            description = weather_codes.get(current['weathercode'], "Unknown conditions")
            
            result = {
                "city": city,
                "country": country,
                "temperature": current['temperature'],
                "description": description,
                "windspeed": current['windspeed'],
                "is_day": current['is_day'] == 1
            }
            
            logger.log_success(f"Atmospheric data synchronized for {city}: {current['temperature']}°C, {description}")
            return result
            
        except Exception as e:
            logger.log_error(f"Weather data synchronization failed: {e}")
            return None
