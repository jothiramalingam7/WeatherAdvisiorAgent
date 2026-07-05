import os
import json
import httpx
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from backend.db.connection import SessionLocal
from backend.db.models import Advisory, AdvisoryCategory

# -------------------------------------------------------------
# Base System Prompt Template
# -------------------------------------------------------------
SYSTEM_PROMPT = """You are AgriWeather Advisor, an agentic AI assistant that gives farmers accurate, location-specific, and actionable farming advice based on real-time and forecast weather data. You combine meteorological data with agronomic best practices to help farmers make decisions about irrigation, planting, harvesting, spraying, and crop protection.

You are not a general chatbot. You are a decision-support tool. Every recommendation must be traceable to a specific data point or well-established agronomic principle — never a guess.

CORE PRINCIPLES (Non-negotiable):
1. Ground every claim in data: Before giving advice, always analyze the provided weather data for the farmer's specific location. Never rely on memory or assumptions about "typical" weather.
2. Never fabricate data: If data is missing or a location is invalid, explicitly say so. Do not invent temperature, rainfall, or forecast numbers.
3. State confidence and uncertainty: Weather forecasts beyond 3-5 days are less reliable. Explicitly label short-term (0-3 days, high confidence) vs. extended (4-10 days, lower confidence) advice.
4. Be crop- and stage-specific: Advice must account for the crop type and growth stage mentioned by the farmer (e.g. "tomato at flowering stage" vs. "tomato at seedling stage"). If crop/stage details are missing, ask for them in your response.
5. Prioritize safety and loss-prevention: Frost, hail, heavy rain, drought stress, and extreme heat warnings must always be surfaced prominently and early.
6. No overconfidence: Never say "It will definitely not rain" — use probability language ("70% chance of rain", "low likelihood of frost tonight").
7. Respect regional/local nuance: Farming practices and units vary by region — adapt to the farmer's locale.

WORKFLOW (Follow in order):
Step 1 — Gather context: Confirm you have: Location, Crop(s) and growth stage, and the specific decision the farmer is trying to make. If any critical piece is missing, ask ONE concise clarifying question before proceeding.
Step 2 — Fetch/read real data: Analyze the provided weather data (current conditions, short-term/extended forecast, and any active alerts).
Step 3 — Interpret for agriculture: Translate raw weather into soil moisture/irrigation need, disease/pest risk, spray suitability, frost/heat stress, and harvest timing.
Step 4 — Give the recommendation: Structure your response matching the output schema.
Step 5 — Offer next steps: Offer to set reminders or monitor a threshold.

Always respond in valid JSON matching this schema exactly:
{
  "summary": string (a short, concise bottom-line summary combining recommendation and key risks),
  "risk_level": "low" | "moderate" | "high" | "severe",
  "recommendations": [string, string, ...],
  "category": "agriculture",
  "bottom_line": string (1-2 sentences, direct answer to their question),
  "supporting_weather_data": string (the specific numbers you used, with source/timestamp),
  "reasoning": string (why this data leads to this advice, tied to crop/stage),
  "risks_and_alerts": string (urgent warning: frost, storm, extreme heat, etc., or "None"),
  "confidence_level": "High" | "Medium" | "Low",
  "confidence_explanation": string (why this confidence level was chosen, linking to forecast reliability),
  "next_steps": string (reminders or thresholds to monitor)
}

If the user's query is completely unrelated to farming or weather safety, set risk_level to 'low', category to 'agriculture', and use the bottom_line and summary to politely decline and redirect them to agricultural weather safety advisory queries.
"""

# -------------------------------------------------------------
# Service Implementation
# -------------------------------------------------------------
class AdvisoryService:
    def __init__(self, gemini_api_key: Optional[str] = None, groq_api_key: Optional[str] = None):
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.groq_api_key = groq_api_key or os.getenv("GROQ_API_KEY")

    async def generate_advisory(
        self,
        weather_data: dict,
        user_context: str,
        weather_query_id: Optional[int] = None,
        db: Optional[Session] = None
    ) -> dict:
        """
        Generates a weather advisory based on weather data and user context using Gemini or Groq LLMs.
        Retries once if response is malformed. Saves log to database if db session is provided.
        """
        if not self.gemini_api_key and not self.groq_api_key:
            raise ValueError("No LLM API Key configured. Set GEMINI_API_KEY or GROQ_API_KEY.")

        # Prepare user input block (structured JSON input as requested)
        input_data = {
            "city": weather_data.get("city_name", "Unknown"),
            "temp_c": weather_data.get("temperature", 0.0),
            "humidity": weather_data.get("humidity", 0),
            "condition": weather_data.get("condition", "Unknown").lower(),
            "user_context": user_context
        }
        user_message = json.dumps(input_data)

        response_text = ""
        success = False
        parsed_advisory = {}

        # Loop for a single retry (try twice total)
        for attempt in range(2):
            try:
                if self.gemini_api_key:
                    response_text = await self._call_gemini(user_message)
                else:
                    response_text = await self._call_groq(user_message)

                # Clean response text in case LLM wraps it in markdown code blocks
                cleaned_text = self._clean_json_response(response_text)
                parsed_advisory = json.loads(cleaned_text)

                # Validate response fields
                self._validate_advisory_fields(parsed_advisory)
                success = True
                break
            except Exception as e:
                if attempt == 1:
                    # On second attempt failure, raise the exception
                    raise ValueError(f"Failed to generate structured advisory: {e}. Raw response: {response_text}")

        # Save advisory to database if session and weather_query_id are available
        if success and db and weather_query_id is not None:
            self._save_to_db(
                db=db,
                weather_query_id=weather_query_id,
                user_context=user_context,
                llm_prompt=user_message,
                llm_response=json.dumps(parsed_advisory),
                category=parsed_advisory.get("category", "general")
            )

        return parsed_advisory

    async def _call_gemini(self, user_message: str) -> str:
        # Use gemini-1.5-flash as a standard lightweight model
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.gemini_api_key}"
        payload = {
            "systemInstruction": {
                "parts": [{"text": SYSTEM_PROMPT}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_message}]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json"
            }
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=20.0)
            if response.status_code != 200:
                raise ValueError(f"Gemini API error: {response.status_code} - {response.text}")
            
            resp_json = response.json()
            try:
                return resp_json["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError):
                raise ValueError(f"Unexpected response structure from Gemini: {resp_json}")

    async def _call_groq(self, user_message: str) -> str:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.groq_api_key}",
            "Content-Type": "application/json"
        }
        # Use llama-3.3-70b-versatile or llama3-8b-8192 as backup
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=20.0)
            if response.status_code != 200:
                raise ValueError(f"Groq API error: {response.status_code} - {response.text}")
            
            resp_json = response.json()
            try:
                return resp_json["choices"][0]["message"]["content"]
            except (KeyError, IndexError):
                raise ValueError(f"Unexpected response structure from Groq: {resp_json}")

    def _clean_json_response(self, text: str) -> str:
        text_strip = text.strip()
        # Remove markdown code blocks if any (e.g. ```json ... ```)
        if text_strip.startswith("```"):
            lines = text_strip.split("\n")
            # Remove first line if it contains ```
            if lines[0].startswith("```"):
                lines = lines[1:]
            # Remove last line if it contains ```
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text_strip = "\n".join(lines).strip()
        return text_strip

    def _validate_advisory_fields(self, data: dict) -> None:
        required_keys = [
            "summary", "risk_level", "recommendations", "category",
            "bottom_line", "supporting_weather_data", "reasoning",
            "risks_and_alerts", "confidence_level", "confidence_explanation",
            "next_steps"
        ]
        for key in required_keys:
            if key not in data:
                raise KeyError(f"Missing required key in output schema: {key}")

        if data["risk_level"] not in ["low", "moderate", "high", "severe"]:
            raise ValueError(f"Invalid risk_level: {data['risk_level']}")

        if not isinstance(data["recommendations"], list):
            raise TypeError("recommendations must be a list of strings")

        if data["category"] not in ["health", "travel", "agriculture", "general"]:
            raise ValueError(f"Invalid category: {data['category']}")

    def _save_to_db(
        self,
        db: Session,
        weather_query_id: int,
        user_context: str,
        llm_prompt: str,
        llm_response: str,
        category: str
    ) -> None:
        try:
            # Match LLM category to database AdvisoryCategory enum
            try:
                advisory_cat = AdvisoryCategory(category)
            except ValueError:
                advisory_cat = AdvisoryCategory.general

            db_advisory = Advisory(
                weather_query_id=weather_query_id,
                user_context=user_context,
                llm_prompt=llm_prompt,
                llm_response=llm_response,
                advisory_category=advisory_cat
            )
            db.add(db_advisory)
            db.commit()
        except Exception as e:
            db.rollback()
            # Log error but don't fail the advisory retrieval
            print(f"Error saving advisory to DB: {e}")
