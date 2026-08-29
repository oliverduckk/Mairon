import requests


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


WEATHER_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    71: "slight snow",
    73: "moderate snow",
    75: "heavy snow",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


def weather_code_description(code):
    return WEATHER_CODES.get(code, "unknown conditions")


def get_weather(location):
    # --------------------------------------------------
    # Convert location name into coordinates
    # --------------------------------------------------

    geocoding_response = requests.get(
        GEOCODING_URL,
        params={
            "name": location,
            "count": 1,
            "language": "en",
            "format": "json"
        },
        timeout=10
    )

    geocoding_response.raise_for_status()

    geocoding_data = geocoding_response.json()
    results = geocoding_data.get("results", [])

    if not results:
        return {
            "success": False,
            "message": f"Could not find a location matching '{location}'."
        }

    place = results[0]

    latitude = place["latitude"]
    longitude = place["longitude"]

    # --------------------------------------------------
    # Retrieve weather data
    # --------------------------------------------------

    forecast_response = requests.get(
        FORECAST_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": (
                "temperature_2m,"
                "apparent_temperature,"
                "precipitation,"
                "weather_code,"
                "wind_speed_10m"
            ),
            "daily": (
                "weather_code,"
                "temperature_2m_max,"
                "temperature_2m_min,"
                "precipitation_probability_max"
            ),
            "timezone": "auto",
            "forecast_days": 3
        },
        timeout=10
    )

    forecast_response.raise_for_status()

    weather = forecast_response.json()

    current = weather["current"]
    daily = weather["daily"]

    forecast_days = []

    for index, date in enumerate(daily["time"]):
        forecast_days.append(
            {
                "date": date,
                "conditions": weather_code_description(
                    daily["weather_code"][index]
                ),
                "max_temperature_c": daily["temperature_2m_max"][index],
                "min_temperature_c": daily["temperature_2m_min"][index],
                "precipitation_probability_percent":
                    daily["precipitation_probability_max"][index]
            }
        )

    return {
        "success": True,
        "location": {
            "name": place["name"],
            "country": place.get("country"),
            "region": place.get("admin1"),
            "latitude": latitude,
            "longitude": longitude,
        },
        "current": {
            "temperature_c": current["temperature_2m"],
            "feels_like_c": current["apparent_temperature"],
            "conditions": weather_code_description(
                current["weather_code"]
            ),
            "precipitation_mm": current["precipitation"],
            "wind_speed_kmh": current["wind_speed_10m"],
        },
        "forecast": forecast_days
    }