import os
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv


load_dotenv()


ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

LOCATION_ALIASES = {
    "home": os.getenv("MAIRON_HOME_ADDRESS"),
    "work": os.getenv("MAIRON_WORK_ADDRESS"),
    "uni": os.getenv("MAIRON_UNI_ADDRESS"),
    "train_station": os.getenv("MAIRON_TRAIN_STATION"),
}

STATION_PARKING_MINUTES = int(
    os.getenv("MAIRON_STATION_PARKING_MINUTES", "5")
)


# --------------------------------------------------
# Preferred work-route configuration
# --------------------------------------------------

WORK_ROUTE_VIA_VALUES = [
    value.strip()
    for value in (
        os.getenv("MAIRON_WORK_ROUTE_VIA_1", ""),
        os.getenv("MAIRON_WORK_ROUTE_VIA_2", ""),
        os.getenv("MAIRON_WORK_ROUTE_VIA_3", ""),
        os.getenv("MAIRON_WORK_ROUTE_VIA_4", ""),
        os.getenv("MAIRON_WORK_ROUTE_VIA_5", ""),
    )
    if value.strip()
]


# --------------------------------------------------
# Location helpers
# --------------------------------------------------

def normalise_location_name(location):
    if not isinstance(location, str):
        return ""

    return location.lower().strip()


def resolve_location(location):
    """
    Convert a private Mairon alias such as home/work/uni into
    the real value stored locally in .env.
    """

    location_lower = normalise_location_name(location)

    if location_lower in LOCATION_ALIASES:
        resolved = LOCATION_ALIASES[location_lower]

        if not resolved:
            raise ValueError(
                f"Location alias '{location_lower}' is not configured."
            )

        return resolved

    return location


def parse_lat_lng(value):
    """
    Parse:
        latitude,longitude

    Otherwise return None so the value can be treated as an
    address / suburb / place string.
    """

    if not isinstance(value, str):
        return None

    parts = [
        part.strip()
        for part in value.split(",")
    ]

    if len(parts) != 2:
        return None

    try:
        latitude = float(parts[0])
        longitude = float(parts[1])
    except ValueError:
        return None

    if not (-90 <= latitude <= 90):
        return None

    if not (-180 <= longitude <= 180):
        return None

    return {
        "latitude": latitude,
        "longitude": longitude
    }


def build_waypoint(value, via=False):
    """
    Build one Routes API waypoint.

    Coordinates are used directly when supplied as lat,lng.
    Otherwise Google geocodes the string.
    """

    coordinates = parse_lat_lng(value)

    if coordinates:
        waypoint = {
            "location": {
                "latLng": coordinates
            }
        }
    else:
        waypoint = {
            "address": value
        }

    if via:
        waypoint["via"] = True

    return waypoint


def normalise_via_values(via):
    """
    Accept:
        None
        "Suburb NSW"
        ["Suburb NSW"]
        ["point 1", "point 2"]

    and return a clean list.
    """

    if via is None:
        return []

    if isinstance(via, str):
        value = via.strip()
        return [value] if value else []

    if isinstance(via, (list, tuple)):
        return [
            str(value).strip()
            for value in via
            if str(value).strip()
        ]

    return []


def get_preferred_work_values(origin, destination):
    """
    Return Oliver's private preferred work-route points in the
    correct direction.
    """

    origin_name = normalise_location_name(origin)
    destination_name = normalise_location_name(destination)

    if not WORK_ROUTE_VIA_VALUES:
        return []

    if (
        origin_name == "home"
        and destination_name == "work"
    ):
        return list(WORK_ROUTE_VIA_VALUES)

    if (
        origin_name == "work"
        and destination_name == "home"
    ):
        return list(
            reversed(WORK_ROUTE_VIA_VALUES)
        )

    return []


# --------------------------------------------------
# Route helpers
# --------------------------------------------------

def parse_duration_seconds(duration):
    return float(
        duration.rstrip("s")
    )


def format_departure_time(dt):
    return (
        dt.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def request_route(
    origin,
    destination,
    travel_mode,
    departure_time=None,
    intermediates=None
):
    """
    Make one Google Routes API request.

    Returns:
        {
            "success": True,
            ...
        }

    or a structured failure.

    This keeps the API result distinct from Mairon's higher-level
    route policy.
    """

    request_body = {
        "origin": build_waypoint(origin),
        "destination": build_waypoint(destination),
        "travelMode": travel_mode,
        "languageCode": "en-AU",
        "units": "METRIC"
    }

    if intermediates:
        request_body[
            "intermediates"
        ] = intermediates

    if travel_mode == "DRIVE":
        request_body[
            "routingPreference"
        ] = "TRAFFIC_AWARE_OPTIMAL"

    if departure_time is not None:
        request_body[
            "departureTime"
        ] = format_departure_time(
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
    routes = data.get(
        "routes",
        []
    )

    if not routes:
        return {
            "success": False,
            "message": "Google returned no route.",
            "intermediate_count": len(
                intermediates or []
            )
        }

    route = routes[0]

    result = {
        "success": True,
        "duration_seconds": (
            parse_duration_seconds(
                route["duration"]
            )
        ),
        "distance_metres": (
            route["distanceMeters"]
        )
    }

    if "staticDuration" in route:
        result[
            "static_duration_seconds"
        ] = parse_duration_seconds(
            route["staticDuration"]
        )

    return result


def build_route_result(
    route,
    origin,
    destination,
    profile,
    waypoint_values=None,
    warning=None
):
    """
    Convert one successful raw driving response into Mairon's
    normal public route result.
    """

    duration_minutes = round(
        route[
            "duration_seconds"
        ] / 60
    )

    waypoint_values = (
        waypoint_values
        or []
    )

    result = {
        "success": True,
        "mode": "drive",
        "origin": origin,
        "destination": destination,
        "route_profile": profile,
        "via_count": len(
            waypoint_values
        ),
        "duration_minutes": (
            duration_minutes
        ),
        "distance_km": round(
            route[
                "distance_metres"
            ] / 1000,
            1
        )
    }

    if waypoint_values:
        # Deliberately expose only the user/model-provided names here.
        # Private preferred-work coordinates remain hidden.
        if profile == "custom_via":
            result[
                "via"
            ] = waypoint_values

    if warning:
        result[
            "warning"
        ] = warning

    if (
        "static_duration_seconds"
        in route
    ):
        static_minutes = round(
            route[
                "static_duration_seconds"
            ] / 60
        )

        result[
            "duration_without_current_traffic_minutes"
        ] = static_minutes

        result[
            "traffic_delay_minutes"
        ] = (
            duration_minutes
            - static_minutes
        )

    return result


def calculate_driving_route(
    origin,
    destination,
    explicit_via=None,
    use_preferred_route=True
):
    """
    Driving policy.

    Priority:
        1. Explicit user-requested via locations.
        2. Private preferred home<->work route.
        3. Google's normal optimal route.

    Explicit via locations are normal intermediate waypoints rather
    than strict pass-through points. This is intentionally more robust
    for conversational requests such as:
        "What if I go through Castle Hill instead?"

    Preferred work points first try strict pass-through waypoints. If
    Google cannot route through one of those exact points, Mairon retries
    them as normal intermediate points before finally falling back to
    Google's unconstrained route.
    """

    resolved_origin = (
        resolve_location(origin)
    )

    resolved_destination = (
        resolve_location(destination)
    )

    explicit_values = (
        normalise_via_values(
            explicit_via
        )
    )

    # --------------------------------------------------
    # Explicit conversational via route
    # --------------------------------------------------

    if explicit_values:

        intermediates = [
            build_waypoint(
                value,
                via=False
            )
            for value in explicit_values
        ]

        route = request_route(
            resolved_origin,
            resolved_destination,
            "DRIVE",
            intermediates=intermediates
        )

        if not route.get(
            "success"
        ):
            return {
                "success": False,
                "message": (
                    "No driving route was found through the "
                    "requested intermediate location(s)."
                ),
                "origin": origin,
                "destination": destination,
                "via": explicit_values
            }

        return build_route_result(
            route=route,
            origin=origin,
            destination=destination,
            profile="custom_via",
            waypoint_values=explicit_values
        )

    # --------------------------------------------------
    # Private preferred work route
    # --------------------------------------------------

    preferred_values = []

    if use_preferred_route:
        preferred_values = (
            get_preferred_work_values(
                origin,
                destination
            )
        )

    if preferred_values:

        # Attempt 1:
        # strict pass-through points.
        via_intermediates = [
            build_waypoint(
                value,
                via=True
            )
            for value in preferred_values
        ]

        preferred_route = (
            request_route(
                resolved_origin,
                resolved_destination,
                "DRIVE",
                intermediates=(
                    via_intermediates
                )
            )
        )

        if preferred_route.get(
            "success"
        ):
            return build_route_result(
                route=preferred_route,
                origin=origin,
                destination=destination,
                profile=(
                    "preferred_work_route"
                ),
                waypoint_values=(
                    preferred_values
                )
            )

        # Attempt 2:
        # same points as ordinary intermediate waypoints.
        #
        # Google documents that strict via waypoints can fail if
        # the chosen point is inaccessible. Normal intermediates
        # give the routing engine more forgiving road snapping.
        stop_intermediates = [
            build_waypoint(
                value,
                via=False
            )
            for value in preferred_values
        ]

        preferred_stop_route = (
            request_route(
                resolved_origin,
                resolved_destination,
                "DRIVE",
                intermediates=(
                    stop_intermediates
                )
            )
        )

        if preferred_stop_route.get(
            "success"
        ):
            return build_route_result(
                route=preferred_stop_route,
                origin=origin,
                destination=destination,
                profile=(
                    "preferred_work_route"
                ),
                waypoint_values=(
                    preferred_values
                ),
                warning=(
                    "Strict pass-through routing failed, "
                    "so the preferred work points were "
                    "used as normal intermediates."
                )
            )

        # Attempt 3:
        # don't kill the whole morning brief because a
        # preferred-route point is broken.
        google_route = request_route(
            resolved_origin,
            resolved_destination,
            "DRIVE"
        )

        if google_route.get(
            "success"
        ):
            return build_route_result(
                route=google_route,
                origin=origin,
                destination=destination,
                profile=(
                    "google_optimal_fallback"
                ),
                warning=(
                    "The configured preferred work route "
                    "could not be calculated, so Google "
                    "optimal routing was used instead."
                )
            )

        return {
            "success": False,
            "message": (
                "Neither the preferred work route nor "
                "Google's normal driving route could be calculated."
            )
        }

    # --------------------------------------------------
    # Normal Google route
    # --------------------------------------------------

    route = request_route(
        resolved_origin,
        resolved_destination,
        "DRIVE"
    )

    if not route.get(
        "success"
    ):
        return {
            "success": False,
            "message": (
                "No driving route was found."
            )
        }

    return build_route_result(
        route=route,
        origin=origin,
        destination=destination,
        profile="google_optimal"
    )


# --------------------------------------------------
# Main public function
# --------------------------------------------------

def get_route(
    origin,
    destination,
    mode="drive",
    via=None,
    use_preferred_route=True
):
    """
    Get travel information.

    Supported modes:

        drive
        transit
        park_and_ride

    Optional via:
        A single location or list of locations that the driving route
        should go through.

    Examples:

        get_route(
            "home",
            "Some party address",
            "drive"
        )

        get_route(
            "home",
            "Some party address",
            "drive",
            via=["Castle Hill NSW, Australia"]
        )

    For home<->work driving, Mairon automatically uses Oliver's
    preferred commute points unless an explicit via route is supplied.
    """

    if not GOOGLE_MAPS_API_KEY:
        return {
            "success": False,
            "message": (
                "Google Maps API key is not configured."
            )
        }

    mode = mode.lower().strip()

    if mode not in (
        "drive",
        "transit",
        "park_and_ride"
    ):
        return {
            "success": False,
            "message": (
                f"Unsupported travel mode '{mode}'."
            )
        }

    try:

        # --------------------------------------------------
        # Driving
        # --------------------------------------------------

        if mode == "drive":
            return calculate_driving_route(
                origin=origin,
                destination=destination,
                explicit_via=via,
                use_preferred_route=(
                    use_preferred_route
                )
            )

        resolved_origin = (
            resolve_location(origin)
        )

        resolved_destination = (
            resolve_location(destination)
        )

        # --------------------------------------------------
        # Pure public transport
        # --------------------------------------------------

        if mode == "transit":

            route = request_route(
                resolved_origin,
                resolved_destination,
                "TRANSIT"
            )

            if not route.get(
                "success"
            ):
                return {
                    "success": False,
                    "message": (
                        "No public transport route was found."
                    )
                }

            return {
                "success": True,
                "mode": "transit",
                "origin": origin,
                "destination": destination,
                "distance_km": round(
                    route[
                        "distance_metres"
                    ] / 1000,
                    1
                ),
                "duration_minutes": round(
                    route[
                        "duration_seconds"
                    ] / 60
                )
            }

        # --------------------------------------------------
        # Park and ride
        # --------------------------------------------------

        train_station = (
            resolve_location(
                "train_station"
            )
        )

        driving_leg = request_route(
            resolved_origin,
            train_station,
            "DRIVE"
        )

        if not driving_leg.get(
            "success"
        ):
            return {
                "success": False,
                "message": (
                    "No driving route to the configured "
                    "train station was found."
                )
            }

        driving_minutes = round(
            driving_leg[
                "duration_seconds"
            ] / 60
        )

        transit_departure_time = (
            datetime.now(
                timezone.utc
            )
            + timedelta(
                seconds=driving_leg[
                    "duration_seconds"
                ]
            )
            + timedelta(
                minutes=(
                    STATION_PARKING_MINUTES
                )
            )
        )

        transit_leg = request_route(
            train_station,
            resolved_destination,
            "TRANSIT",
            departure_time=(
                transit_departure_time
            )
        )

        if not transit_leg.get(
            "success"
        ):
            return {
                "success": False,
                "message": (
                    "The drive to the station was found, "
                    "but no suitable public transport route "
                    "was found from the station to the destination."
                )
            }

        transit_minutes = round(
            transit_leg[
                "duration_seconds"
            ] / 60
        )

        total_minutes = (
            driving_minutes
            + STATION_PARKING_MINUTES
            + transit_minutes
        )

        total_distance_km = round(
            (
                driving_leg[
                    "distance_metres"
                ]
                + transit_leg[
                    "distance_metres"
                ]
            )
            / 1000,
            1
        )

        return {
            "success": True,
            "mode": "park_and_ride",
            "origin": origin,
            "destination": destination,
            "drive_to_station_minutes": (
                driving_minutes
            ),
            "parking_and_walk_minutes": (
                STATION_PARKING_MINUTES
            ),
            "transit_from_station_minutes": (
                transit_minutes
            ),
            "total_duration_minutes": (
                total_minutes
            ),
            "total_distance_km": (
                total_distance_km
            )
        }

    except ValueError as error:
        return {
            "success": False,
            "message": str(error)
        }

    except requests.RequestException as error:
        return {
            "success": False,
            "message": (
                f"Route request failed: {error}"
            )
        }


# --------------------------------------------------
# Preferred work-route diagnostics
# --------------------------------------------------

def diagnose_preferred_work_route():
    """
    Diagnose the private home->work configuration without printing
    the actual private waypoint values.

    This tells us whether:
        - base Google routing works
        - all strict via points work
        - all ordinary intermediate points work
        - a specific waypoint prefix is where routing starts failing
    """

    resolved_home = resolve_location(
        "home"
    )

    resolved_work = resolve_location(
        "work"
    )

    result = {
        "success": True,
        "preferred_point_count": len(
            WORK_ROUTE_VIA_VALUES
        ),
        "tests": []
    }

    base = request_route(
        resolved_home,
        resolved_work,
        "DRIVE"
    )

    result[
        "tests"
    ].append({
        "test": "google_optimal",
        "success": base.get(
            "success",
            False
        )
    })

    if not WORK_ROUTE_VIA_VALUES:
        result[
            "message"
        ] = (
            "No preferred work-route points are configured."
        )

        return result

    # Test the complete strict-via route.
    all_via = request_route(
        resolved_home,
        resolved_work,
        "DRIVE",
        intermediates=[
            build_waypoint(
                value,
                via=True
            )
            for value
            in WORK_ROUTE_VIA_VALUES
        ]
    )

    result[
        "tests"
    ].append({
        "test": "all_points_as_via",
        "success": all_via.get(
            "success",
            False
        )
    })

    # Test the complete ordinary-intermediate route.
    all_stop = request_route(
        resolved_home,
        resolved_work,
        "DRIVE",
        intermediates=[
            build_waypoint(
                value,
                via=False
            )
            for value
            in WORK_ROUTE_VIA_VALUES
        ]
    )

    result[
        "tests"
    ].append({
        "test": "all_points_as_intermediates",
        "success": all_stop.get(
            "success",
            False
        )
    })

    # Incrementally add strict-via points.
    #
    # We deliberately report only via_1, via_2, etc.
    # Actual coordinates remain private.
    for count in range(
        1,
        len(
            WORK_ROUTE_VIA_VALUES
        ) + 1
    ):

        test = request_route(
            resolved_home,
            resolved_work,
            "DRIVE",
            intermediates=[
                build_waypoint(
                    value,
                    via=True
                )
                for value
                in WORK_ROUTE_VIA_VALUES[
                    :count
                ]
            ]
        )

        result[
            "tests"
        ].append({
            "test": (
                f"via_prefix_{count}"
            ),
            "success": test.get(
                "success",
                False
            )
        })

    return result


# --------------------------------------------------
# Standalone test
# --------------------------------------------------

if __name__ == "__main__":

    import json

    print(
        "--- Preferred work-route diagnostic ---"
    )

    print(
        json.dumps(
            diagnose_preferred_work_route(),
            indent=2
        )
    )

    print()

    print(
        "--- Preferred work commute ---"
    )

    print(
        json.dumps(
            get_route(
                origin="home",
                destination="work",
                mode="drive"
            ),
            indent=2
        )
    )
