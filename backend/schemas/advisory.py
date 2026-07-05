from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from backend.services.weather import WeatherData

# -------------------------------------------------------------
# Request Schemas
# -------------------------------------------------------------
class AdvisoryRequest(BaseModel):
    city: str = Field(..., example="Coimbatore", description="Name of the city for the weather query")
    user_context: str = Field(..., example="Activity: Running, Health Conditions: Asthma", description="User's personal context")
    user_id: Optional[int] = Field(None, example=1, description="Optional ID of the querying user")

# -------------------------------------------------------------
# Response Schemas
# -------------------------------------------------------------
class AdvisoryContent(BaseModel):
    summary: str
    risk_level: str
    recommendations: List[str]
    category: str
    bottom_line: Optional[str] = None
    supporting_weather_data: Optional[str] = None
    reasoning: Optional[str] = None
    risks_and_alerts: Optional[str] = None
    confidence_level: Optional[str] = None
    confidence_explanation: Optional[str] = None
    next_steps: Optional[str] = None

class AdvisoryResponse(BaseModel):
    query_id: int
    location: Dict[str, Any]
    weather: WeatherData
    advisory: AdvisoryContent

class AdvisoryHistoryItem(BaseModel):
    id: int
    user_context: str
    llm_response: Dict[str, Any]
    advisory_category: str
    created_at: datetime

    class Config:
        from_attributes = True

class WeatherQueryHistoryResponse(BaseModel):
    id: int
    user_id: Optional[int]
    location: Dict[str, Any]
    raw_weather_json: Dict[str, Any]
    queried_at: datetime
    advisories: List[AdvisoryHistoryItem]

    class Config:
        from_attributes = True
