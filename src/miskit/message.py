import json


class ToolCall:
    def __init__(self, id, name, arguments):
        if not isinstance(arguments, dict):
            raise TypeError("tool arguments must be a dictionary")

        self.id = id
        self.name = name
        self.arguments = arguments


class Message:
    def __init__(self, role, content="", tool_calls=None, tool_call_id=None, name=None, usage=None):
        if role not in ("system", "user", "assistant", "tool"):
            raise ValueError("role must be system, user, assistant, or tool")

        if not isinstance(content, str):
            raise TypeError("content must be text")

        if usage is not None and not isinstance(usage, dict):
            raise TypeError("usage must be a dictionary")

        self.role = role
        self.content = content
        self.tool_calls = tool_calls or []
        self.tool_call_id = tool_call_id
        self.name = name
        self.usage = usage or {}
