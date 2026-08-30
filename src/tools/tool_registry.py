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
from tools.web_tools import web_read, web_search


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
            "This tool returns search results and snippets. "
            "If an exact or authoritative answer requires reading a source in detail, "
            "use web_read on the most relevant result after searching. "
            "Do not use web search unnecessarily for stable facts that can be answered confidently "
            "without current information. "
            "Never include passwords, API keys, private addresses, secret information, "
            "or private memory content in a search query unless Oliver explicitly authorises it."
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
        "name": "web_read",
        "description": (
            "Read and extract useful content from a specific public webpage. "
            "Use this after web_search when a search result appears authoritative or relevant "
            "and the actual webpage needs to be examined before answering. "
            "Prefer official documentation, primary sources, developers, manufacturers, "
            "government sources, or other authoritative sources when available. "
            "Do not invent URLs. Normally use a URL obtained from web_search or explicitly "
            "provided by Oliver. "
            "The focus should describe the specific information being verified. "
            "This tool is for public HTTP or HTTPS webpages only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": (
                        "The complete HTTP or HTTPS URL of the public webpage to read."
                    )
                },
                "focus": {
                    "type": "string",
                    "description": (
                        "The specific question or information to focus on while reading. "
                        "Use an empty string if no specific focus is necessary."
                    )
                }
            },
            "required": [
                "url",
                "focus"
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
        app_name = arguments.get("app_name")

        if not app_name:
            return {
                "success": False,
                "message": "No application name was provided."
            }

        return launch_application(app_name)

    if tool_name == "get_weather":
        location = arguments.get("location")

        if not location:
            return {
                "success": False,
                "message": "No weather location was provided."
            }

        return get_weather(location)

    if tool_name == "get_route":
        origin = arguments.get("origin")
        destination = arguments.get("destination")
        mode = arguments.get("mode")

        if not origin or not destination or not mode:
            return {
                "success": False,
                "message": (
                    "Route request is missing an origin, "
                    "destination, or travel mode."
                )
            }

        # Any public transport journey beginning from home
        # requires driving to a transit interchange first.
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
        query = arguments.get("query")

        if not query:
            return {
                "success": False,
                "message": "No web search query was provided."
            }

        topic = arguments.get(
            "topic",
            "general"
        )

        time_range = arguments.get(
            "time_range",
            "none"
        )

        if time_range == "none":
            time_range = None

        return web_search(
            query=query,
            topic=topic,
            time_range=time_range,
            max_results=5
        )

    if tool_name == "web_read":
        url = arguments.get("url")

        if not url:
            return {
                "success": False,
                "message": "No webpage URL was provided."
            }

        # Models may omit focus despite the schema requesting it.
        # Treat a missing or empty focus as a general page read
        # instead of crashing Mairon.
        focus = arguments.get(
            "focus",
            ""
        )

        if isinstance(focus, str):
            focus = focus.strip()

        if not focus:
            focus = None

        return web_read(
            url=url,
            focus=focus
        )

    if tool_name == "save_memory":
        memory = arguments.get("memory")

        if not memory:
            return {
                "success": False,
                "message": "No memory content was provided."
            }

        return save_memory(memory)

    if tool_name == "search_memory":
        query = arguments.get("query")

        if not query:
            return {
                "success": False,
                "message": "No memory search query was provided."
            }

        return search_memories(query)

    if tool_name == "list_memories":
        return list_memories()

    if tool_name == "delete_memory":
        query = arguments.get("query")

        if not query:
            return {
                "success": False,
                "message": "No memory deletion query was provided."
            }

        return delete_memory(query)

    return {
        "success": False,
        "message": f"Unknown tool: {tool_name}"
    }