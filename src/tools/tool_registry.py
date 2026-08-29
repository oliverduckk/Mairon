from memory.memory_store import (
    delete_memory,
    list_memories,
    save_memory,
    search_memories,
)

from tools.desktop_tools import launch_application
from tools.route_tools import get_route
from tools.system_tools import get_system_info
from tools.weather_tools import get_weather


TOOLS = [
    {
        "type": "function",
        "name": "get_system_info",
        "description": (
            "Get factual information about the computer currently running Mairon, "
            "including its operating system, OS version, computer name, and architecture. "
            "Use this when Oliver asks about the current computer or system."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False
        },
        "strict": True
    },

    {
        "type": "function",
        "name": "launch_application",
        "description": (
            "Launch an approved application on the computer currently running Mairon. "
            "Only approved applications can be launched."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "enum": [
                        "notepad",
                        "calculator"
                    ],
                    "description": "The approved application to launch."
                }
            },
            "required": ["app_name"],
            "additionalProperties": False
        },
        "strict": True
    },

    {
        "type": "function",
        "name": "get_weather",
        "description": (
            "Get live current weather and a short forecast for a real-world location "
            "using an internet weather service. Use this when Oliver asks about current "
            "weather, today's weather, tomorrow's weather, temperature, rain, or similar "
            "weather information."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": (
                        "The city or location to retrieve weather for, "
                        "for example 'Sydney, Australia'."
                    )
                }
            },
            "required": ["location"],
            "additionalProperties": False
        },
        "strict": True
    },

    {
        "type": "function",
        "name": "get_route",
        "description": (
            "Get current travel information between two locations. "
            "Use this when Oliver asks how long it will take to get somewhere, "
            "how far away somewhere is, current driving time, public transport time, "
            "or whether driving or public transport is preferable. "
            "The aliases 'home' and 'uni' may be used. "
            "IMPORTANT: Oliver lives in a rural area and does NOT begin his normal "
            "train commute to uni using public transport from home. He drives from "
            "home to his configured train station, parks, and then continues by train. "
            "Therefore, whenever Oliver asks about going from home to uni 'by train', "
            "'by public transport', or similar, ALWAYS use park_and_ride rather than transit. "
            "Use transit only when the requested journey genuinely begins at a public "
            "transport-accessible origin."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "origin": {
                    "type": "string",
                    "description": "Starting location, such as 'home'."
                },
                "destination": {
                    "type": "string",
                    "description": "Destination, such as 'uni'."
                },
                "mode": {
                    "type": "string",
                    "enum": [
                        "drive",
                        "transit",
                        "park_and_ride"
                    ],
                    "description": (
                        "Travel mode. Use drive for a car journey. "
                        "Use transit for a journey that genuinely starts using public transport. "
                        "Use park_and_ride for Oliver's normal home-to-uni train journey, "
                        "because he first drives from home to his configured train station."
                    )
                }
            },
            "required": [
                "origin",
                "destination",
                "mode"
            ],
            "additionalProperties": False
        },
        "strict": True
    },

    {
        "type": "function",
        "name": "save_memory",
        "description": (
            "Save information into Mairon's persistent local memory. "
            "Only use this when Oliver explicitly asks you to remember, save, or store something. "
            "Do not save ordinary conversation, jokes, hypothetical examples, temporary information, "
            "or facts that Oliver did not explicitly ask to remember."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "memory": {
                    "type": "string",
                    "description": (
                        "The concise fact or information Oliver explicitly asked Mairon to remember."
                    )
                }
            },
            "required": ["memory"],
            "additionalProperties": False
        },
        "strict": True
    },

    {
        "type": "function",
        "name": "search_memory",
        "description": (
            "Search Mairon's persistent local memory for information previously saved by Oliver. "
            "Use this when Oliver asks about something he may have previously asked Mairon to remember."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What information to search Mairon's memory for."
                }
            },
            "required": ["query"],
            "additionalProperties": False
        },
        "strict": True
    },

    {
        "type": "function",
        "name": "list_memories",
        "description": (
            "List all information currently stored in Mairon's persistent local memory. "
            "Use this when Oliver explicitly asks what Mairon remembers or has stored about him."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False
        },
        "strict": True
    },

    {
        "type": "function",
        "name": "delete_memory",
        "description": (
            "Delete a persistent memory that Oliver explicitly asks Mairon to forget. "
            "The deletion system is conservative and will not delete anything when multiple "
            "memories match the request."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Description of the memory Oliver explicitly wants forgotten."
                }
            },
            "required": ["query"],
            "additionalProperties": False
        },
        "strict": True
    }
]


def execute_tool(tool_name, arguments=None):
    arguments = arguments or {}

    if tool_name == "get_system_info":
        return get_system_info()

    if tool_name == "launch_application":
        return launch_application(arguments["app_name"])

    if tool_name == "get_weather":
        return get_weather(arguments["location"])

    if tool_name == "get_route":
        origin = arguments["origin"]
        destination = arguments["destination"]
        mode = arguments["mode"]

        # Deterministic commute rule:
        # Oliver's normal home → uni public transport journey
        # always involves driving to the station first.
        if (
            origin.lower().strip() == "home"
            and destination.lower().strip() == "uni"
            and mode == "transit"
        ):
            mode = "park_and_ride"

        return get_route(
            origin,
            destination,
            mode
        )

    if tool_name == "save_memory":
        return save_memory(arguments["memory"])

    if tool_name == "search_memory":
        return search_memories(arguments["query"])

    if tool_name == "list_memories":
        return list_memories()

    if tool_name == "delete_memory":
        return delete_memory(arguments["query"])

    raise ValueError(f"Unknown tool: {tool_name}")