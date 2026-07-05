import os
import sys

# Add workspace directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.db.connection import SessionLocal
from backend.db.models import User, Location, WeatherQuery, Advisory

def verify_db():
    print("Verifying database contents...")
    db = SessionLocal()
    try:
        users = db.query(User).all()
        locations = db.query(Location).all()
        queries = db.query(WeatherQuery).all()
        advisories = db.query(Advisory).all()
        
        print("\n--- Users ---")
        for u in users:
            print(f"ID: {u.id} | Name: {u.name} | Email: {u.email} | Created At: {u.created_at}")
            
        print("\n--- Locations ---")
        for loc in locations:
            print(f"ID: {loc.id} | City: {loc.city_name} | Lat/Lon: {loc.lat}, {loc.lon} | Country: {loc.country}")
            
        print("\n--- Weather Queries ---")
        for q in queries:
            print(f"ID: {q.id} | User ID: {q.user_id} | Location ID: {q.location_id} | Weather Description: {q.raw_weather_json.get('weather', [{}])[0].get('description')}")
            
        print("\n--- Advisories ---")
        for adv in advisories:
            print(f"ID: {adv.id} | Query ID: {adv.weather_query_id} | Category: {adv.advisory_category.value}")
            print(f"Context: {adv.user_context}")
            print(f"Response: {adv.llm_response}")
            print("-" * 50)
            
    finally:
        db.close()

if __name__ == "__main__":
    verify_db()
