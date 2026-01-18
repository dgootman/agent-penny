import requests 

class WeatherProvider:
    def __init__(self):
        self.tools = [
            self.get_current_location,
            self.get_weather_forecast,
        ]
    
    """
    Fetches the user's current location based on IP. More accurate than just calling wttr.in directly.
    """
    def get_current_location(self):
        return requests.get("https://ipinfo.io/json").json()
    
    """
    Provides forecast based on location. Agent can request weather for other locations based on query.
    """
    def get_weather_forecast(self, location: str):
        return requests.get(f"https://wttr.in/{location}?format=j1").json()