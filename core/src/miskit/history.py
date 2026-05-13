import json
from datetime import datetime
from pathlib import Path

from miskit.message import Message
from miskit.message import ToolCall


class History:
    session_file = "session.jsonl"

    def __init__(self, folder):
        self.folder = Path(folder)

    def path(self):
        return self.folder / self.session_file

    def setup(self):
        self.folder.mkdir(parents=True, exist_ok=True)

        path = self.path()
        if not path.exists():
            path.write_text("", encoding="utf-8")

    def log(self, message):
        self.setup()
        with self.path().open("a", encoding="utf-8") as file:
            self.write_message(file, message)

    def read(self):
        self.setup()
        messages = []

        lines = self.path().read_text(encoding="utf-8").splitlines()
        for line_number, line in enumerate(lines, start=1):
            if line:
                try:
                    data = json.loads(line)
                    messages.append(self.message_from_data(data))
                except (json.JSONDecodeError, TypeError, ValueError) as error:
                    messages.append(Message(
                        "system",
                        f"[Could not read history line {line_number}: {error}]\n{line}",
                    ))

        return messages

    def archive_path(self):
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S-%f")
        return self.folder / "archive" / f"session-{timestamp}.jsonl"

    def archive(self):
        self.setup()
        archive_path = self.archive_path()
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        self.path().replace(archive_path)
        self.path().write_text("", encoding="utf-8")
        return archive_path

    def write(self, messages):
        self.setup()
        with self.path().open("w", encoding="utf-8") as file:
            for message in messages:
                self.write_message(file, message)

    def write_message(self, file, message):
        file.write(json.dumps(self.message_data(message)) + "\n")

    def message_data(self, message):
        data = {
            "role": message.role,
            "content": message.content,
            "tool_calls": [self.tool_call_data(tool_call) for tool_call in message.tool_calls],
            "tool_call_id": message.tool_call_id,
            "name": message.name,
        }
        if message.usage:
            data["usage"] = message.usage
        return data

    def message_from_data(self, data):
        if not isinstance(data, dict):
            raise ValueError("history entry must be a JSON object")

        tool_calls = []
        raw_tool_calls = data.get("tool_calls", [])
        if not isinstance(raw_tool_calls, list):
            raw_tool_calls = []
        for tool_call in raw_tool_calls:
            if not isinstance(tool_call, dict):
                continue
            tool_calls.append(ToolCall(
                tool_call.get("id"),
                tool_call.get("name"),
                tool_call.get("arguments", {}),
            ))

        return Message(
            data.get("role"),
            data.get("content", ""),
            tool_calls=tool_calls,
            tool_call_id=data.get("tool_call_id"),
            name=data.get("name"),
            usage=data.get("usage"),
        )

    def tool_call_data(self, tool_call):
        return {
            "id": tool_call.id,
            "name": tool_call.name,
            "arguments": tool_call.arguments,
        }
