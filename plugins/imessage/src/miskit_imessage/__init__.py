import asyncio
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from miskit.channel import Channel


@dataclass
class IncomingMessage:
    rowid: int
    text: str


class MessagesDatabase:
    def __init__(self, path=None):
        if path is None:
            path = Path.home() / "Library" / "Messages" / "chat.db"
        self.path = Path(path).expanduser()

    def latest_rowid(self, chat_guid):
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                select coalesce(max(message.ROWID), 0) as rowid
                from message
                join chat_message_join on chat_message_join.message_id = message.ROWID
                join chat on chat.ROWID = chat_message_join.chat_id
                where chat.guid = ?
                """,
                (chat_guid,),
            ).fetchone()
        return int(row["rowid"])

    def chat_guid(self, recipient):
        with closing(self.connect()) as connection:
            row = connection.execute(
                "select guid from chat where guid = ? limit 1",
                (recipient,),
            ).fetchone()
            if row is not None:
                return row["guid"]

            row = connection.execute(
                """
                select chat.guid as guid
                from chat
                join chat_handle_join on chat_handle_join.chat_id = chat.ROWID
                join handle on handle.ROWID = chat_handle_join.handle_id
                where handle.id = ?
                  and (
                    select count(*)
                    from chat_handle_join as members
                    where members.chat_id = chat.ROWID
                  ) = 1
                order by chat.ROWID desc
                limit 1
                """,
                (recipient,),
            ).fetchone()

            if row is None:
                row = connection.execute(
                    """
                    select guid
                    from chat
                    where chat_identifier = ?
                    order by ROWID desc
                    limit 1
                    """,
                    (recipient,),
                ).fetchone()
        if row is None:
            return None
        return row["guid"]

    def incoming_after(self, chat_guid, rowid):
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                select message.ROWID as rowid, message.text as text
                from message
                join chat_message_join on chat_message_join.message_id = message.ROWID
                join chat on chat.ROWID = chat_message_join.chat_id
                where chat.guid = ?
                  and message.ROWID > ?
                  and message.is_from_me = 0
                  and message.text is not null
                  and message.text != ''
                order by message.ROWID
                """,
                (chat_guid, rowid),
            ).fetchall()

        return [IncomingMessage(int(row["rowid"]), row["text"]) for row in rows]

    def connect(self):
        database_uri = "file:" + quote(str(self.path), safe="/") + "?mode=ro"
        connection = sqlite3.connect(database_uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection


_SEND_SCRIPT = Path(__file__).parent / "send.applescript"


class MessagesApp:
    async def send(self, chat_guid, content):
        process = await asyncio.create_subprocess_exec(
            "osascript", str(_SEND_SCRIPT),
            chat_guid,
            content,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            output = stderr.decode("utf-8", errors="replace").strip()
            if not output:
                output = stdout.decode("utf-8", errors="replace").strip()
            raise RuntimeError(output or "Messages failed to send the iMessage.")


class IMessageChannel(Channel):
    def __init__(self, recipient, database=None, sender=None, poll_seconds=2, write=print):
        self.recipient = recipient
        self.database = database or MessagesDatabase()
        self.sender = sender or MessagesApp()
        self.poll_seconds = poll_seconds
        self.write = write
        self.chat_guid = None
        self.last_rowid = None

    def _note(self, line):
        self.write(f"[imessage] {line}")

    def start(self):
        self.chat_guid = self.database.chat_guid(self.recipient)
        if self.chat_guid is None:
            raise ValueError(
                "No iMessage chat found for this recipient. "
                "Send or receive a message with this recipient first."
            )
        self.last_rowid = self.database.latest_rowid(self.chat_guid)

    async def run(self, runner):
        self.start()
        self.write(f"Miskit iMessage channel watching {self.recipient}. Press Ctrl-C to stop.")

        while True:
            await self.run_pending(runner)
            await asyncio.sleep(self.poll_seconds)

    async def run_pending(self, runner):
        if self.last_rowid is None:
            self.start()

        for message in self.database.incoming_after(self.chat_guid, self.last_rowid):
            self.last_rowid = message.rowid
            self._note(f"Received: {message.text!r}")
            reply = await runner.chat(message.text)
            await self.send(reply.content)

    async def send(self, content):
        self._note(f"Sending to {self.recipient} ({len(content)} chars).")
        await self.sender.send(self.chat_guid, content)
        self._note("Sent.")


def create_channel(config):
    recipient = str(config.get("recipient", "")).strip()
    if not recipient:
        raise ValueError("channel.recipient is required for imessage")

    try:
        poll_seconds = float(config.get("pollSeconds", 2))
    except (TypeError, ValueError) as error:
        raise ValueError("channel.pollSeconds must be a number") from error

    if poll_seconds <= 0:
        raise ValueError("channel.pollSeconds must be greater than 0")

    database_path = config.get("database")
    database = MessagesDatabase(database_path) if database_path else None
    return IMessageChannel(recipient, database=database, poll_seconds=poll_seconds)
