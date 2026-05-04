from miskit.tool import Tool


class MemoryTool(Tool):
    name = "memory"
    description = "Add, list, update, and remove long-term memories in Miskit's markdown memory files."
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "list", "update", "remove"],
                "description": "Use add to save a memory, list to show memories, update to edit one, or remove to delete one.",
            },
            "category": {
                "type": "string",
                "enum": ["user", "bot", "notes"],
                "description": "Use user for user facts/preferences, bot for Miskit facts, notes for project notes.",
            },
            "text": {
                "type": "string",
                "description": "One concise memory bullet to save or use as replacement text.",
            },
            "memory_id": {
                "type": "string",
                "description": "Memory id from the list action, like user:1.",
            },
        },
        "required": ["action"],
    }

    def __init__(self, memory):
        self.memory = memory
        self.added = []

    def run(self, arguments):
        action = str(arguments.get("action", "add")).strip() or "add"
        if action == "add":
            return self._add(arguments)
        if action == "list":
            return self._list(arguments)
        if action == "update":
            return self._update(arguments)
        if action == "remove":
            return self._remove(arguments)

        return "Unknown memory action. Use add, list, update, or remove."

    def _add(self, arguments):
        category = str(arguments.get("category", "")).strip()
        text = str(arguments.get("text", "")).strip()

        if not category:
            return "Error: memory requires category."
        if not text:
            return "Error: memory requires text."

        try:
            self.memory.add(category, text)
        except ValueError as error:
            return f"Error: {error}"

        self.added.append((category, text))
        return f"Saved {category} memory: {text}"

    def _list(self, arguments):
        category = str(arguments.get("category", "")).strip() or None

        try:
            entries = self.memory.entries(category)
        except ValueError as error:
            return f"Error: {error}"

        if not entries:
            if category is None:
                return "No memories."
            return f"No {category} memories."

        lines = ["Memories:"]
        for entry in entries:
            lines.append(f"- {entry['id']} [{entry['category']}] {entry['text']}")
        return "\n".join(lines)

    def _update(self, arguments):
        memory_id = str(arguments.get("memory_id", "")).strip()
        text = str(arguments.get("text", "")).strip()

        if not memory_id:
            return "Error: memory update requires memory_id."
        if not text:
            return "Error: memory update requires text."

        try:
            self.memory.update(memory_id, text)
        except ValueError as error:
            return f"Error: {error}"

        return f"Updated memory {memory_id}: {text}"

    def _remove(self, arguments):
        memory_id = str(arguments.get("memory_id", "")).strip()
        if not memory_id:
            return "Error: memory remove requires memory_id."

        try:
            self.memory.remove(memory_id)
        except ValueError as error:
            return f"Error: {error}"

        return f"Removed memory {memory_id}."


def create_tool(config, services=None):
    services = services or {}
    memory = services.get("memory")
    if memory is None:
        raise ValueError("memory tool requires a memory service")

    return MemoryTool(memory)
