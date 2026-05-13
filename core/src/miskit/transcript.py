import json

from miskit.message import Message
from miskit.message import ToolCall


def message_data(message):
    data = {
        "role": message.role,
        "content": message.content,
        "tool_calls": [tool_call_data(tool_call) for tool_call in message.tool_calls],
        "tool_call_id": message.tool_call_id,
        "name": message.name,
    }
    if message.usage:
        data["usage"] = message.usage
    return data


def message_from_data(data):
    return Message(
        data.get("role"),
        data.get("content", ""),
        tool_calls=[tool_call_from_data(item) for item in data.get("tool_calls", [])],
        tool_call_id=data.get("tool_call_id"),
        name=data.get("name"),
        usage=data.get("usage"),
    )


def tool_call_data(tool_call):
    return {
        "id": tool_call.id,
        "name": tool_call.name,
        "arguments": tool_call.arguments,
    }


def tool_call_from_data(data):
    return ToolCall(
        data.get("id"),
        data.get("name"),
        data.get("arguments", {}),
    )


def format_message(message):
    label = message.role
    if message.name:
        label = f"{label} {message.name}"

    content = message.content or "(no text)"
    if message.tool_calls:
        calls = [format_tool_call(tool_call) for tool_call in message.tool_calls]
        content = f"{content}\nTool calls: {', '.join(calls)}"

    return f"{label}: {content}"


def format_tool_call(tool_call):
    return f"{tool_call.name}({json.dumps(tool_call.arguments)})"


def log_message_data(message):
    data = {
        "role": message.role,
        "content": message.content,
    }
    if message.tool_calls:
        data["tool_calls"] = [
            {"name": tool_call.name, "arguments": tool_call.arguments}
            for tool_call in message.tool_calls
        ]
    if message.name:
        data["name"] = message.name
    return data
