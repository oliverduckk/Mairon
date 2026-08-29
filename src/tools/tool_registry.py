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
    }
]


def execute_tool(tool_name, arguments=None):
    if tool_name == "get_system_info":
        return get_system_info()

    raise ValueError(f"Unknown tool: {tool_name}")