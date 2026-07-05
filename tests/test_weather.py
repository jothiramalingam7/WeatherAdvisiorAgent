import pytest
import httpx
from unittest.mock import MagicMock
from backend.services.weather import (
    WeatherService,
    WeatherData,
    CityNotFoundError,
    RateLimitError,
    WeatherAPIError
)

# Mock responses from OpenWeatherMap API
MOCK_CURRENT_WEATHER = {
    "name": "Coimbatore",
    "coord": {"lat": 11.0168, "lon": 76.9558},
    "main": {
        "temp": 34.2,
        "feels_like": 41.5,
        "humidity": 78
    },
    "wind": {
        "speed": 4.1
    },
    "weather": [
        {"main": "Clouds", "description": "scattered clouds"}
    ]
}

MOCK_FORECAST = {
    "list": [
        {
            "dt_txt": "2026-07-04 12:00:00",
            "main": {"temp": 32.5, "feels_like": 38.2},
            "weather": [{"main": "Rain"}],
            "pop": 0.8  # 80% chance of rain
        },
        {
            "dt_txt": "2026-07-04 15:00:00",
            "main": {"temp": 30.0, "feels_like": 35.0},
            "weather": [{"main": "Clouds"}],
            "pop": 0.4
        }
    ]
}

MOCK_UV_INDEX = {
    "value": 8.5
}

@pytest.mark.asyncio
async def test_fetch_weather_by_city_success(mocker):
    # Initialize service with a dummy key
    service = WeatherService(api_key="dummy_key", cache_ttl=60)
    
    # Mock httpx.AsyncClient.get to handle multiple endpoints
    mock_get = mocker.patch("httpx.AsyncClient.get", new_callable=mocker.AsyncMock)
    
    # Setup return values based on endpoint URL
    async def mock_get_side_effect(url, params=None, timeout=None):
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        
        if "/weather" in url:
            mock_response.json.return_value = MOCK_CURRENT_WEATHER
        elif "/forecast" in url:
            mock_response.json.return_value = MOCK_FORECAST
        elif "/uvi" in url:
            mock_response.json.return_value = MOCK_UV_INDEX
        else:
            mock_response.json.return_value = {}
        return mock_response
        
    mock_get.side_effect = mock_get_side_effect

    # Call service
    data = await service.fetch_weather_by_city("Coimbatore")
    
    # Assertions
    assert isinstance(data, WeatherData)
    assert data.city_name == "Coimbatore"
    assert data.temperature == 34.2
    assert data.feels_like == 41.5
    assert data.humidity == 78
    assert data.wind_speed == 4.1
    assert data.condition == "Scattered clouds"
    assert data.uv_index == 8.5
    assert data.chance_of_rain == 0.8  # From the first forecast item
    assert len(data.forecast) == 2
    
    # Verify calls
    assert mock_get.call_count == 3

@pytest.mark.asyncio
async def test_weather_cache_hit(mocker):
    service = WeatherService(api_key="dummy_key", cache_ttl=10)
    mock_get = mocker.patch("httpx.AsyncClient.get", new_callable=mocker.AsyncMock)
    
    # Setup response
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.side_effect = [MOCK_CURRENT_WEATHER, MOCK_FORECAST, MOCK_UV_INDEX]
    mock_get.return_value = mock_response

    # Fetch 1st time (Cache Miss -> Calls API)
    data1 = await service.fetch_weather_by_city("Coimbatore")
    
    # Fetch 2nd time (Cache Hit -> Does not call API)
    data2 = await service.fetch_weather_by_city("Coimbatore")
    
    assert data1 == data2
    assert mock_get.call_count == 3  # Calls were made only in the first call

@pytest.mark.asyncio
async def test_city_not_found(mocker):
    service = WeatherService(api_key="dummy_key")
    mock_get = mocker.patch("httpx.AsyncClient.get", new_callable=mocker.AsyncMock)
    
    # Setup response with 404 error
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 404
    mock_response.json.return_value = {"message": "city not found"}
    mock_get.return_value = mock_response

    with pytest.raises(CityNotFoundError) as exc_info:
        await service.fetch_weather_by_city("InvalidCity")
        
    assert exc_info.value.status_code == 404
    assert "City not found" in str(exc_info.value)

@pytest.mark.asyncio
async def test_rate_limit_exceeded(mocker):
    service = WeatherService(api_key="dummy_key")
    mock_get = mocker.patch("httpx.AsyncClient.get", new_callable=mocker.AsyncMock)
    
    # Setup response with 429 error
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 429
    mock_response.json.return_value = {"message": "Rate limit exceeded"}
    mock_get.return_value = mock_response

    with pytest.raises(RateLimitError) as exc_info:
        await service.fetch_weather_by_city("Coimbatore")
        
    assert exc_info.value.status_code == 429
    assert "Rate limit exceeded" in str(exc_info.value)

@pytest.mark.asyncio
async def test_api_timeout(mocker):
    service = WeatherService(api_key="dummy_key")
    mock_get = mocker.patch("httpx.AsyncClient.get", new_callable=mocker.AsyncMock)
    mock_get.side_effect = httpx.TimeoutException("Timeout")

    with pytest.raises(WeatherAPIError) as exc_info:
        await service.fetch_weather_by_city("Coimbatore")
        
    assert "timed out" in str(exc_info.value)
