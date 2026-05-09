class ToolCall:
    def __init__(self, id, name, arguments):
        if not isinstance(arguments, dict):
            raise TypeError("tool arguments must be a dictionary")

        self.id = id
        self.name = name
        self.arguments = arguments


def text_part(text):
    return {"type": "text", "text": str(text or "")}


def image_part(path, mime_type):
    return {"type": "image", "path": str(path), "mime_type": str(mime_type or "")}


class Message:
    def __init__(self, role, content="", tool_calls=None, tool_call_id=None, name=None, usage=None, stored_content=None):
        if role not in ("system", "user", "assistant", "tool"):
            raise ValueError("role must be system, user, assistant, or tool")

        if not isinstance(content, (str, list)):
            raise TypeError("content must be text or a list of content parts")

        if stored_content is not None and not isinstance(stored_content, (str, list)):
            raise TypeError("stored_content must be text or a list of content parts")

        if usage is not None and not isinstance(usage, dict):
            raise TypeError("usage must be a dictionary")

        self.role = role
        self.content = content
        self.tool_calls = tool_calls or []
        self.tool_call_id = tool_call_id
        self.name = name
        self.usage = usage or {}
        self.stored_content = stored_content

    @property
    def text(self):
        if isinstance(self.content, str):
            return self.content

        lines = []
        for part in self.content:
            if part["type"] == "text":
                text = part["text"].strip()
                if text:
                    lines.append(text)
            elif part["type"] == "image":
                lines.append("[Image]")
        return "\n".join(lines)

    @property
    def parts(self):
        if isinstance(self.content, str):
            return [text_part(self.content)] if self.content else []
        return [dict(part) for part in self.content]

    def with_prepended_text(self, text):
        if not text:
            return Message(self.role, self.content)
        if isinstance(self.content, str):
            content = f"{text}{self.content}" if self.content else text
        else:
            content = [text_part(text)] + [dict(p) for p in self.content]
        return Message(self.role, content)

    def storage_message(self):
        if self.stored_content is None:
            return self

        return Message(
            self.role,
            self.stored_content,
            tool_calls=self.tool_calls,
            tool_call_id=self.tool_call_id,
            name=self.name,
            usage=self.usage,
        )
