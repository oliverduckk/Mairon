from memory.memory_store import (
    delete_memory,
    list_memories,
    save_memory,
    search_memories,
)

from tools.alarm_tools import (
    disable_alarm_for_date,
    get_alarm_for_date,
    get_upcoming_alarms,
    set_alarm_for_date,
)

from tools.calendar_tools import (
    get_calendar_events,
    get_next_calendar_event,
)

from tools.desktop_tools import (
    launch_application,
)

from tools.gmail_tools import (
    find_emails,
    get_recent_emails,
    read_email,
)

from tools.route_tools import (
    get_route,
)

from tools.routine_tools import (
    get_routine_context,
    set_work_location,
)

from tools.system_tools import (
    get_system_info,
)

from tools.weather_tools import (
    get_weather,
)

from tools.web_tools import (
    web_read,
    web_search,
)


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
# System / desktop tools
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


# --------------------------------------------------
# Weather
# --------------------------------------------------

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


# --------------------------------------------------
# Routes
# --------------------------------------------------

GET_ROUTE_TOOL = function_tool(
    name="get_route",
    description=(
        "Get current travel information between two locations. "
        "Use this when Oliver asks about travel time, distance, current driving "
        "time, public transport time, or whether driving or public transport is better. "
        "Private aliases include 'home', 'work', 'uni', and 'train_station'. "
        "For a normal home-to-work driving request, use origin='home', "
        "destination='work', mode='drive'; Mairon Core will automatically use Oliver's "
        "configured preferred work-route corridor. "
        "For follow-up driving questions such as 'what if I go through Castle Hill instead?', "
        "reuse the previous origin and destination and pass the requested place in 'via'. "
        "Do not invent a new destination merely because Oliver asks to go through another place. "
        "IMPORTANT: Oliver never begins a public transport journey directly from home. "
        "Any public transport journey beginning at home requires driving to a station "
        "or bus stop first. For Oliver's normal home-to-uni train commute, "
        "use park_and_ride."
    ),
    properties={
        "origin": {
            "type": "string",
            "description": (
                "Starting location. Private aliases include 'home', 'work', "
                "'uni', and 'train_station'."
            )
        },
        "destination": {
            "type": "string",
            "description": (
                "Final destination. On a follow-up route question, preserve the "
                "previous destination unless Oliver explicitly changes it."
            )
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
        },
        "via": {
            "type": "array",
            "items": {
                "type": "string"
            },
            "description": (
                "Optional intermediate places the driving route should go through, "
                "in travel order. Use this for requests such as 'go through Castle Hill' "
                "or 'what if I go via Parramatta instead?'. Leave it empty/omitted for "
                "normal routing."
            )
        }
    },
    required=[
        "origin",
        "destination",
        "mode"
    ]
)


# --------------------------------------------------
# Calendar
# --------------------------------------------------

GET_CALENDAR_EVENTS_TOOL = function_tool(
    name="get_calendar_events",
    description=(
        "Read Oliver's private Google Calendar for an upcoming time period. "
        "Use this when Oliver asks specifically about Calendar events today, tomorrow, "
        "during the next week, or during the next month. General questions such as "
        "'what am I doing tomorrow?' are handled by Mairon Core using routine and "
        "Calendar together."
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


# --------------------------------------------------
# Gmail
# --------------------------------------------------

GET_RECENT_EMAILS_TOOL = function_tool(
    name="get_recent_emails",
    description=(
        "Get lightweight summaries of Oliver's recent private Gmail messages. "
        "Use this when Oliver asks what emails he recently received, what unread "
        "emails he has, what arrived today, or what messages came in recently. "
        "This returns sender, subject, date, snippet, unread status, and message ID. "
        "It does not return full email bodies. Use read_email only if the contents "
        "of a particular message need deeper inspection. This tool is strictly read-only."
    ),
    properties={
        "days": {
            "type": "integer",
            "minimum": 1,
            "maximum": 90,
            "description": "Number of previous days to search."
        },
        "max_results": {
            "type": "integer",
            "minimum": 1,
            "maximum": 20,
            "description": "Maximum number of messages to return."
        },
        "unread_only": {
            "type": "boolean",
            "description": "True only when Oliver specifically wants unread messages."
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
        "order, subject, topic, service, or keyword. Do not construct Gmail search syntax "
        "yourself. The result contains lightweight summaries and message IDs, not full bodies. "
        "Use read_email on a relevant message ID when body details are required."
    ),
    properties={
        "search_text": {
            "type": "string",
            "description": "Plain text describing what to search for."
        },
        "days": {
            "type": "integer",
            "minimum": 1,
            "maximum": 365,
            "description": "How many previous days should be searched."
        },
        "unread_only": {
            "type": "boolean",
            "description": "True only if Oliver specifically requested unread matching emails."
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
        "Read the contents of one specific private Gmail message after it has been "
        "identified using get_recent_emails or find_emails. Do not read full bodies "
        "unnecessarily when the summary already answers Oliver's question. This tool "
        "is strictly read-only."
    ),
    properties={
        "message_id": {
            "type": "string",
            "description": "The Gmail message ID returned by a Gmail search tool."
        }
    },
    required=["message_id"]
)


# --------------------------------------------------
# Routine / daily context
# --------------------------------------------------

GET_ROUTINE_CONTEXT_TOOL = function_tool(
    name="get_routine_context",
    description=(
        "Get Mairon's private local understanding of Oliver's routine for one specific date. "
        "This combines his normal repeating weekly routine with temporary one-day context. "
        "Use this for routine/day-type/work-location/recommended-wake questions. Resolve "
        "relative dates using the current local runtime date before calling this tool."
    ),
    properties={
        "date": {
            "type": "string",
            "description": "Date in YYYY-MM-DD format."
        }
    },
    required=["date"]
)


SET_WORK_LOCATION_TOOL = function_tool(
    name="set_work_location",
    description=(
        "Set whether Oliver is working from home or going into the office on one specific "
        "workday. This is a temporary one-day context update and MUST NOT change his normal "
        "weekly routine or persistent memory. It also synchronises the routine-derived wake "
        "alarm unless Oliver already has a manual or explicitly disabled wake alarm for that "
        "date. Resolve relative dates using the current local runtime date."
    ),
    properties={
        "date": {
            "type": "string",
            "description": "The specific work date in YYYY-MM-DD format."
        },
        "location": {
            "type": "string",
            "enum": ["home", "office"],
            "description": "'home' means WFH; 'office' means travelling into work."
        }
    },
    required=[
        "date",
        "location"
    ]
)


# --------------------------------------------------
# Alarm tools
# --------------------------------------------------

GET_WAKE_ALARM_TOOL = function_tool(
    name="get_wake_alarm",
    description=(
        "Read Mairon's local wake-alarm record for one specific date. Use this when Oliver "
        "asks whether he has a wake alarm, what time he is getting up, or when a workflow "
        "needs the ACTUAL alarm rather than merely a recommended routine wake time. The "
        "record may exist but be disabled. This is private local data."
    ),
    properties={
        "date": {
            "type": "string",
            "description": "Date in YYYY-MM-DD format."
        }
    },
    required=["date"]
)


SET_WAKE_ALARM_TOOL = function_tool(
    name="set_wake_alarm",
    description=(
        "Create or update Oliver's explicit local wake-alarm record for one specific date. "
        "Use this when Oliver directly asks to be woken at a particular time, set an alarm, "
        "or change an existing wake alarm. This is a MANUAL override and therefore takes "
        "priority over routine-derived wake recommendations. There can only be one wake alarm "
        "per date. IMPORTANT: the current development build stores the alarm persistently but "
        "does not yet have speaker/OS playback attached, so do not claim it will audibly ring."
    ),
    properties={
        "date": {
            "type": "string",
            "description": "Alarm date in YYYY-MM-DD format."
        },
        "time": {
            "type": "string",
            "description": "Wake time in 24-hour HH:MM format."
        },
    },
    required=[
        "date",
        "time"
    ]
)


DISABLE_WAKE_ALARM_TOOL = function_tool(
    name="disable_wake_alarm",
    description=(
        "Disable Oliver's wake-alarm record for one specific date. Use this when he says "
        "not to wake him, cancel tomorrow's wake alarm, or otherwise explicitly disables it. "
        "Routine processing must not silently re-enable an explicitly disabled alarm."
    ),
    properties={
        "date": {
            "type": "string",
            "description": "Alarm date in YYYY-MM-DD format."
        }
    },
    required=["date"]
)


GET_UPCOMING_ALARMS_TOOL = function_tool(
    name="get_upcoming_alarms",
    description=(
        "List Mairon's enabled local wake-alarm records for the upcoming period. "
        "Use this when Oliver asks what alarms he has coming up."
    ),
    properties={
        "days": {
            "type": "integer",
            "minimum": 1,
            "maximum": 90,
            "description": "Number of upcoming days to inspect."
        }
    },
    required=["days"]
)


# --------------------------------------------------
# Public web
# --------------------------------------------------

WEB_SEARCH_TOOL = function_tool(
    name="web_search",
    description=(
        "Search the live public internet for current or externally verifiable information. "
        "Use this for recent events, news, current information, documentation, software "
        "versions, product announcements, and other changing public facts. Do not use web "
        "search for Oliver's private email, calendar, routine, alarms, memory, routes, or "
        "other information available through a dedicated private tool. Never include passwords, "
        "API keys, private addresses, private email contents, or secret information in a query."
    ),
    properties={
        "query": {
            "type": "string",
            "description": "Concise public web search query."
        },
        "topic": {
            "type": "string",
            "enum": ["general", "news", "finance"],
            "description": "Search category."
        },
        "time_range": {
            "type": "string",
            "enum": ["none", "day", "week", "month", "year"],
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
        "Use this after web_search when the actual source needs to be examined. Prefer "
        "authoritative sources and do not use this tool to access private account data."
    ),
    properties={
        "url": {
            "type": "string",
            "description": "Complete public HTTP or HTTPS URL."
        },
        "focus": {
            "type": "string",
            "description": "Specific information to focus on; empty string for general read."
        }
    },
    required=[
        "url",
        "focus"
    ]
)


# --------------------------------------------------
# Persistent memory
# --------------------------------------------------

SAVE_MEMORY_TOOL = function_tool(
    name="save_memory",
    description=(
        "Save information into Mairon's persistent local memory. Only use this when Oliver "
        "explicitly asks Mairon to remember, save, or store something. Do NOT use persistent "
        "memory for temporary daily context or alarms; use the dedicated tools instead."
    ),
    properties={
        "memory": {
            "type": "string",
            "description": "The concise information Oliver explicitly requested to remember."
        }
    },
    required=["memory"]
)


SEARCH_MEMORY_TOOL = function_tool(
    name="search_memory",
    description=(
        "Search Mairon's persistent local memory for information Oliver previously asked "
        "Mairon to remember. Do not use persistent memory as a substitute for routine, alarms, "
        "Gmail, Calendar, or another dedicated private source."
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
        "The deletion system is conservative and will not delete anything if multiple "
        "memories ambiguously match."
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
    GET_ROUTINE_CONTEXT_TOOL,
    SET_WORK_LOCATION_TOOL,
    GET_WAKE_ALARM_TOOL,
    SET_WAKE_ALARM_TOOL,
    DISABLE_WAKE_ALARM_TOOL,
    GET_UPCOMING_ALARMS_TOOL,
    WEB_SEARCH_TOOL,
    WEB_READ_TOOL,
    SAVE_MEMORY_TOOL,
    SEARCH_MEMORY_TOOL,
    LIST_MEMORIES_TOOL,
    DELETE_MEMORY_TOOL,
]


# Cloud models deliberately receive only public-information tools.
# Private routine/alarm/Gmail/Calendar/memory/system data stays local.
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
        app_name = arguments.get("app_name")
        if not app_name:
            return {"success": False, "message": "No application name was provided."}
        return launch_application(app_name)

    if tool_name == "get_weather":
        location = arguments.get("location")
        if not location:
            return {"success": False, "message": "No weather location was provided."}
        return get_weather(location)

    if tool_name == "get_route":
        origin = arguments.get("origin")
        destination = arguments.get("destination")
        mode = arguments.get("mode")

        if not origin or not destination or not mode:
            return {
                "success": False,
                "message": "Route request is missing an origin, destination, or travel mode."
            }

        if origin.lower().strip() == "home" and mode == "transit":
            mode = "park_and_ride"

        via = arguments.get("via")

        return get_route(
            origin=origin,
            destination=destination,
            mode=mode,
            via=via
        )

    if tool_name == "get_calendar_events":
        return get_calendar_events(arguments.get("period", "today"))

    if tool_name == "get_next_calendar_event":
        return get_next_calendar_event()

    if tool_name == "get_recent_emails":
        return get_recent_emails(
            days=arguments.get("days", 7),
            max_results=arguments.get("max_results", 10),
            unread_only=arguments.get("unread_only", False)
        )

    if tool_name == "find_emails":
        return find_emails(
            search_text=arguments.get("search_text", ""),
            days=arguments.get("days", 30),
            unread_only=arguments.get("unread_only", False),
            max_results=arguments.get("max_results", 10)
        )

    if tool_name == "read_email":
        message_id = arguments.get("message_id")
        if not message_id:
            return {"success": False, "message": "No Gmail message ID was provided."}
        return read_email(message_id)

    if tool_name == "get_routine_context":
        date = arguments.get("date")
        if not date:
            return {"success": False, "message": "No routine context date was provided."}
        return get_routine_context(date=date)

    if tool_name == "set_work_location":
        date = arguments.get("date")
        location = arguments.get("location")
        if not date:
            return {"success": False, "message": "No work date was provided."}
        if not location:
            return {"success": False, "message": "No work location was provided."}
        return set_work_location(date=date, location=location)

    if tool_name == "get_wake_alarm":
        date = arguments.get("date")
        if not date:
            return {"success": False, "message": "No alarm date was provided."}
        return get_alarm_for_date(date=date)

    if tool_name == "set_wake_alarm":
        date = arguments.get("date")
        time = arguments.get("time")

        if not date or not time:
            return {
                "success": False,
                "message": "Alarm date and time are required."
            }

        # Manual wake alarms use a neutral label. The model does not
        # control routine metadata such as "Work - Home" or
        # "Work - Office"; those labels belong only to routine-derived
        # alarms and would become stale when plans change.
        return set_alarm_for_date(
            date=date,
            time=time,
            label="Wake up",
            source="manual"
        )

    if tool_name == "disable_wake_alarm":
        date = arguments.get("date")
        if not date:
            return {"success": False, "message": "No alarm date was provided."}
        return disable_alarm_for_date(date=date)

    if tool_name == "get_upcoming_alarms":
        return get_upcoming_alarms(
            days=arguments.get("days", 7)
        )

    if tool_name == "web_search":
        query = arguments.get("query")
        if not query:
            return {"success": False, "message": "No web search query was provided."}

        topic = arguments.get("topic", "general")
        time_range = arguments.get("time_range", "none")
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
            return {"success": False, "message": "No webpage URL was provided."}

        focus = arguments.get("focus", "")
        if isinstance(focus, str):
            focus = focus.strip()
        if not focus:
            focus = None

        return web_read(url=url, focus=focus)

    if tool_name == "save_memory":
        memory = arguments.get("memory")
        if not memory:
            return {"success": False, "message": "No memory content was provided."}
        return save_memory(memory)

    if tool_name == "search_memory":
        query = arguments.get("query")
        if not query:
            return {"success": False, "message": "No memory search query was provided."}
        return search_memories(query)

    if tool_name == "list_memories":
        return list_memories()

    if tool_name == "delete_memory":
        query = arguments.get("query")
        if not query:
            return {"success": False, "message": "No memory deletion query was provided."}
        return delete_memory(query)

    return {
        "success": False,
        "message": f"Unknown tool: {tool_name}"
    }
