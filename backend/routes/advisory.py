# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, HTTPException, Query
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import datetime
import json

from backend.db.connection import get_db
from backend.db.models import Location, WeatherQuery, Advisory, User
from backend.services.weather import WeatherService, WeatherData
from backend.services.advisory import AdvisoryService
from backend.schemas.advisory import (
    AdvisoryRequest,
    AdvisoryResponse,
    AdvisoryContent,
    WeatherQueryHistoryResponse,
    AdvisoryHistoryItem
)

router = APIRouter(prefix="/api", tags=["Advisory & Weather"])

# Initialize Services
weather_service = WeatherService()
advisory_service = AdvisoryService()

# -------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------

@router.get("/health", response_model=dict)
def health_check():
    """Health check endpoint for deployment monitoring."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat()
    }

@router.get("/weather/{city}", response_model=WeatherData)
async def get_raw_weather(city: str):
    """Retrieve raw normalized current weather and forecast for a city."""
    try:
        data = await weather_service.fetch_weather_by_city(city)
        return data
    except Exception as e:
        raise e  # Let exception handlers deal with it

@router.post("/advisory", response_model=AdvisoryResponse)
async def generate_weather_advisory(
    request: AdvisoryRequest,
    db: Session = Depends(get_db)
):
    """
    Fetch current weather, generate LLM advisory, save history, and return results.
    """
    # 1. Fetch current weather and forecast
    try:
        weather_data = await weather_service.fetch_weather_by_city(request.city)
    except Exception as e:
        raise e

    # 2. Resolve / Create Location in Database
    city_normalized = weather_data.city_name.strip()
    location = db.query(Location).filter(
        Location.city_name.ilike(city_normalized)
    ).first()

    if not location:
        location = Location(
            city_name=city_normalized,
            lat=weather_data.lat,
            lon=weather_data.lon,
            country=weather_data.country
        )
        db.add(location)
        db.flush()  # Obtain ID

    # 3. Create Weather Query Log
    # Save raw weather json as dict to map to database JSON column
    weather_query = WeatherQuery(
        user_id=request.user_id,
        location_id=location.id,
        raw_weather_json=weather_data.model_dump()
    )
    db.add(weather_query)
    db.flush()  # Obtain ID

    # 4. Generate LLM Advisory (Saves to advisories table internally if db session passed)
    try:
        llm_advisory = await advisory_service.generate_advisory(
            weather_data=weather_data.model_dump(),
            user_context=request.user_context,
            weather_query_id=weather_query.id,
            db=db
        )
    except Exception as e:
        # If LLM generation fails, roll back query logging
        db.rollback()
        raise HTTPException(status_code=502, detail=f"LLM advisory generation failed: {e}")

    # Build response structure
    return AdvisoryResponse(
        query_id=weather_query.id,
        location={
            "city_name": location.city_name,
            "country": location.country,
            "lat": location.lat,
            "lon": location.lon
        },
        weather=weather_data,
        advisory=AdvisoryContent(
            summary=llm_advisory["summary"],
            risk_level=llm_advisory["risk_level"],
            recommendations=llm_advisory["recommendations"],
            category=llm_advisory["category"],
            bottom_line=llm_advisory.get("bottom_line"),
            supporting_weather_data=llm_advisory.get("supporting_weather_data"),
            reasoning=llm_advisory.get("reasoning"),
            risks_and_alerts=llm_advisory.get("risks_and_alerts"),
            confidence_level=llm_advisory.get("confidence_level"),
            confidence_explanation=llm_advisory.get("confidence_explanation"),
            next_steps=llm_advisory.get("next_steps")
        )
    )

@router.get("/history", response_model=List[WeatherQueryHistoryResponse])
def get_advisory_history(
    user_id: Optional[int] = Query(None, description="Filter history by user ID"),
    db: Session = Depends(get_db)
):
    """
    Retrieve historical query and advisory logs, optionally filtered by user_id.
    """
    query_builder = db.query(WeatherQuery).options(
        joinedload(WeatherQuery.location),
        joinedload(WeatherQuery.advisories)
    )

    if user_id is not None:
        query_builder = query_builder.filter(WeatherQuery.user_id == user_id)

    queries = query_builder.order_by(WeatherQuery.queried_at.desc()).all()

    # Format the DB objects into history schemas
    history_list = []
    for q in queries:
        advisories_dto = []
        for adv in q.advisories:
            try:
                # Load response text back into a dict for the history response DTO
                llm_response_json = json.loads(adv.llm_response)
            except Exception:
                llm_response_json = {"summary": adv.llm_response}

            advisories_dto.append(
                AdvisoryHistoryItem(
                    id=adv.id,
                    user_context=adv.user_context,
                    llm_response=llm_response_json,
                    advisory_category=adv.advisory_category.value,
                    created_at=adv.created_at
                )
            )

        history_list.append(
            WeatherQueryHistoryResponse(
                id=q.id,
                user_id=q.user_id,
                location={
                    "city_name": q.location.city_name,
                    "country": q.location.country,
                    "lat": q.location.lat,
                    "lon": q.location.lon
                },
                raw_weather_json=q.raw_weather_json,
                queried_at=q.queried_at,
                advisories=advisories_dto
            )
        )

    return history_list
