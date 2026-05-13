from miskit.message import Message


DEFAULT_MAX_TOOL_OUTPUT_CHARS = 20_000


class ToolRunner:
    def __init__(self, tools=None, truncation_store=None, max_output_chars=DEFAULT_MAX_TOOL_OUTPUT_CHARS):
        self.tools = list(tools or [])
        self.truncation_store = truncation_store
        self.max_output_chars = max_output_chars

    def run(self, tool_call):
        tool = self._find(tool_call.name)
        if tool is None:
            content = f"Unknown tool: {tool_call.name}"
        else:
            content = tool.run(tool_call.arguments)

        return Message(
            "tool",
            self._truncate(content),
            tool_call_id=tool_call.id,
            name=tool_call.name,
        )

    def _find(self, name):
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    def _truncate(self, content):
        if not isinstance(content, str):
            content = str(content)

        limit = self.max_output_chars
        if limit <= 0 or len(content) <= limit:
            return content

        if self.truncation_store is None:
            return content[:limit] + f"\n\n[output truncated at {limit} characters]"

        store_id = self.truncation_store.save(content)
        return (
            content[:limit]
            + f"\n\n[output truncated at {limit} characters, id: {store_id}"
            + f" -- use read_more(id=\"{store_id}\", offset={limit}) to retrieve the rest]"
        )
