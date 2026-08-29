from memory.memory_store import (
    delete_memory,
    list_memories,
    save_memory,
    search_memories,
)
from tools.desktop_tools import launch_application
from tools.system_tools import get_system_info


TOOLS = [
    {
        "type": "function",
        "name": "get_system_info",
        "description": (
            "Get factual information about the computer currently running Mairon, "
            "including its operating system, OS version, computer name, and architecture. "
            "Use this when the user asks about the current computer or system."
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

    if tool_name == "save_memory":
        return save_memory(arguments["memory"])

    if tool_name == "search_memory":
        return search_memories(arguments["query"])

    if tool_name == "list_memories":
        return list_memories()

    if tool_name == "delete_memory":
        return delete_memory(arguments["query"])

    raise ValueError(f"Unknown tool: {tool_name}")