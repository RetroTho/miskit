import asyncio
from datetime import datetime

from miskit.conversation import Conversation
from miskit.message import Message

# Default cap on how many times the model may answer with tool calls in one user turn (each time: run tools, then ask again).
DEFAULT_MAX_TOOL_ROUNDS = 20
_CONTEXT_USAGE_LIMIT = 0.8


def runtime_metadata():
    now = datetime.now().astimezone()
    offset = now.strftime("%z")
    offset = f"{offset[:3]}:{offset[3:]}" if len(offset) == 5 else offset
    timezone = now.tzname() or "local time"
    current_time = f"{now.strftime('%Y-%m-%d %H:%M (%A)')} {timezone}, UTC{offset}"
    return f"[Runtime Metadata]\nCurrent Time: {current_time}\n[/Runtime Metadata]"


DEFAULT_MAX_TOOL_OUTPUT_CHARS = 20_000


class Runner:
    def __init__(
        self,
        model,
        conversation=None,
        memory=None,
        history=None,
        tools=None,
        compactor=None,
        dream=None,
        max_tool_rounds=DEFAULT_MAX_TOOL_ROUNDS,
        truncation_store=None,
        max_tool_output_chars=DEFAULT_MAX_TOOL_OUTPUT_CHARS,
    ):
        self.model = model
        self.memory = memory
        self.history = history
        self.tools = tools or []
        self.compactor = compactor
        self.dream = dream
        self.max_tool_rounds = max_tool_rounds
        self.truncation_store = truncation_store
        self.max_tool_output_chars = max_tool_output_chars
        self._last_prompt_tokens = None
        self._dream_requested = False
        self._dream_task = None

        if conversation is None:
            conversation = Conversation()
            if history is not None:
                for message in history.read():
                    conversation.add(message)

        self.conversation = conversation
        self._logged_count = len(self.conversation.messages)
        self._chat_lock = asyncio.Lock()

    async def run_turn(self, messages, log_tools=False):
        messages = self._messages_for_model(messages)
        turn_start = len(self.conversation.messages) - 1 if log_tools else 0

        # A model may chain several tool rounds before answering.
        for _ in range(self.max_tool_rounds):
            message = await self.complete(messages)

            if message.role != "assistant":
                raise ValueError("model must return an assistant message")

            if not message.tool_calls:
                return message

            if log_tools:
                self.conversation.add(message)

            messages = list(messages) + [message]
            for tool_call in message.tool_calls:
                tool_result = self.run_tool(tool_call)
                messages.append(tool_result)
                if log_tools:
                    self.conversation.add(tool_result)

            if log_tools and self._context_nearly_full(messages):
                if self.compactor is not None and self.history is not None:
                    await self._compact_for_overflow(turn_start)
                    messages = self._messages_for_model(list(self.conversation.messages))
                else:
                    return Message(
                        "assistant",
                        "I need to stop here because the conversation context is nearly full. "
                        "Please start a new conversation to continue.",
                    )

        raise ValueError(
            f"model kept asking for tools after {self.max_tool_rounds} rounds "
            "(increase context.maxToolRounds in config.json if you need more)"
        )

    def _messages_for_model(self, messages):
        messages = list(messages)

        if self.memory is not None:
            system_prompt = self.memory.system_prompt()
            if system_prompt:
                messages = [Message("system", system_prompt)] + messages

        metadata = runtime_metadata()
        for index in range(len(messages) - 1, -1, -1):
            message = messages[index]
            if message.role == "user":
                messages[index] = message.with_prepended_text(f"{metadata}\n\n")
                return messages

        messages.append(Message("user", metadata))
        return messages

    async def chat(self, content):
        async with self._chat_lock:
            user_message = self._user_message(content)
            stored_message = user_message.storage_message()
            self.conversation.add(stored_message)
            archived = await self.compact_if_needed()
            snapshot = len(self.conversation.messages)
            messages = self._messages_with_active_user_message(stored_message, user_message)
            try:
                message = await self.run_turn(messages, log_tools=True)
            except Exception:
                self.rollback_conversation(snapshot)
                raise
            self._last_prompt_tokens = message.usage.get("prompt_tokens")
            self.conversation.add(message)
            self.log_conversation()
            if archived:
                self.request_dream()
            return message

    def _messages_for_compaction_check(self):
        messages = list(self.conversation.messages)
        if self.memory is not None:
            system_prompt = self.memory.system_prompt()
            if system_prompt:
                messages = [Message("system", system_prompt)] + messages
        return messages

    async def compact_if_needed(self):
        if self.compactor is None or self.history is None:
            return False

        messages = self._messages_for_compaction_check()
        if not self.compactor.should_compact(messages, self._last_prompt_tokens):
            return False

        old_messages, recent_messages = self.compactor.split(self.conversation.messages)
        if not old_messages:
            return False

        summary = await self.summarize(old_messages)
        self.history.archive()
        self.conversation.messages = [self.compactor.summary_message(summary)] + recent_messages
        self.history.write(self.conversation.messages)
        self._logged_count = len(self.conversation.messages)
        self._last_prompt_tokens = None
        return True

    def request_dream(self):
        if self.dream is None:
            return

        self._dream_requested = True
        if self._dream_task is None or self._dream_task.done():
            self._dream_task = asyncio.create_task(self.run_dream_requests())

    async def run_dream_requests(self):
        while self._dream_requested:
            self._dream_requested = False
            await self.dream.run_once()

    async def summarize(self, messages):
        summary = ""
        remaining = list(messages)
        while remaining:
            chunks = self.compactor.split_for_summary(remaining, reserved_chars=len(summary))
            chunk = chunks[0]
            remaining = remaining[len(chunk):]
            prompt = self.compactor.summary_prompt(chunk, prior_summary=summary)
            reply = await self.model.complete([Message("user", prompt)])
            if reply.role != "assistant":
                raise ValueError("model must return an assistant message")
            summary = reply.content
        return summary

    def log_conversation(self):
        if self.history is not None:
            for message in self.conversation.messages[self._logged_count:]:
                self.history.log(message)
            self._logged_count = len(self.conversation.messages)

    def rollback_conversation(self, message_count):
        self.conversation.messages = self.conversation.messages[:message_count]
        self._logged_count = message_count
        if self.history is not None:
            self.history.write(self.conversation.messages)

    async def complete(self, messages):
        if not self.tools:
            return await self.model.complete(messages)

        return await self.model.complete(messages, self.tools)

    def _user_message(self, content):
        if isinstance(content, Message):
            if content.role != "user":
                raise ValueError("chat messages must have role='user'")
            return content
        return Message("user", content)

    def _messages_with_active_user_message(self, stored_message, active_message):
        messages = list(self.conversation.messages)
        for index in range(len(messages) - 1, -1, -1):
            if messages[index] is stored_message:
                messages[index] = active_message
                break
        return messages

    async def _compact_for_overflow(self, turn_start):
        prior = self.conversation.messages[:turn_start]
        current_turn = self.conversation.messages[turn_start:]
        if not prior:
            return
        old_messages, recent = self.compactor.split(prior)
        if not old_messages:
            return
        summary = await self.summarize(old_messages)
        self.history.archive()
        self.conversation.messages = [self.compactor.summary_message(summary)] + recent + current_turn
        self.history.write(self.conversation.messages)
        self._logged_count = len(self.conversation.messages)
        self._last_prompt_tokens = None

    def _context_nearly_full(self, messages):
        if self.compactor is None:
            return False
        tokens = self.compactor.estimate_tokens(messages)
        return tokens >= self.compactor.context_tokens * _CONTEXT_USAGE_LIMIT

    def run_tool(self, tool_call):
        for tool in self.tools:
            if tool.name == tool_call.name:
                content = tool.run(tool_call.arguments)
                content = self._truncate_output(content)
                return Message("tool", content, tool_call_id=tool_call.id, name=tool_call.name)

        return Message("tool", f"Unknown tool: {tool_call.name}", tool_call_id=tool_call.id, name=tool_call.name)

    def _truncate_output(self, content):
        if not isinstance(content, str):
            content = str(content)
        limit = self.max_tool_output_chars
        if limit <= 0 or len(content) <= limit:
            return content
        if self.truncation_store is not None:
            store_id = self.truncation_store.save(content)
            return (
                content[:limit] +
                f"\n\n[output truncated at {limit} characters, id: {store_id}"
                f" -- use read_more(id=\"{store_id}\", offset={limit}) to retrieve the rest]"
            )
        return content[:limit] + f"\n\n[output truncated at {limit} characters]"
