// -------------------------------------------------------------
// Configuration & Endpoint Base
// -------------------------------------------------------------
const API_BASE = "https://weatheradvisioragent-production.up.railway.app/api";

// -------------------------------------------------------------
// DOM Selection
// -------------------------------------------------------------
const advisoryForm = document.getElementById("advisory-form");
const cityInput = document.getElementById("city");
const cropInput = document.getElementById("crop-context");
const decisionInput = document.getElementById("farming-decision");
const submitBtn = document.getElementById("submit-btn");

// Dynamic Views
const placeholderState = document.getElementById("placeholder-state");
const loadingState = document.getElementById("loading-state");
const errorBanner = document.getElementById("error-banner");
const errorMessage = document.getElementById("error-message");
const resultsWrapper = document.getElementById("results-wrapper");

// Result Card Data Slots
const riskBadge = document.getElementById("risk-badge");
const confidenceBadge = document.getElementById("confidence-badge");
const bottomLineText = document.getElementById("bottom-line-text");
const alertsCard = document.getElementById("alerts-card");
const alertsText = document.getElementById("alerts-text");
const reasoningText = document.getElementById("reasoning-text");
const recsList = document.getElementById("recs-list");
const nextStepsText = document.getElementById("next-steps-text");
const supportingDataText = document.getElementById("supporting-data-text");

const weatherCity = document.getElementById("weather-city");
const weatherCoords = document.getElementById("weather-coords");
const weatherTemp = document.getElementById("weather-temp");
const weatherCondition = document.getElementById("weather-condition");
const weatherFeels = document.getElementById("weather-feels");
const weatherHumidity = document.getElementById("weather-humidity");
const weatherWind = document.getElementById("weather-wind");

// History Toggle
const historySection = document.getElementById("history-section");
const historyToggle = document.getElementById("history-toggle");
const historyList = document.getElementById("history-list");

// -------------------------------------------------------------
// Initialization & Global Event Registers
// -------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
    // Attempt loading initial history logs
    fetchHistory();

    // Setup history expand toggle
    historyToggle.addEventListener("click", () => {
        historySection.classList.toggle("expanded");
        if (historySection.classList.contains("expanded")) {
            fetchHistory();
        }
    });

    // Setup form submissions
    advisoryForm.addEventListener("submit", handleFormSubmit);
});

// -------------------------------------------------------------
// Request Handler: Form Submission
// -------------------------------------------------------------
async function handleFormSubmit(e) {
    e.preventDefault();
    
    const city = cityInput.value.trim();
    const crop = cropInput.value.trim();
    const decision = decisionInput.value.trim();

    if (!city || !crop || !decision) return;

    const context = `Crop & Stage: ${crop}. Decision: ${decision}`;

    // Reset views and show spinner
    showLoader(true);
    showError(false);

    try {
        const response = await fetch(`${API_BASE}/advisory`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                city: city,
                user_context: context,
                user_id: 1 // Default MVP user id
            })
        });

        if (!response.ok) {
            const errBody = await response.json();
            throw new Error(errBody.detail || `Server returned status ${response.status}`);
        }

        const data = await response.json();
        renderAdvisory(data);
        
        // Refresh history log to include current search
        fetchHistory();

    } catch (err) {
        let msg = err.message;
        if (msg.toLowerCase().includes("weather") || msg.toLowerCase().includes("api") || msg.toLowerCase().includes("fetch") || msg.toLowerCase().includes("server")) {
            msg = `I couldn't retrieve current weather data for "${city}" — here's what I'd need to check before advising you: a valid OpenWeatherMap API key and connection.`;
        }
        showError(true, msg);
    } finally {
        showLoader(false);
    }
}

// -------------------------------------------------------------
// History Fetcher & Renderer
// -------------------------------------------------------------
async function fetchHistory() {
    try {
        const response = await fetch(`${API_BASE}/history?user_id=1`);
        if (!response.ok) return;

        const data = await response.json();
        renderHistoryList(data);
    } catch (err) {
        console.error("Failed to load query history:", err);
    }
}

function renderHistoryList(historyItems) {
    if (!historyItems || historyItems.length === 0) {
        historyList.innerHTML = `<p style="color: var(--text-muted); font-size: 0.85rem; text-align: center; padding: 1.5rem 0;">No query history yet.</p>`;
        return;
    }

    historyList.innerHTML = historyItems.map(item => {
        // Extract basic data (handles multiple advisories fallback)
        const advisory = item.advisories[0] || {};
        const weather = item.raw_weather_json || {};
        const llm = advisory.llm_response || {};
        
        const dateStr = new Date(item.queried_at).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit"
        });

        // Store serialized data to reconstitute it upon click selection
        const stringifiedItem = encodeURIComponent(JSON.stringify(item));

        return `
            <div class="history-item" onclick="loadHistoryItem('${stringifiedItem}')">
                <div class="history-item-top">
                    <span class="history-city">${item.location.city_name}</span>
                    <span class="history-date">${dateStr}</span>
                </div>
                <div class="history-context">Context: "${item.user_context}"</div>
                <div class="history-summary-line">${llm.summary || "Advisory details logged"}</div>
            </div>
        `;
    }).join("");
}

// Reconstitutes a historical item into the primary view
window.loadHistoryItem = function(encodedItem) {
    try {
        const item = JSON.parse(decodeURIComponent(encodedItem));
        const advisory = item.advisories[0];
        
        if (!advisory) return;

        const llm = advisory.llm_response;

        // Reconstitute expected schema formatting
        const mockAdvisoryResponse = {
            query_id: item.id,
            location: item.location,
            weather: item.raw_weather_json,
            advisory: {
                summary: llm.summary,
                risk_level: llm.risk_level || "low",
                recommendations: llm.recommendations || [],
                category: llm.category || advisory.advisory_category,
                bottom_line: llm.bottom_line,
                supporting_weather_data: llm.supporting_weather_data,
                reasoning: llm.reasoning,
                risks_and_alerts: llm.risks_and_alerts,
                confidence_level: llm.confidence_level,
                confidence_explanation: llm.confidence_explanation,
                next_steps: llm.next_steps
            }
        };

        // Populate fields and set context inputs for utility
        cityInput.value = item.location.city_name;
        
        const contextStr = item.user_context || "";
        const cropMatch = contextStr.match(/Crop & Stage:\s*(.*?)\.\s*Decision:\s*(.*)/i);
        if (cropMatch) {
            cropInput.value = cropMatch[1];
            decisionInput.value = cropMatch[2];
        } else {
            cropInput.value = "";
            decisionInput.value = contextStr;
        }

        showError(false);
        renderAdvisory(mockAdvisoryResponse);

        // Smooth scroll to top on mobile layouts to view details
        if (window.innerWidth <= 900) {
            window.scrollTo({ top: 0, behavior: "smooth" });
        }
    } catch (e) {
        console.error("Error loading historical query details:", e);
    }
};

// -------------------------------------------------------------
// View Render Helpers
// -------------------------------------------------------------
function renderAdvisory(data) {
    // Extract weather attributes supporting both legacy (raw) and new (normalized) schemas
    const w = data.weather || {};
    const main = w.main || {};
    const wind = w.wind || {};
    const weatherList = w.weather || [{}];

    const tempVal = w.temperature !== undefined ? w.temperature : main.temp;
    const feelsVal = w.feels_like !== undefined ? w.feels_like : main.feels_like;
    const humidityVal = w.humidity !== undefined ? w.humidity : main.humidity;
    const windVal = w.wind_speed !== undefined ? w.wind_speed : wind.speed;
    const condVal = w.condition !== undefined ? w.condition : (weatherList[0].description || weatherList[0].main || "Unknown");

    // Fill Weather metrics
    weatherCity.innerText = data.location.city_name;
    weatherCoords.innerText = `${data.location.lat.toFixed(4)}° N, ${data.location.lon.toFixed(4)}° E`;
    weatherTemp.innerText = tempVal !== undefined ? `${Math.round(tempVal)}°C` : "N/A";
    weatherCondition.innerText = condVal.charAt(0).toUpperCase() + condVal.slice(1);
    weatherFeels.innerText = feelsVal !== undefined ? `${feelsVal.toFixed(1)}°C` : "N/A";
    weatherHumidity.innerText = humidityVal !== undefined ? `${humidityVal}%` : "N/A";
    weatherWind.innerText = windVal !== undefined ? `${windVal.toFixed(1)} m/s` : "N/A";

    // Fill Advisory texts
    bottomLineText.innerText = data.advisory.bottom_line || data.advisory.summary || "No specific bottom-line recommendation.";
    
    // Risks & Alerts Banner
    const alertText = data.advisory.risks_and_alerts || "None";
    if (alertText.toLowerCase() !== "none") {
        alertsCard.classList.add("active");
        alertsText.innerText = alertText;
    } else {
        alertsCard.classList.remove("active");
    }

    // Reasoning
    reasoningText.innerText = data.advisory.reasoning || "No rationale provided.";

    // Next Steps
    nextStepsText.innerText = data.advisory.next_steps || "No next steps provided.";

    // Supporting Weather Data
    supportingDataText.innerText = data.advisory.supporting_weather_data || `Source: OpenWeatherMap (UV Index: ${data.weather.uv_index.toFixed(1)})`;

    // Format risk level badge class styling
    const risk = data.advisory.risk_level.toLowerCase();
    riskBadge.innerText = risk;
    riskBadge.className = `risk-badge ${risk}`;

    // Format confidence badge styling
    const conf = (data.advisory.confidence_level || "High").toLowerCase();
    confidenceBadge.innerText = `${data.advisory.confidence_level || "High"} Confidence`;
    confidenceBadge.className = `confidence-badge ${conf}`;

    // Format recommendation lists
    recsList.innerHTML = data.advisory.recommendations.map(rec => `<li>${rec}</li>`).join("");

    // Toggle View State Displays
    placeholderState.style.display = "none";
    resultsWrapper.style.display = "block";
}

function showLoader(isVisible) {
    if (isVisible) {
        placeholderState.style.display = "none";
        resultsWrapper.style.display = "none";
        loadingState.style.display = "flex";
        submitBtn.disabled = true;
    } else {
        loadingState.style.display = "none";
        submitBtn.disabled = false;
    }
}

function showError(isVisible, message = "") {
    if (isVisible) {
        resultsWrapper.style.display = "none";
        placeholderState.style.display = "none";
        errorBanner.style.display = "flex";
        errorMessage.innerText = message;
    } else {
        errorBanner.style.display = "none";
    }
}
