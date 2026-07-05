import os
import sys
from datetime import datetime

# Add the workspace root to python path to resolve 'backend' imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.db.connection import SessionLocal, engine, Base
from backend.db.models import User, Location, WeatherQuery, Advisory, AdvisoryCategory

def seed_database():
    print("Seeding database...")
    db = SessionLocal()
    try:
        # Check if users already exist
        if db.query(User).count() > 0:
            print("Database already contains data. Skipping seeding.")
            return

        # 1. Create Users
        alice = User(name="Alice Smith", email="alice@example.com")
        bob = User(name="Bob Jones", email="bob@example.com")
        db.add_all([alice, bob])
        db.flush()  # Populates IDs

        # 2. Create Locations
        coimbatore = Location(city_name="Coimbatore", lat=11.0168, lon=76.9558, country="IN")
        chennai = Location(city_name="Chennai", lat=13.0827, lon=80.2707, country="IN")
        bangalore = Location(city_name="Bangalore", lat=12.9716, lon=77.5946, country="IN")
        db.add_all([coimbatore, chennai, bangalore])
        db.flush()

        # 3. Create Weather Queries
        query_coimbatore = WeatherQuery(
            user_id=alice.id,
            location_id=coimbatore.id,
            raw_weather_json={
                "main": {"temp": 34.2, "humidity": 78, "feels_like": 41.5},
                "weather": [{"main": "Clear", "description": "clear sky"}],
                "wind": {"speed": 4.1}
            }
        )
        query_chennai = WeatherQuery(
            user_id=bob.id,
            location_id=chennai.id,
            raw_weather_json={
                "main": {"temp": 28.5, "humidity": 95, "feels_like": 32.0},
                "weather": [{"main": "Rain", "description": "heavy intensity rain"}],
                "wind": {"speed": 12.5}
            }
        )
        db.add_all([query_coimbatore, query_chennai])
        db.flush()

        # 4. Create Advisories
        advisory_coimbatore = Advisory(
            weather_query_id=query_coimbatore.id,
            user_context="Activity: Running, Health Conditions: Asthma, Travel Plans: None",
            llm_prompt="Mock system prompt with weather (temp: 34.2C, humidity: 78%) and context (running, asthma)",
            llm_response="Caution: Coimbatore is currently very hot (34.2°C) with high humidity (78%), giving a feels-like temperature of 41.5°C. Since you have asthma and plan on running, please avoid outdoor exercise during mid-day. Opt for an air-conditioned indoor track or treadmill, and carry your rescue inhaler at all times.",
            advisory_category=AdvisoryCategory.health
        )
        advisory_chennai = Advisory(
            weather_query_id=query_chennai.id,
            user_context="Activity: Flight passenger, Health Conditions: None, Travel Plans: Flight departing at 6 PM",
            llm_prompt="Mock system prompt with weather (heavy rain, wind: 12.5m/s) and travel plans (flight departure)",
            llm_response="Travel Advisory: Heavy rain and strong winds (12.5 m/s) are reported in Chennai. This is highly likely to cause flight delays or traffic congestion on the way to Chennai International Airport. Please check your flight status before departing and head to the airport at least 1 hour earlier than planned.",
            advisory_category=AdvisoryCategory.travel
        )
        db.add_all([advisory_coimbatore, advisory_chennai])
        
        db.commit()
        print("Database seeded successfully with sample data!")
        
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
