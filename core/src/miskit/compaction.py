import json

from miskit.message import Message


class Compactor:
    def __init__(self, context_tokens=8000, compact_at=0.5, keep_recent=10):
        self.context_tokens = context_tokens
        self.compact_at = compact_at
        self.keep_recent = keep_recent

    @classmethod
    def from_config(cls, config):
        return cls(
            context_tokens=config.get("tokens", 8000),
            compact_at=config.get("compactAt", 0.5),
            keep_recent=config.get("keepRecent", 10),
        )

    def should_compact(self, messages, prompt_tokens=None):
        if len(messages) <= self.keep_recent:
            return False

        if prompt_tokens is None:
            prompt_tokens = self.estimate_tokens(messages)

        return prompt_tokens >= self.context_tokens * self.compact_at

    def estimate_tokens(self, messages):
        total = 0
        for message in messages:
            total += self.estimate_text(message.role)
            total += self.estimate_text(message.content)
            if message.name:
                total += self.estimate_text(message.name)
            for tool_call in message.tool_calls:
                total += self.estimate_text(tool_call.name)
                total += self.estimate_text(json.dumps(tool_call.arguments))
        return total

    def estimate_text(self, text):
        return max(1, len(text) // 3)

    def split(self, messages):
        messages = list(messages)
        if len(messages) <= self.keep_recent:
            return [], messages

        start = max(0, len(messages) - self.keep_recent)
        if start == len(messages):
            return messages, []

        while start > 0 and not self._safe_start(messages[start]):
            start -= 1

        return messages[:start], messages[start:]

    def _safe_start(self, message):
        if message.role == "tool":
            return False
        if message.role == "assistant" and message.tool_calls:
            return False
        return True

    def summary_prompt(self, messages):
        text = "\n\n".join(self.format_message(message) for message in messages)
        return (
            "Summarize this conversation so Miskit can continue it later.\n\n"
            "Do not answer the conversation. Only write a compact summary for future turns.\n\n"
            "Include important names, facts, decisions, preferences, open tasks, "
            "and any details the user may expect Miskit to remember. Keep it concise.\n\n"
            f"{text}"
        )

    def summary_message(self, summary):
        content = (
            "# Previous Conversation Summary\n\n"
            "This is a compact summary of an archived conversation. Use it as background context, "
            "but prefer newer messages when details conflict.\n\n"
            f"{summary}"
        )
        return Message("system", content)

    def format_message(self, message):
        label = message.role
        if message.name:
            label = f"{label} {message.name}"
        content = message.content or "(no text)"
        if message.tool_calls:
            calls = []
            for tool_call in message.tool_calls:
                calls.append(f"{tool_call.name}({json.dumps(tool_call.arguments)})")
            content = f"{content}\nTool calls: {', '.join(calls)}"
        return f"{label}: {content}"
