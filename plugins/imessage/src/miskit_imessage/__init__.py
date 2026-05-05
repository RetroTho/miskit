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

    def has_recipient(self, recipient):
        with closing(self.connect()) as connection:
            row = connection.execute(
                "select 1 from handle where id = ? limit 1",
                (recipient,),
            ).fetchone()
        return row is not None

    def latest_rowid(self, recipient):
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                select coalesce(max(message.ROWID), 0) as rowid
                from message
                join handle on message.handle_id = handle.ROWID
                where handle.id = ?
                """,
                (recipient,),
            ).fetchone()
        return int(row["rowid"])

    def incoming_after(self, recipient, rowid):
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                select message.ROWID as rowid, message.text as text
                from message
                join handle on message.handle_id = handle.ROWID
                where handle.id = ?
                  and message.ROWID > ?
                  and message.is_from_me = 0
                  and message.text is not null
                  and message.text != ''
                order by message.ROWID
                """,
                (recipient, rowid),
            ).fetchall()

        return [IncomingMessage(int(row["rowid"]), row["text"]) for row in rows]

    def connect(self):
        database_uri = "file:" + quote(str(self.path), safe="/") + "?mode=ro"
        connection = sqlite3.connect(database_uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection


_SEND_SCRIPT = """
on run argv
    set targetRecipient to item 1 of argv
    set messageText to item 2 of argv
    tell application "Messages"
        set targetService to 1st service whose service type = iMessage
        set targetBuddy to buddy targetRecipient of targetService
        send messageText to targetBuddy
    end tell
end run
"""


class MessagesApp:
    async def send(self, recipient, content):
        # Pass the script via stdin ("-") so osascript forwards the extra
        # arguments (recipient, content) to the "on run argv" handler.
        # Using "-e" does not reliably pass arguments to argv.
        process = await asyncio.create_subprocess_exec(
            "osascript", "-",
            recipient,
            content,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate(_SEND_SCRIPT.encode("utf-8"))

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
        self.last_rowid = None

    def start(self):
        if not self.database.has_recipient(self.recipient):
            raise ValueError(
                "iMessage recipient was not found in the local Messages database. "
                "Send or receive a message with this recipient first."
            )
        self.last_rowid = self.database.latest_rowid(self.recipient)

    async def run(self, runner):
        self.start()
        self.write(f"Miskit iMessage channel watching {self.recipient}. Press Ctrl-C to stop.")

        while True:
            await self.run_pending(runner)
            await asyncio.sleep(self.poll_seconds)

    async def run_pending(self, runner):
        if self.last_rowid is None:
            self.start()

        for message in self.database.incoming_after(self.recipient, self.last_rowid):
            self.last_rowid = message.rowid
            reply = await runner.chat(message.text)
            await self.send(reply.content)

    async def send(self, content):
        await self.sender.send(self.recipient, content)


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
