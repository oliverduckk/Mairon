from memory.memory_store import (
    delete_memory,
    list_memories,
    save_memory,
    search_memories,
)

from tools.calendar_tools import (
    get_calendar_events,
    get_next_calendar_event,
)
from tools.desktop_tools import launch_application
from tools.gmail_tools import (
    find_emails,
    get_recent_emails,
    read_email,
)
from tools.route_tools import get_route
from tools.system_tools import get_system_info
from tools.weather_tools import get_weather
from tools.web_tools import web_read, web_search


# --------------------------------------------------
# Tool schema helper
# --------------------------------------------------

def function_tool(
    name,
    description,
    properties=None,
    required=None
):
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties or {},
            "required": required or [],
            "additionalProperties": False
        },
        "strict": True
    }


# --------------------------------------------------
# Tool definitions
# --------------------------------------------------

GET_SYSTEM_INFO_TOOL = function_tool(
    name="get_system_info",
    description=(
        "Get factual information about the computer currently running Mairon, "
        "including operating system, version, computer name, and architecture. "
        "Use this when Oliver asks about the current computer or system."
    )
)


LAUNCH_APPLICATION_TOOL = function_tool(
    name="launch_application",
    description=(
        "Launch an approved application on the computer currently running Mairon. "
        "Only approved applications can be launched."
    ),
    properties={
        "app_name": {
            "type": "string",
            "enum": [
                "notepad",
                "calculator"
            ],
            "description": "The approved application to launch."
        }
    },
    required=["app_name"]
)


GET_WEATHER_TOOL = function_tool(
    name="get_weather",
    description=(
        "Get live current weather and a short forecast for a real-world location. "
        "Use this for current weather, tomorrow's weather, temperature, rain, "
        "or similar weather information."
    ),
    properties={
        "location": {
            "type": "string",
            "description": (
                "The city or location to retrieve weather for, "
                "for example 'Sydney, Australia'."
            )
        }
    },
    required=["location"]
)


GET_ROUTE_TOOL = function_tool(
    name="get_route",
    description=(
        "Get current travel information between two locations. "
        "Use this when Oliver asks about travel time, distance, current driving "
        "time, public transport time, or whether driving or public transport is better. "
        "The aliases 'home' and 'uni' may be used. "
        "IMPORTANT: Oliver never begins a public transport journey directly from home. "
        "Any public transport journey beginning at home requires driving to a station "
        "or bus stop first. For Oliver's normal home-to-uni train commute, "
        "use park_and_ride."
    ),
    properties={
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
                "Use drive for car travel, transit for journeys genuinely beginning "
                "on public transport, and park_and_ride when driving to transit first."
            )
        }
    },
    required=[
        "origin",
        "destination",
        "mode"
    ]
)


GET_CALENDAR_EVENTS_TOOL = function_tool(
    name="get_calendar_events",
    description=(
        "Read Oliver's private Google Calendar for an upcoming time period. "
        "Use this when Oliver asks what he has scheduled today, tomorrow, "
        "during the next week, or during the next month. "
        "Prefer this over public web search for Oliver's personal schedule."
    ),
    properties={
        "period": {
            "type": "string",
            "enum": [
                "today",
                "tomorrow",
                "next_7_days",
                "next_30_days"
            ],
            "description": "Calendar period to retrieve."
        }
    },
    required=["period"]
)


GET_NEXT_CALENDAR_EVENT_TOOL = function_tool(
    name="get_next_calendar_event",
    description=(
        "Get Oliver's next upcoming Google Calendar event. "
        "Use this when he asks about his next event, appointment, class, "
        "deadline, meeting, or other scheduled item."
    )
)


GET_RECENT_EMAILS_TOOL = function_tool(
    name="get_recent_emails",
    description=(
        "Get lightweight summaries of Oliver's recent private Gmail messages. "
        "Use this when Oliver asks what emails he recently received, what unread "
        "emails he has, what arrived today, or what messages came in recently. "
        "This returns sender, subject, date, snippet, unread status, and message ID. "
        "It does not return full email bodies. "
        "Use read_email only if the contents of a particular message need deeper inspection. "
        "This tool is strictly read-only."
    ),
    properties={
        "days": {
            "type": "integer",
            "minimum": 1,
            "maximum": 90,
            "description": (
                "Number of previous days to search. "
                "Use 1 for today or very recent messages."
            )
        },
        "max_results": {
            "type": "integer",
            "minimum": 1,
            "maximum": 20,
            "description": "Maximum number of messages to return."
        },
        "unread_only": {
            "type": "boolean",
            "description": (
                "True only when Oliver specifically wants unread messages."
            )
        }
    },
    required=[
        "days",
        "max_results",
        "unread_only"
    ]
)


FIND_EMAILS_TOOL = function_tool(
    name="find_emails",
    description=(
        "Find recent messages in Oliver's private Gmail using structured search inputs. "
        "Use this when Oliver asks whether he has received email about a person, company, "
        "order, subject, topic, service, or keyword. "
        "Do not construct Gmail search syntax yourself. "
        "Supply the plain search text and desired recency instead. "
        "The result contains lightweight email summaries and message IDs, not full bodies. "
        "If Oliver asks what a particular matching email actually says, use read_email "
        "on the relevant message ID after finding it. "
        "This tool is strictly read-only."
    ),
    properties={
        "search_text": {
            "type": "string",
            "description": (
                "Plain text describing what to search for, "
                "for example 'Hype DC', 'COMP2200', or 'Qantas'."
            )
        },
        "days": {
            "type": "integer",
            "minimum": 1,
            "maximum": 365,
            "description": (
                "How many previous days should be searched. "
                "For 'recent' without a more specific timeframe, normally use 30."
            )
        },
        "unread_only": {
            "type": "boolean",
            "description": (
                "True only if Oliver specifically requested unread matching emails."
            )
        },
        "max_results": {
            "type": "integer",
            "minimum": 1,
            "maximum": 20,
            "description": "Maximum number of matching emails to return."
        }
    },
    required=[
        "search_text",
        "days",
        "unread_only",
        "max_results"
    ]
)


READ_EMAIL_TOOL = function_tool(
    name="read_email",
    description=(
        "Read the contents of one specific private Gmail message. "
        "Use this only when a particular email needs deeper inspection after it has "
        "been identified using get_recent_emails or find_emails. "
        "The message_id should come from a Gmail search result. "
        "Do not read full email bodies unnecessarily when the sender, subject, or snippet "
        "already answers Oliver's question. "
        "This tool is strictly read-only and cannot reply, forward, archive, delete, "
        "mark as read, or otherwise modify the message."
    ),
    properties={
        "message_id": {
            "type": "string",
            "description": (
                "The Gmail message ID returned by get_recent_emails or find_emails."
            )
        }
    },
    required=["message_id"]
)


WEB_SEARCH_TOOL = function_tool(
    name="web_search",
    description=(
        "Search the live public internet for current or externally verifiable information. "
        "Use this for recent events, news, current information, documentation, "
        "software versions, product announcements, and other changing public facts. "
        "Do not use web search for Oliver's private email, calendar, memory, "
        "routes, or other information available through a dedicated private tool. "
        "Never include passwords, API keys, private addresses, private email contents, "
        "or secret information in a public web search query."
    ),
    properties={
        "query": {
            "type": "string",
            "description": "Concise public web search query."
        },
        "topic": {
            "type": "string",
            "enum": [
                "general",
                "news",
                "finance"
            ],
            "description": "Search category."
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
            "description": "How recent search results should be."
        }
    },
    required=[
        "query",
        "topic",
        "time_range"
    ]
)


WEB_READ_TOOL = function_tool(
    name="web_read",
    description=(
        "Read and extract useful content from a specific public HTTP or HTTPS webpage. "
        "Use this after web_search when the actual source needs to be examined. "
        "Prefer authoritative or primary sources when available. "
        "Do not use this tool to access private account data."
    ),
    properties={
        "url": {
            "type": "string",
            "description": "Complete public HTTP or HTTPS URL."
        },
        "focus": {
            "type": "string",
            "description": (
                "Specific information to focus on while reading. "
                "Use an empty string for a general read."
            )
        }
    },
    required=[
        "url",
        "focus"
    ]
)


SAVE_MEMORY_TOOL = function_tool(
    name="save_memory",
    description=(
        "Save information into Mairon's persistent local memory. "
        "Only use this when Oliver explicitly asks Mairon to remember, save, "
        "or store something. Do not automatically save email contents, calendar "
        "information, web results, jokes, temporary facts, or inferred information."
    ),
    properties={
        "memory": {
            "type": "string",
            "description": (
                "The concise information Oliver explicitly requested to be remembered."
            )
        }
    },
    required=["memory"]
)


SEARCH_MEMORY_TOOL = function_tool(
    name="search_memory",
    description=(
        "Search Mairon's persistent local memory for information Oliver previously "
        "asked Mairon to remember."
    ),
    properties={
        "query": {
            "type": "string",
            "description": "Information to search persistent memory for."
        }
    },
    required=["query"]
)


LIST_MEMORIES_TOOL = function_tool(
    name="list_memories",
    description=(
        "List all information currently stored in Mairon's persistent local memory. "
        "Use when Oliver explicitly asks what Mairon remembers about him."
    )
)


DELETE_MEMORY_TOOL = function_tool(
    name="delete_memory",
    description=(
        "Delete a persistent memory that Oliver explicitly asks Mairon to forget. "
        "The deletion system is conservative and will not delete anything if "
        "multiple memories ambiguously match."
    ),
    properties={
        "query": {
            "type": "string",
            "description": "Description of the memory Oliver wants forgotten."
        }
    },
    required=["query"]
)


# --------------------------------------------------
# Provider-specific capability boundaries
# --------------------------------------------------

LOCAL_TOOLS = [
    GET_SYSTEM_INFO_TOOL,
    LAUNCH_APPLICATION_TOOL,
    GET_WEATHER_TOOL,
    GET_ROUTE_TOOL,
    GET_CALENDAR_EVENTS_TOOL,
    GET_NEXT_CALENDAR_EVENT_TOOL,
    GET_RECENT_EMAILS_TOOL,
    FIND_EMAILS_TOOL,
    READ_EMAIL_TOOL,
    WEB_SEARCH_TOOL,
    WEB_READ_TOOL,
    SAVE_MEMORY_TOOL,
    SEARCH_MEMORY_TOOL,
    LIST_MEMORIES_TOOL,
    DELETE_MEMORY_TOOL,
]


# Cloud models deliberately receive only public-information tools.
#
# Gmail, Calendar, memory, routes, local system information,
# and desktop control are absent.
CLOUD_TOOLS = [
    GET_WEATHER_TOOL,
    WEB_SEARCH_TOOL,
    WEB_READ_TOOL,
]


# Current Ollama provider imports TOOLS.
TOOLS = LOCAL_TOOLS


# --------------------------------------------------
# Tool execution
# --------------------------------------------------

def execute_tool(
    tool_name,
    arguments=None
):
    arguments = arguments or {}

    if tool_name == "get_system_info":
        return get_system_info()

    if tool_name == "launch_application":
        app_name = arguments.get(
            "app_name"
        )

        if not app_name:
            return {
                "success": False,
                "message": "No application name was provided."
            }

        return launch_application(
            app_name
        )

    if tool_name == "get_weather":
        location = arguments.get(
            "location"
        )

        if not location:
            return {
                "success": False,
                "message": "No weather location was provided."
            }

        return get_weather(
            location
        )

    if tool_name == "get_route":
        origin = arguments.get(
            "origin"
        )

        destination = arguments.get(
            "destination"
        )

        mode = arguments.get(
            "mode"
        )

        if (
            not origin
            or not destination
            or not mode
        ):
            return {
                "success": False,
                "message": (
                    "Route request is missing an origin, "
                    "destination, or travel mode."
                )
            }

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

    if tool_name == "get_calendar_events":
        period = arguments.get(
            "period",
            "today"
        )

        return get_calendar_events(
            period
        )

    if tool_name == "get_next_calendar_event":
        return get_next_calendar_event()

    if tool_name == "get_recent_emails":
        return get_recent_emails(
            days=arguments.get(
                "days",
                7
            ),
            max_results=arguments.get(
                "max_results",
                10
            ),
            unread_only=arguments.get(
                "unread_only",
                False
            )
        )

    if tool_name == "find_emails":
        return find_emails(
            search_text=arguments.get(
                "search_text",
                ""
            ),
            days=arguments.get(
                "days",
                30
            ),
            unread_only=arguments.get(
                "unread_only",
                False
            ),
            max_results=arguments.get(
                "max_results",
                10
            )
        )

    if tool_name == "read_email":
        message_id = arguments.get(
            "message_id"
        )

        if not message_id:
            return {
                "success": False,
                "message": (
                    "No Gmail message ID was provided."
                )
            }

        return read_email(
            message_id
        )

    if tool_name == "web_search":
        query = arguments.get(
            "query"
        )

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
        url = arguments.get(
            "url"
        )

        if not url:
            return {
                "success": False,
                "message": "No webpage URL was provided."
            }

        focus = arguments.get(
            "focus",
            ""
        )

        if isinstance(
            focus,
            str
        ):
            focus = focus.strip()

        if not focus:
            focus = None

        return web_read(
            url=url,
            focus=focus
        )

    if tool_name == "save_memory":
        memory = arguments.get(
            "memory"
        )

        if not memory:
            return {
                "success": False,
                "message": "No memory content was provided."
            }

        return save_memory(
            memory
        )

    if tool_name == "search_memory":
        query = arguments.get(
            "query"
        )

        if not query:
            return {
                "success": False,
                "message": "No memory search query was provided."
            }

        return search_memories(
            query
        )

    if tool_name == "list_memories":
        return list_memories()

    if tool_name == "delete_memory":
        query = arguments.get(
            "query"
        )

        if not query:
            return {
                "success": False,
                "message": "No memory deletion query was provided."
            }

        return delete_memory(
            query
        )

    return {
        "success": False,
        "message": (
            f"Unknown tool: {tool_name}"
        )
    }