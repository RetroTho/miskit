import asyncio
import json
from datetime import datetime

from miskit.conversation import Conversation
from miskit.message import Message
from miskit.message import text_part

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
        if (truncation_store is not None and
                not self._has_read_more_tool(self.tools)):
            raise ValueError("read_more tool is required when tool output truncation is enabled")
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

        # Pre-flight: check context size before the first model call.
        if log_tools and self._context_nearly_full(messages):
            if self.compactor is not None and self.history is not None:
                await self._compact_for_overflow(turn_start)
                messages = self._messages_for_model(list(self.conversation.messages))
            if self._context_nearly_full(messages):
                return Message(
                    "assistant",
                    "I need to stop here because the conversation context is nearly full. "
                    "Please start a new conversation to continue.",
                )

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
                    if self._context_nearly_full(messages):
                        return Message(
                            "assistant",
                            "I need to stop here because the conversation context is nearly full. "
                            "Please start a new conversation to continue.",
                        )
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
        messages = self._normalize_messages(messages)

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
            snapshot = list(self.conversation.messages)
            logged_count = self._logged_count
            user_message = self._user_message(content)
            stored_message = user_message.storage_message()
            try:
                self.conversation.add(stored_message)
                archived = await self.compact_if_needed()
                messages = self._messages_with_active_user_message(stored_message, user_message)
                message = await self.run_turn(messages, log_tools=True)
            except Exception:
                self.restore_conversation(snapshot, logged_count)
                raise
            self._last_prompt_tokens = message.usage.get("prompt_tokens")
            self.conversation.add(message)
            self.log_conversation()
            if archived:
                self.request_dream()
            return message

    def _messages_for_compaction_check(self, messages=None):
        if messages is None:
            messages = list(self.conversation.messages)
        else:
            messages = list(messages)
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

        # Phase 1: truncate tool outputs in old messages, preserving user/assistant content
        compacted_old = self.compactor.compact_messages(old_messages, store=self.truncation_store)
        candidate = self._messages_for_compaction_check(compacted_old + recent_messages)
        if not self.compactor.should_compact(candidate):
            self.history.archive()
            self.conversation.messages = compacted_old + recent_messages
            self.history.write(self.conversation.messages)
            self._logged_count = len(self.conversation.messages)
            self._last_prompt_tokens = None
            return True

        # Phase 2: still too large — save transcript then fall back to summarization
        store_id = None
        if self.truncation_store is not None:
            transcript = "\n\n".join(self.compactor.format_message(m) for m in old_messages)
            store_id = self.truncation_store.save(transcript)

        summary = await self.summarize(compacted_old)
        self.history.archive()
        self.conversation.messages = [self.compactor.summary_message(summary, store_id=store_id)] + recent_messages
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
            try:
                await self.dream.run_once()
            except Exception:
                pass

    async def summarize(self, messages):
        summary = ""
        remaining = list(messages)
        while remaining:
            chunk, remaining = self.compactor.take_for_summary(
                remaining,
                reserved_chars=len(summary),
            )
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

    def restore_conversation(self, messages, logged_count=None):
        self.conversation.messages = list(messages)
        if logged_count is None:
            self._logged_count = len(self.conversation.messages)
        else:
            self._logged_count = logged_count
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

        # Phase 1: truncate tool outputs in old messages
        compacted_old = self.compactor.compact_messages(old_messages, store=self.truncation_store)
        candidate = compacted_old + recent + current_turn
        if not self._context_nearly_full(candidate):
            self.history.archive()
            self.conversation.messages = candidate
            self.history.write(self.conversation.messages)
            self._logged_count = len(self.conversation.messages)
            self._last_prompt_tokens = None
            return

        # Phase 2: still too large — save transcript then fall back to summarization
        store_id = None
        if self.truncation_store is not None:
            transcript = "\n\n".join(self.compactor.format_message(m) for m in old_messages)
            store_id = self.truncation_store.save(transcript)

        summary = await self.summarize(compacted_old)
        self.history.archive()
        self.conversation.messages = [self.compactor.summary_message(summary, store_id=store_id)] + recent + current_turn
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
                try:
                    content = tool.run(tool_call.arguments)
                except Exception as error:
                    content = f"Tool {tool_call.name} failed: {error}"
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
        return content

    def _normalize_messages(self, messages):
        result = []
        pending_ids = []
        tool_chain_start = None

        for message in messages:
            if message.role == "tool":
                if pending_ids and message.tool_call_id in pending_ids:
                    result.append(message)
                    pending_ids.remove(message.tool_call_id)
                else:
                    if tool_chain_start is not None:
                        self._downgrade_tool_chain(result, tool_chain_start)
                        tool_chain_start = None
                        pending_ids = []
                    self._append_turn_message(result, self._tool_as_user_message(message))
                continue

            if pending_ids:
                self._downgrade_tool_chain(result, tool_chain_start)
                pending_ids = []
                tool_chain_start = None
            elif tool_chain_start is not None and message.role != "assistant":
                self._downgrade_tool_chain(result, tool_chain_start)
                tool_chain_start = None

            self._append_turn_message(result, message)

            if message.role == "assistant" and message.tool_calls:
                pending_ids = [tool_call.id for tool_call in message.tool_calls]
                tool_chain_start = len(result) - 1
            elif message.role == "assistant":
                tool_chain_start = None

        if pending_ids:
            self._downgrade_tool_chain(result, tool_chain_start)

        return result

    def _append_turn_message(self, messages, message):
        if (messages and
                message.role in ("user", "assistant") and
                messages[-1].role == message.role and
                not messages[-1].tool_calls):
            previous = messages[-1]
            content = self._joined_content(
                previous.content,
                message.content,
                role=message.role,
            )
            messages[-1] = Message(
                message.role,
                content,
                tool_calls=message.tool_calls,
                tool_call_id=message.tool_call_id,
                name=message.name or previous.name,
                usage=message.usage or previous.usage,
            )
            return

        messages.append(message)

    def _joined_content(self, left, right, role):
        if not left:
            return right
        if not right:
            return left

        if role == "assistant":
            return f"{self._content_text(left)}\n\n{self._content_text(right)}"

        if isinstance(left, str) and isinstance(right, str):
            return f"{left}\n\n{right}"

        parts = []
        parts.extend(self._content_parts(left))
        parts.append(text_part("\n\n"))
        parts.extend(self._content_parts(right))
        return parts

    def _content_parts(self, content):
        if isinstance(content, str):
            return [text_part(content)] if content else []
        return [dict(part) for part in content]

    def _content_text(self, content):
        if isinstance(content, str):
            return content
        return Message("user", content).text

    def _downgrade_tool_chain(self, messages, start):
        if start is None or start >= len(messages):
            return

        chain = messages[start:]
        del messages[start:]
        text = "\n\n".join(self._context_text(message) for message in chain)
        self._append_turn_message(messages, Message("assistant", text))

    def _tool_as_user_message(self, message):
        return Message("user", self._context_text(message))

    def _context_text(self, message):
        label = message.role
        if message.name:
            label = f"{label} {message.name}"
        content = self._content_text(message.content) if message.content else "(no text)"
        if message.tool_calls:
            calls = []
            for tool_call in message.tool_calls:
                calls.append(f"{tool_call.name}({json.dumps(tool_call.arguments)})")
            content = f"{content}\nTool calls: {', '.join(calls)}"
        if message.role == "tool" and message.tool_call_id:
            label = f"{label} {message.tool_call_id}"
        return f"{label}: {content}"

    def _has_read_more_tool(self, tools):
        for tool in tools:
            if tool.name == "read_more":
                return True
        return False
