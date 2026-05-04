from miskit.heartbeat import HeartbeatTasks
from miskit.tool import Tool


class HeartbeatTool(Tool):
    name = "heartbeat"
    description = "Add, list, complete, and remove tasks in Miskit's heartbeat task file."
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "list", "complete", "remove"],
                "description": "Use add to create a task, list to show tasks, complete to mark one done, or remove to delete one.",
            },
            "text": {
                "type": "string",
                "description": "Task text to add.",
            },
            "task_id": {
                "type": "integer",
                "description": "Task number from the list action.",
            },
        },
        "required": ["action"],
    }

    def __init__(self, tasks):
        self.tasks = tasks

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

        return "Unknown heartbeat action. Use add, list, complete, or remove."

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


def create_tool(config, services=None):
    services = services or {}
    heartbeat_path = services.get("heartbeat_path")
    if heartbeat_path is None:
        raise ValueError("heartbeat tool requires a heartbeat path")

    return HeartbeatTool(HeartbeatTasks(heartbeat_path))
