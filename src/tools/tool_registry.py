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
    }
]


def execute_tool(tool_name, arguments=None):
    arguments = arguments or {}

    if tool_name == "get_system_info":
        return get_system_info()

    if tool_name == "launch_application":
        return launch_application(arguments["app_name"])

    raise ValueError(f"Unknown tool: {tool_name}")