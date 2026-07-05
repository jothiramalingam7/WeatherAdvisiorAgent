import enum
from datetime import datetime
from sqlalchemy import ForeignKey, String, Text, Float, JSON, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.db.connection import Base

class AdvisoryCategory(str, enum.Enum):
    health = "health"
    travel = "travel"
    agriculture = "agriculture"
    general = "general"

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    
    # Relationships
    weather_queries: Mapped[list["WeatherQuery"]] = relationship(back_populates="user", cascade="all, delete-orphan")

class Location(Base):
    __tablename__ = "locations"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    city_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    country: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Relationships
    weather_queries: Mapped[list["WeatherQuery"]] = relationship(back_populates="location", cascade="all, delete-orphan")

class WeatherQuery(Base):
    __tablename__ = "weather_queries"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), nullable=False)
    raw_weather_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    queried_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    
    # Relationships
    user: Mapped[User | None] = relationship(back_populates="weather_queries")
    location: Mapped[Location] = relationship(back_populates="weather_queries")
    advisories: Mapped[list["Advisory"]] = relationship(back_populates="weather_query", cascade="all, delete-orphan")

class Advisory(Base):
    __tablename__ = "advisories"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    weather_query_id: Mapped[int] = mapped_column(ForeignKey("weather_queries.id", ondelete="CASCADE"), nullable=False)
    user_context: Mapped[str] = mapped_column(Text, nullable=False)
    llm_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    llm_response: Mapped[str] = mapped_column(Text, nullable=False)
    advisory_category: Mapped[AdvisoryCategory] = mapped_column(Enum(AdvisoryCategory), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    
    # Relationships
    weather_query: Mapped[WeatherQuery] = relationship(back_populates="advisories")
