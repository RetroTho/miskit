import asyncio

from miskit.channel import Channel


class TerminalChannel(Channel):
    def __init__(self, read=input, write=print):
        self.read = read
        self.write = write

    async def run(self, runner):
        self.write("Type '/quit' to exit.")

        while True:
            text = (await asyncio.to_thread(self.read, "You: ")).strip()

            if text == "/quit":
                break

            if not text:
                continue

            reply = await runner.chat(text)
            await self.send(reply.content)

    async def send(self, content):
        self.write(f"Agent: {content}")


def create_channel(config):
    return TerminalChannel()
