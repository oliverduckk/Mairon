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
from tools.web_tools import web_search


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
            "IMPORTANT: Oliver does not begin public transport journeys directly from home. "
            "Any public transport journey beginning at home requires driving to an "
            "appropriate station or bus stop first. "
            "For Oliver's normal home-to-uni train commute, use park_and_ride."
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
                        "Use transit only when the journey genuinely begins using public transport. "
                        "Use park_and_ride for Oliver's normal home-to-uni train journey."
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
        "name": "web_search",
        "description": (
            "Search the live public internet for current or externally verifiable information. "
            "Use this when Oliver asks about recent events, news, current information, "
            "software versions, documentation, product announcements, changing facts, "
            "or something that requires information beyond the model's training knowledge. "
            "Do not use web search unnecessarily for stable facts that can be answered confidently "
            "without current information. "
            "The search query is sent to an external search provider. Never include passwords, "
            "API keys, private addresses, secret information, or private memory content in a "
            "web search query unless Oliver has explicitly authorised that disclosure."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "A concise search-engine query containing only the information "
                        "necessary to perform the public web search."
                    )
                },
                "topic": {
                    "type": "string",
                    "enum": [
                        "general",
                        "news",
                        "finance"
                    ],
                    "description": (
                        "Search category. Use news for recent news stories, finance for "
                        "financial or market information, and general for everything else."
                    )
                },
                "time_range": {
                    "type": "string",
                    "enum": [
                        "none",
                        "day",
                        "week",
                        "month",
                        "year"
                    ],
                    "description": (
                        "How recent the search results should be. "
                        "Use none when no time restriction is necessary."
                    )
                }
            },
            "required": [
                "query",
                "topic",
                "time_range"
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

        # Any home → public transport journey requires
        # driving to a transit interchange first.
        if (
            origin.lower().strip() == "home"
            and mode == "transit"
        ):
            mode = "park_and_ride"

        return get_route(
            origin,
            destination,
            mode
        )

    if tool_name == "web_search":
        time_range = arguments["time_range"]

        if time_range == "none":
            time_range = None

        return web_search(
            query=arguments["query"],
            topic=arguments["topic"],
            time_range=time_range,
            max_results=5
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