import json
# pyrefly: ignore [missing-import]
import pytest
import httpx
from unittest.mock import MagicMock
from sqlalchemy.orm import Session
from backend.services.advisory import AdvisoryService
from backend.db.models import Advisory, AdvisoryCategory

MOCK_SUCCESSFUL_ADVISORY = {
    "summary": "High heat indices make hydration critical.",
    "risk_level": "moderate",
    "recommendations": [
        "Drink plenty of water",
        "Avoid heavy exercise under direct sunlight",
        "Wear sunscreen"
    ],
    "category": "agriculture",
    "bottom_line": "Drink plenty of water and avoid midday sun.",
    "supporting_weather_data": "Temp: 34.2C, Humidity: 78% (OpenWeatherMap)",
    "reasoning": "High temperatures combined with high humidity increase heat risk.",
    "risks_and_alerts": "High temperature alert",
    "confidence_level": "High",
    "confidence_explanation": "Short term forecast is highly accurate.",
    "next_steps": "Monitor weather updates."
}

MOCK_GUARDRAIL_ADVISORY = {
    "summary": "I can only assist you with weather-safety queries. Please ask a weather-related question.",
    "risk_level": "low",
    "recommendations": ["Refrain from asking non-weather questions"],
    "category": "agriculture",
    "bottom_line": "Please ask a weather or agricultural-related question.",
    "supporting_weather_data": "N/A",
    "reasoning": "N/A",
    "risks_and_alerts": "None",
    "confidence_level": "High",
    "confidence_explanation": "Deterministic decline logic.",
    "next_steps": "Rephrase question."
}

@pytest.mark.asyncio
async def test_generate_advisory_gemini_success(mocker):
    # Initialize service with Gemini API Key
    service = AdvisoryService(gemini_api_key="test_gemini_key")
    
    # Mock httpx.AsyncClient.post
    mock_post = mocker.patch("httpx.AsyncClient.post", new_callable=mocker.AsyncMock)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": json.dumps(MOCK_SUCCESSFUL_ADVISORY)}]
                }
            }
        ]
    }
    mock_post.return_value = mock_response

    # Mock DB Session
    mock_db = MagicMock(spec=Session)

    weather_data = {"city_name": "Coimbatore", "temperature": 34.2, "humidity": 78, "condition": "Scattered clouds"}
    user_context = "Running with asthma"

    # Call service
    result = await service.generate_advisory(
        weather_data=weather_data,
        user_context=user_context,
        weather_query_id=10,
        db=mock_db
    )

    # Assertions
    assert result == MOCK_SUCCESSFUL_ADVISORY
    assert mock_post.call_count == 1
    
    # Verify mock DB was called to save the advisory
    assert mock_db.add.call_count == 1
    saved_advisory = mock_db.add.call_args[0][0]
    assert isinstance(saved_advisory, Advisory)
    assert saved_advisory.weather_query_id == 10
    assert saved_advisory.user_context == user_context
    assert saved_advisory.advisory_category == AdvisoryCategory.agriculture
    assert mock_db.commit.call_count == 1

@pytest.mark.asyncio
async def test_generate_advisory_groq_success(mocker):
    # Initialize service with only Groq API Key
    service = AdvisoryService(groq_api_key="test_groq_key")
    service.gemini_api_key = None
    
    # Mock httpx.AsyncClient.post
    mock_post = mocker.patch("httpx.AsyncClient.post", new_callable=mocker.AsyncMock)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {"content": json.dumps(MOCK_SUCCESSFUL_ADVISORY)}
            }
        ]
    }
    mock_post.return_value = mock_response

    weather_data = {"city_name": "Mumbai", "temperature": 27.0, "humidity": 90, "condition": "Heavy rain"}
    user_context = "Flight departure in 3 hours"

    result = await service.generate_advisory(
        weather_data=weather_data,
        user_context=user_context
    )

    assert result == MOCK_SUCCESSFUL_ADVISORY
    assert mock_post.call_count == 1

@pytest.mark.asyncio
async def test_retry_on_malformed_json(mocker):
    service = AdvisoryService(gemini_api_key="test_gemini_key")
    
    # Mock httpx.AsyncClient.post
    mock_post = mocker.patch("httpx.AsyncClient.post", new_callable=mocker.AsyncMock)
    
    # First response is malformed text, second response is valid JSON
    mock_response_malformed = MagicMock(spec=httpx.Response)
    mock_response_malformed.status_code = 200
    mock_response_malformed.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "this is not json!"}]}}]
    }
    
    mock_response_valid = MagicMock(spec=httpx.Response)
    mock_response_valid.status_code = 200
    mock_response_valid.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": json.dumps(MOCK_SUCCESSFUL_ADVISORY)}]}}]
    }
    
    mock_post.side_effect = [mock_response_malformed, mock_response_valid]

    weather_data = {"city_name": "Coimbatore", "temperature": 34.2}
    result = await service.generate_advisory(
        weather_data=weather_data,
        user_context="Running"
    )

    # Should succeed on the second attempt
    assert result == MOCK_SUCCESSFUL_ADVISORY
    assert mock_post.call_count == 2

@pytest.mark.asyncio
async def test_raise_error_after_retry_fails(mocker):
    service = AdvisoryService(gemini_api_key="test_gemini_key")
    mock_post = mocker.patch("httpx.AsyncClient.post", new_callable=mocker.AsyncMock)
    
    # Both responses are malformed
    mock_response_malformed = MagicMock(spec=httpx.Response)
    mock_response_malformed.status_code = 200
    mock_response_malformed.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "not json!"}]}}]
    }
    mock_post.return_value = mock_response_malformed

    weather_data = {"city_name": "Coimbatore"}
    with pytest.raises(ValueError) as exc_info:
        await service.generate_advisory(
            weather_data=weather_data,
            user_context="Jogging"
        )
        
    assert "Failed to generate structured advisory" in str(exc_info.value)
    assert mock_post.call_count == 2
