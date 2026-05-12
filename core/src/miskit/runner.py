import asyncio
from datetime import datetime

from miskit.conversation import Conversation
from miskit.message import Message

# Default cap on how many times the model may answer with tool calls in one user turn (each time: run tools, then ask again).
DEFAULT_MAX_TOOL_ROUNDS = 20


def runtime_metadata():
    now = datetime.now().astimezone()
    offset = now.strftime("%z")
    offset = f"{offset[:3]}:{offset[3:]}" if len(offset) == 5 else offset
    timezone = now.tzname() or "local time"
    current_time = f"{now.strftime('%Y-%m-%d %H:%M (%A)')} {timezone}, UTC{offset}"
    return f"[Runtime Metadata]\nCurrent Time: {current_time}\n[/Runtime Metadata]"


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
    ):
        self.model = model
        self.memory = memory
        self.history = history
        self.tools = tools or []
        self.compactor = compactor
        self.dream = dream
        self.max_tool_rounds = max_tool_rounds
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
            messages = self._messages_with_active_user_message(stored_message, user_message)
            message = await self.run_turn(messages, log_tools=True)
            self._last_prompt_tokens = message.usage.get("prompt_tokens")
            self.conversation.add(message)
            self.log_conversation()
            if archived:
                self.request_dream()
            return message

    async def compact_if_needed(self):
        if self.compactor is None or self.history is None:
            return False

        if not self.compactor.should_compact(self.conversation.messages, self._last_prompt_tokens):
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
        chunks = self.compactor.split_for_summary(messages)
        summary = ""
        for chunk in chunks:
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

    def run_tool(self, tool_call):
        for tool in self.tools:
            if tool.name == tool_call.name:
                content = tool.run(tool_call.arguments)
                return Message("tool", content, tool_call_id=tool_call.id, name=tool_call.name)

        return Message("tool", f"Unknown tool: {tool_call.name}", tool_call_id=tool_call.id, name=tool_call.name)
