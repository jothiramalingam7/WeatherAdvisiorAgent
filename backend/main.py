import time
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

from backend.routes.advisory import router as advisory_router
from backend.services.weather import CityNotFoundError, RateLimitError, WeatherAPIError

# Initialize FastAPI App
app = FastAPI(
    title="Weather Advisory Agent API",
    description="Backend REST API for fetching weather metrics and producing AI-generated safety advisories.",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI enabled at /docs
    redoc_url="/redoc"
)

# Enable CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, replace with specific frontend origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Router
app.include_router(advisory_router)

# -------------------------------------------------------------
# Centralized Error Handlers
# -------------------------------------------------------------
@app.exception_handler(CityNotFoundError)
async def city_not_found_exception_handler(request: Request, exc: CityNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc)}
    )

@app.exception_handler(RateLimitError)
async def rate_limit_exception_handler(request: Request, exc: RateLimitError):
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": str(exc)}
    )

@app.exception_handler(WeatherAPIError)
async def weather_api_exception_handler(request: Request, exc: WeatherAPIError):
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": f"Weather API error: {str(exc)}"}
    )

@app.exception_handler(ValueError)
async def value_error_exception_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)}
    )

# -------------------------------------------------------------
# Request Logging Middleware (Optional/Helpful)
# -------------------------------------------------------------
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

if __name__ == "__main__":
    import uvicorn
    # Default local dev port 8000
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
