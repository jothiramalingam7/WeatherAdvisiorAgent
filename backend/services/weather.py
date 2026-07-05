import os
import time
from typing import Dict, List, Tuple, Optional, Any
import httpx
from pydantic import BaseModel, Field

# -------------------------------------------------------------
# Custom Exceptions
# -------------------------------------------------------------
class WeatherAPIError(Exception):
    """Base exception for all weather API related issues."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code

class CityNotFoundError(WeatherAPIError):
    """Raised when the specified city is not found."""
    pass

class RateLimitError(WeatherAPIError):
    """Raised when the API rate limit is exceeded."""
    pass

# -------------------------------------------------------------
# Data Transfer Objects (DTOs)
# -------------------------------------------------------------
class ForecastItem(BaseModel):
    dt_txt: str = Field(..., description="Timestamp of the forecast interval")
    temp: float = Field(..., description="Temperature in Celsius")
    feels_like: float = Field(..., description="Feels-like temperature in Celsius")
    condition: str = Field(..., description="Short weather condition (e.g. Rain, Clouds)")
    chance_of_rain: float = Field(..., description="Probability of precipitation (0.0 to 1.0)")

class WeatherData(BaseModel):
    city_name: str = Field(..., description="City name")
    lat: float = Field(..., description="Latitude")
    lon: float = Field(..., description="Longitude")
    country: str = Field(default="Unknown", description="Country code")
    temperature: float = Field(..., description="Current temperature in Celsius")
    feels_like: float = Field(..., description="Current feels-like temperature in Celsius")
    humidity: int = Field(..., description="Humidity percentage")
    wind_speed: float = Field(..., description="Wind speed in m/s")
    condition: str = Field(..., description="Current weather condition description")
    uv_index: float = Field(default=0.0, description="UV Index")
    chance_of_rain: float = Field(default=0.0, description="Current chance of rain (0.0 to 1.0)")
    alerts: List[str] = Field(default_factory=list, description="Active weather alerts")
    forecast: List[ForecastItem] = Field(default_factory=list, description="5-day forecast (3-hour intervals)")

# -------------------------------------------------------------
# In-Memory Cache
# -------------------------------------------------------------
class WeatherCache:
    def __init__(self, ttl_seconds: int = 600):
        # Key: query identifier (string or coordinates tuple), Value: (WeatherData, time_stored)
        self._cache: Dict[Any, Tuple[WeatherData, float]] = {}
        self.ttl = ttl_seconds

    def get(self, key: Any) -> Optional[WeatherData]:
        if key in self._cache:
            data, timestamp = self._cache[key]
            if time.time() - timestamp < self.ttl:
                return data
            else:
                del self._cache[key]
        return None

    def set(self, key: Any, data: WeatherData) -> None:
        self._cache[key] = (data, time.time())

    def clear(self) -> None:
        self._cache.clear()

# -------------------------------------------------------------
# Weather Service Client
# -------------------------------------------------------------
class WeatherService:
    def __init__(self, api_key: Optional[str] = None, cache_ttl: int = 600):
        # Read from environment variables if not passed directly
        self.api_key = api_key or os.getenv("OPENWEATHERMAP_API_KEY")
        self.base_url = "https://api.openweathermap.org/data/2.5"
        self.cache = WeatherCache(ttl_seconds=cache_ttl)

    async def fetch_weather_by_city(self, city_name: str) -> WeatherData:
        """Fetch current weather and forecast for a given city name."""
        if not self.api_key:
            raise WeatherAPIError("OpenWeatherMap API Key is missing. Set OPENWEATHERMAP_API_KEY env variable.")

        # Check cache
        cache_key = f"city:{city_name.lower().strip()}"
        cached_data = self.cache.get(cache_key)
        if cached_data:
            return cached_data

        async with httpx.AsyncClient() as client:
            # 1. Resolve coordinates first via Geocoding or direct Weather API lookup
            # Let's perform a current weather query by city name to get lat/lon and current weather metrics
            current_url = f"{self.base_url}/weather"
            params = {
                "q": city_name,
                "appid": self.api_key,
                "units": "metric"
            }
            try:
                response = await client.get(current_url, params=params, timeout=10.0)
            except httpx.TimeoutException:
                raise WeatherAPIError("Connection to OpenWeatherMap timed out.", status_code=504)
            except httpx.RequestError as exc:
                raise WeatherAPIError(f"HTTP Request failed: {exc}")

            self._validate_response(response)
            current_data = response.json()

            lat = current_data["coord"]["lat"]
            lon = current_data["coord"]["lon"]

            # 2. Fetch the 5-day forecast (which is by coordinates or city id)
            forecast_data = await self._fetch_forecast(client, lat, lon)

            # 3. Fetch UV index if possible (note: requires latitude/longitude)
            uv_index = await self._fetch_uv_index(client, lat, lon)

            # 4. Normalize and build WeatherData DTO
            weather_data = self._normalize_weather(current_data, forecast_data, uv_index)

            # Cache the result under both the city key and coordinates key
            self.cache.set(cache_key, weather_data)
            self.cache.set(f"coords:{lat:.4f},{lon:.4f}", weather_data)

            return weather_data

    async def fetch_weather_by_coords(self, lat: float, lon: float) -> WeatherData:
        """Fetch current weather and forecast for given latitude and longitude."""
        if not self.api_key:
            raise WeatherAPIError("OpenWeatherMap API Key is missing. Set OPENWEATHERMAP_API_KEY env variable.")

        # Check cache (round to 4 decimal places for consistency)
        cache_key = f"coords:{lat:.4f},{lon:.4f}"
        cached_data = self.cache.get(cache_key)
        if cached_data:
            return cached_data

        async with httpx.AsyncClient() as client:
            current_url = f"{self.base_url}/weather"
            params = {
                "lat": lat,
                "lon": lon,
                "appid": self.api_key,
                "units": "metric"
            }
            try:
                response = await client.get(current_url, params=params, timeout=10.0)
            except httpx.TimeoutException:
                raise WeatherAPIError("Connection to OpenWeatherMap timed out.", status_code=504)
            except httpx.RequestError as exc:
                raise WeatherAPIError(f"HTTP Request failed: {exc}")

            self._validate_response(response)
            current_data = response.json()

            # Fetch the 5-day forecast
            forecast_data = await self._fetch_forecast(client, lat, lon)

            # Fetch UV index
            uv_index = await self._fetch_uv_index(client, lat, lon)

            # Normalize and build DTO
            weather_data = self._normalize_weather(current_data, forecast_data, uv_index)

            # Cache response
            self.cache.set(cache_key, weather_data)
            self.cache.set(f"city:{weather_data.city_name.lower().strip()}", weather_data)

            return weather_data

    async def _fetch_forecast(self, client: httpx.AsyncClient, lat: float, lon: float) -> Dict[str, Any]:
        forecast_url = f"{self.base_url}/forecast"
        params = {
            "lat": lat,
            "lon": lon,
            "appid": self.api_key,
            "units": "metric"
        }
        try:
            response = await client.get(forecast_url, params=params, timeout=10.0)
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass  # Fallback to empty forecast on failure
        return {"list": []}

    async def _fetch_uv_index(self, client: httpx.AsyncClient, lat: float, lon: float) -> float:
        # OpenWeatherMap 2.5 UV index endpoint
        uv_url = f"{self.base_url}/uvi"
        params = {
            "lat": lat,
            "lon": lon,
            "appid": self.api_key
        }
        try:
            response = await client.get(uv_url, params=params, timeout=5.0)
            if response.status_code == 200:
                return float(response.json().get("value", 0.0))
        except Exception:
            pass  # Fallback to 0.0 on failure
        return 0.0

    def _validate_response(self, response: httpx.Response) -> None:
        status = response.status_code
        if status == 200:
            return
        
        try:
            err_msg = response.json().get("message", "Unknown error occurred.")
        except Exception:
            err_msg = response.text

        if status == 404:
            raise CityNotFoundError(f"City not found: {err_msg}", status_code=404)
        elif status == 429:
            raise RateLimitError(f"API Rate limit exceeded: {err_msg}", status_code=429)
        else:
            raise WeatherAPIError(f"API request failed with status {status}: {err_msg}", status_code=status)

    def _normalize_weather(self, current: Dict[str, Any], forecast: Dict[str, Any], uv_index: float) -> WeatherData:
        # Extract current weather parameters
        main = current.get("main", {})
        wind = current.get("wind", {})
        weather_list = current.get("weather", [{}])
        weather_desc = weather_list[0].get("description", "no description")
        weather_cond = weather_list[0].get("main", "Clear")

        # Map forecast items
        forecast_items: List[ForecastItem] = []
        forecast_list = forecast.get("list", [])
        
        # Calculate current chance of rain: check the first available forecast pop
        chance_of_rain = 0.0
        if forecast_list:
            # pop (probability of precipitation) is between 0.0 and 1.0 in OWM 5-day forecast
            chance_of_rain = float(forecast_list[0].get("pop", 0.0))

        for item in forecast_list[:8]:  # Limit to next 24 hours (8 intervals of 3 hours)
            item_main = item.get("main", {})
            item_weather = item.get("weather", [{}])[0]
            forecast_items.append(
                ForecastItem(
                    dt_txt=item.get("dt_txt", ""),
                    temp=float(item_main.get("temp", 0.0)),
                    feels_like=float(item_main.get("feels_like", 0.0)),
                    condition=item_weather.get("main", "Clear"),
                    chance_of_rain=float(item.get("pop", 0.0))
                )
            )

        # Build alerts list (default empty for 2.5 current weather)
        alerts: List[str] = []

        return WeatherData(
            city_name=current.get("name", "Unknown"),
            lat=float(current.get("coord", {}).get("lat", 0.0)),
            lon=float(current.get("coord", {}).get("lon", 0.0)),
            country=current.get("sys", {}).get("country", "Unknown"),
            temperature=float(main.get("temp", 0.0)),
            feels_like=float(main.get("feels_like", 0.0)),
            humidity=int(main.get("humidity", 0)),
            wind_speed=float(wind.get("speed", 0.0)),
            condition=weather_desc.capitalize(),
            uv_index=uv_index,
            chance_of_rain=chance_of_rain,
            alerts=alerts,
            forecast=forecast_items
        )
