from miskit.heartbeat import HeartbeatLog, HeartbeatTasks
from miskit.tool import Tool


def _truncate(text, limit):
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[output truncated at {limit} characters]"


class HeartbeatTool(Tool):
    name = "heartbeat"
    description = "Add, list, complete, and remove tasks in Miskit's heartbeat task file. Use history to view past heartbeat results."
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "list", "complete", "remove", "history"],
                "description": "Use add to create a task, list to show tasks, complete to mark one done, remove to delete one, or history to view past heartbeat results.",
            },
            "text": {
                "type": "string",
                "description": "Task text to add.",
            },
            "task_id": {
                "type": "integer",
                "description": "Task number from the list action.",
            },
            "limit": {
                "type": "integer",
                "description": "Number of past heartbeats to show (default 10). Only used with the history action.",
            },
            "timestamp": {
                "type": "string",
                "description": "For history: show the full turn details for the heartbeat with this timestamp.",
            },
        },
        "required": ["action"],
    }

    def __init__(self, tasks, log=None, max_output_chars=20_000):
        self.tasks = tasks
        self.log = log
        self.max_output_chars = max_output_chars

    def run(self, arguments):
        action = str(arguments.get("action", "")).strip()

        if action == "add":
            return self._add(arguments)
        if action == "list":
            return self._list()
        if action == "complete":
            return self._complete(arguments)
        if action == "remove":
            return self._remove(arguments)
        if action == "history":
            return self._history(arguments)

        return "Unknown heartbeat action. Use add, list, complete, remove, or history."

    def _add(self, arguments):
        text = str(arguments.get("text", "")).strip()
        if not text:
            return "Error: heartbeat add requires text."

        try:
            self.tasks.add(text)
        except ValueError as error:
            return f"Error: {error}"

        return f"Added heartbeat task: {text}"

    def _list(self):
        tasks = self.tasks.list()
        if not tasks:
            return "No heartbeat tasks."

        lines = ["Heartbeat tasks:"]
        for index, task in enumerate(tasks, start=1):
            marker = "x" if task["done"] else " "
            lines.append(f"{index}. [{marker}] {task['text']}")
        return "\n".join(lines)

    def _complete(self, arguments):
        task_id = arguments.get("task_id")
        if task_id is None:
            return "Error: heartbeat complete requires task_id."

        try:
            self.tasks.complete(task_id)
        except ValueError as error:
            return f"Error: {error}"

        return f"Completed heartbeat task {task_id}."

    def _remove(self, arguments):
        task_id = arguments.get("task_id")
        if task_id is None:
            return "Error: heartbeat remove requires task_id."

        try:
            self.tasks.remove(task_id)
        except ValueError as error:
            return f"Error: {error}"

        return f"Removed heartbeat task {task_id}."

    def _history(self, arguments):
        if self.log is None:
            return "No heartbeat log available."

        timestamp = str(arguments.get("timestamp", "")).strip()
        if timestamp:
            return self._history_detail(timestamp)

        limit = arguments.get("limit", 10)
        entries = self.log.read(limit=limit)
        if not entries:
            return "No past heartbeats recorded."

        lines = [f"Last {len(entries)} heartbeat(s):"]
        for entry in entries:
            status = "quiet" if entry.get("quiet") else "responded"
            lines.append(f"\n[{entry['timestamp']}] ({status})")
            for message in reversed(entry.get("messages", [])):
                if message.get("role") == "assistant":
                    lines.append(f"  {message.get('content', '').strip()}")
                    break
        return "\n".join(lines)

    def _history_detail(self, timestamp):
        entry = self.log.read_by_timestamp(timestamp)
        if entry is None:
            return f"No heartbeat found with timestamp: {timestamp}"

        status = "quiet" if entry.get("quiet") else "responded"
        lines = [
            f"Heartbeat: {entry['timestamp']} ({status})",
        ]
        for message in entry.get("messages", []):
            role = message.get("role", "unknown")
            if message.get("name"):
                role = f"{role} {message['name']}"
            lines.append(f"\n{role}: {message.get('content', '')}")
            for tc in message.get("tool_calls", []):
                lines.append(f"  -> tool call: {tc['name']}({tc['arguments']})")
        return _truncate("\n".join(lines), self.max_output_chars)


def create_tool(config, services=None):
    services = services or {}
    heartbeat_path = services.get("heartbeat_path")
    if heartbeat_path is None:
        raise ValueError("heartbeat tool requires a heartbeat path")

    heartbeat_log = services.get("heartbeat_log")
    context_tokens = services.get("context_tokens", 8000)
    return HeartbeatTool(HeartbeatTasks(heartbeat_path), log=heartbeat_log, max_output_chars=context_tokens * 5 // 2)
