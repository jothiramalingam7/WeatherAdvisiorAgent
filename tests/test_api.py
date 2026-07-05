import pytest
import json
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from typing import Generator

from backend.main import app
from backend.db.connection import Base, get_db
from backend.db.models import User, Location, WeatherQuery, Advisory, AdvisoryCategory
from backend.services.weather import WeatherService, WeatherData, ForecastItem
from backend.services.advisory import AdvisoryService

from sqlalchemy.pool import StaticPool

# -------------------------------------------------------------
# Setup Test Database (In-Memory SQLite with StaticPool)
# -------------------------------------------------------------
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session() -> Generator:
    # Create all tables in memory
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        # Drop all tables after the test
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(db_session) -> TestClient:
    # Override get_db dependency to use the in-memory test database session
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
            
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    # Clear overrides
    app.dependency_overrides.clear()

# -------------------------------------------------------------
# Mock Constants
# -------------------------------------------------------------
MOCK_WEATHER_DTO = WeatherData(
    city_name="Coimbatore",
    lat=11.0168,
    lon=76.9558,
    country="IN",
    temperature=34.2,
    feels_like=41.5,
    humidity=78,
    wind_speed=4.1,
    condition="Scattered clouds",
    uv_index=8.5,
    chance_of_rain=0.8,
    alerts=[],
    forecast=[
        ForecastItem(
            dt_txt="2026-07-04 12:00:00",
            temp=32.5,
            feels_like=38.2,
            condition="Rain",
            chance_of_rain=0.8
        )
    ]
)

MOCK_ADVISORY_DICT = {
    "summary": "Caution: Coimbatore is very hot and humid.",
    "risk_level": "moderate",
    "recommendations": ["Drink water", "Stay indoors"],
    "category": "agriculture",
    "bottom_line": "Caution: Coimbatore is very hot and humid.",
    "supporting_weather_data": "Temp: 34.2C, Humidity: 78%",
    "reasoning": "High temperatures combined with high humidity increase heat risk.",
    "risks_and_alerts": "High temperature alert",
    "confidence_level": "High",
    "confidence_explanation": "Short term forecast is highly accurate.",
    "next_steps": "Monitor weather updates."
}

# -------------------------------------------------------------
# Test Cases
# -------------------------------------------------------------

def test_health_check_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "timestamp" in response.json()

def test_get_raw_weather_success(client, mocker):
    # Mock WeatherService.fetch_weather_by_city
    mock_fetch = mocker.patch.object(
        WeatherService, "fetch_weather_by_city", new_callable=mocker.AsyncMock
    )
    mock_fetch.return_value = MOCK_WEATHER_DTO

    response = client.get("/api/weather/Coimbatore")
    
    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json["city_name"] == "Coimbatore"
    assert resp_json["temperature"] == 34.2
    assert resp_json["humidity"] == 78
    assert len(resp_json["forecast"]) == 1

def test_generate_advisory_flow_success(client, mocker):
    # Mock WeatherService.fetch_weather_by_city
    mock_weather = mocker.patch.object(
        WeatherService, "fetch_weather_by_city", new_callable=mocker.AsyncMock
    )
    mock_weather.return_value = MOCK_WEATHER_DTO

    # Mock AdvisoryService.generate_advisory with database insertion side-effect
    mock_advisory = mocker.patch.object(
        AdvisoryService, "generate_advisory", new_callable=mocker.AsyncMock
    )
    async def mock_generate(weather_data, user_context, weather_query_id=None, db=None):
        if db and weather_query_id:
            db_advisory = Advisory(
                weather_query_id=weather_query_id,
                user_context=user_context,
                llm_prompt="mock prompt",
                llm_response=json.dumps(MOCK_ADVISORY_DICT),
                advisory_category=AdvisoryCategory.agriculture
            )
            db.add(db_advisory)
            db.commit()
        return MOCK_ADVISORY_DICT
    mock_advisory.side_effect = mock_generate

    payload = {
        "city": "Coimbatore",
        "user_context": "Running outdoors with asthma",
        "user_id": 1
    }

    # Call POST API
    response = client.post("/api/advisory", json=payload)
    assert response.status_code == 200
    resp_json = response.json()
    
    assert "query_id" in resp_json
    assert resp_json["location"]["city_name"] == "Coimbatore"
    assert resp_json["weather"]["temperature"] == 34.2
    assert resp_json["advisory"]["summary"] == MOCK_ADVISORY_DICT["summary"]
    assert resp_json["advisory"]["risk_level"] == MOCK_ADVISORY_DICT["risk_level"]
    assert resp_json["advisory"]["recommendations"] == MOCK_ADVISORY_DICT["recommendations"]
    assert resp_json["advisory"]["category"] == MOCK_ADVISORY_DICT["category"]
    assert resp_json["advisory"]["bottom_line"] == MOCK_ADVISORY_DICT["bottom_line"]
    assert resp_json["advisory"]["supporting_weather_data"] == MOCK_ADVISORY_DICT["supporting_weather_data"]
    assert resp_json["advisory"]["reasoning"] == MOCK_ADVISORY_DICT["reasoning"]
    assert resp_json["advisory"]["risks_and_alerts"] == MOCK_ADVISORY_DICT["risks_and_alerts"]
    assert resp_json["advisory"]["confidence_level"] == MOCK_ADVISORY_DICT["confidence_level"]
    assert resp_json["advisory"]["confidence_explanation"] == MOCK_ADVISORY_DICT["confidence_explanation"]
    assert resp_json["advisory"]["next_steps"] == MOCK_ADVISORY_DICT["next_steps"]

    # Verify history is populated
    history_response = client.get("/api/history?user_id=1")
    assert history_response.status_code == 200
    history_json = history_response.json()
    assert len(history_json) == 1
    assert history_json[0]["location"]["city_name"] == "Coimbatore"
    assert len(history_json[0]["advisories"]) == 1
    assert history_json[0]["advisories"][0]["user_context"] == payload["user_context"]
