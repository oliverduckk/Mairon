import os
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv


load_dotenv()


ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

LOCATION_ALIASES = {
    "home": os.getenv("MAIRON_HOME_ADDRESS"),
    "uni": os.getenv("MAIRON_UNI_ADDRESS"),
    "train_station": os.getenv("MAIRON_TRAIN_STATION"),
}

STATION_PARKING_MINUTES = int(
    os.getenv("MAIRON_STATION_PARKING_MINUTES", "5")
)


def resolve_location(location):
    """
    Convert a private Mairon alias such as 'home' or 'uni'
    into the real address stored locally in .env.
    """

    location_lower = location.lower().strip()

    if location_lower in LOCATION_ALIASES:
        resolved = LOCATION_ALIASES[location_lower]

        if not resolved:
            raise ValueError(
                f"Location alias '{location_lower}' is not configured."
            )

        return resolved

    return location


def parse_duration_seconds(duration):
    """
    Google returns durations such as '2534s'.
    Convert that into seconds.
    """

    return float(duration.rstrip("s"))


def format_departure_time(dt):
    """
    Convert a timezone-aware datetime into RFC 3339 UTC format
    for the Google Routes API.
    """

    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def request_route(
    origin,
    destination,
    travel_mode,
    departure_time=None
):
    """
    Make one Google Routes API request.

    travel_mode must be DRIVE or TRANSIT.
    """

    request_body = {
        "origin": {
            "address": origin
        },
        "destination": {
            "address": destination
        },
        "travelMode": travel_mode,
        "languageCode": "en-AU",
        "units": "METRIC"
    }

    # Driving routes should use live traffic.
    if travel_mode == "DRIVE":
        request_body["routingPreference"] = "TRAFFIC_AWARE_OPTIMAL"

    # This is especially important for the second leg of
    # park-and-ride, because Oliver has to reach the station first.
    if departure_time is not None:
        request_body["departureTime"] = format_departure_time(
            departure_time
        )

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": (
            "routes.duration,"
            "routes.staticDuration,"
            "routes.distanceMeters"
        )
    }

    response = requests.post(
        ROUTES_URL,
        json=request_body,
        headers=headers,
        timeout=15
    )

    response.raise_for_status()

    data = response.json()
    routes = data.get("routes", [])

    if not routes:
        return None

    route = routes[0]

    result = {
        "duration_seconds": parse_duration_seconds(
            route["duration"]
        ),
        "distance_metres": route["distanceMeters"]
    }

    if "staticDuration" in route:
        result["static_duration_seconds"] = (
            parse_duration_seconds(
                route["staticDuration"]
            )
        )

    return result


def get_route(origin, destination, mode="drive"):
    """
    Get travel information.

    Supported modes:

    drive
        Normal driving route with live traffic.

    transit
        Public transport beginning directly from the origin.

    park_and_ride
        Drive from the origin to Oliver's configured train station,
        allow time to park/walk to the platform, then calculate
        public transport from the station to the destination.
    """

    if not GOOGLE_MAPS_API_KEY:
        return {
            "success": False,
            "message": "Google Maps API key is not configured."
        }

    mode = mode.lower().strip()

    if mode not in (
        "drive",
        "transit",
        "park_and_ride"
    ):
        return {
            "success": False,
            "message": f"Unsupported travel mode '{mode}'."
        }

    try:
        resolved_origin = resolve_location(origin)
        resolved_destination = resolve_location(destination)

        # --------------------------------------------------
        # Driving
        # --------------------------------------------------

        if mode == "drive":
            route = request_route(
                resolved_origin,
                resolved_destination,
                "DRIVE"
            )

            if route is None:
                return {
                    "success": False,
                    "message": "No driving route was found."
                }

            duration_minutes = round(
                route["duration_seconds"] / 60
            )

            result = {
                "success": True,
                "mode": "drive",
                "origin": origin,
                "destination": destination,
                "distance_km": round(
                    route["distance_metres"] / 1000,
                    1
                ),
                "duration_minutes": duration_minutes
            }

            if "static_duration_seconds" in route:
                static_minutes = round(
                    route["static_duration_seconds"] / 60
                )

                result[
                    "duration_without_current_traffic_minutes"
                ] = static_minutes

                result["traffic_delay_minutes"] = (
                    duration_minutes - static_minutes
                )

            return result

        # --------------------------------------------------
        # Pure public transport
        # --------------------------------------------------

        if mode == "transit":
            route = request_route(
                resolved_origin,
                resolved_destination,
                "TRANSIT"
            )

            if route is None:
                return {
                    "success": False,
                    "message": "No public transport route was found."
                }

            return {
                "success": True,
                "mode": "transit",
                "origin": origin,
                "destination": destination,
                "distance_km": round(
                    route["distance_metres"] / 1000,
                    1
                ),
                "duration_minutes": round(
                    route["duration_seconds"] / 60
                )
            }

        # --------------------------------------------------
        # Park and ride
        # --------------------------------------------------

        train_station = resolve_location("train_station")

        # Leg 1: drive from origin to station
        driving_leg = request_route(
            resolved_origin,
            train_station,
            "DRIVE"
        )

        if driving_leg is None:
            return {
                "success": False,
                "message": (
                    "No driving route to the configured "
                    "train station was found."
                )
            }

        driving_minutes = round(
            driving_leg["duration_seconds"] / 60
        )

        # Work out when Oliver will actually be ready
        # to board public transport.
        transit_departure_time = (
            datetime.now(timezone.utc)
            + timedelta(
                seconds=driving_leg["duration_seconds"]
            )
            + timedelta(
                minutes=STATION_PARKING_MINUTES
            )
        )

        # Leg 2: station to final destination by transit
        transit_leg = request_route(
            train_station,
            resolved_destination,
            "TRANSIT",
            departure_time=transit_departure_time
        )

        if transit_leg is None:
            return {
                "success": False,
                "message": (
                    "The drive to the station was found, "
                    "but no suitable public transport route "
                    "was found from the station to the destination."
                )
            }

        transit_minutes = round(
            transit_leg["duration_seconds"] / 60
        )

        total_minutes = (
            driving_minutes
            + STATION_PARKING_MINUTES
            + transit_minutes
        )

        total_distance_km = round(
            (
                driving_leg["distance_metres"]
                + transit_leg["distance_metres"]
            )
            / 1000,
            1
        )

        return {
            "success": True,
            "mode": "park_and_ride",
            "origin": origin,
            "destination": destination,
            "drive_to_station_minutes": driving_minutes,
            "parking_and_walk_minutes": STATION_PARKING_MINUTES,
            "transit_from_station_minutes": transit_minutes,
            "total_duration_minutes": total_minutes,
            "total_distance_km": total_distance_km
        }

    except ValueError as error:
        return {
            "success": False,
            "message": str(error)
        }

    except requests.RequestException as error:
        return {
            "success": False,
            "message": f"Route request failed: {error}"
        }