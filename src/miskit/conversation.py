from miskit.message import Message


class Conversation:
    def __init__(self):
        self.messages = []

    def add(self, message):
        if not isinstance(message, Message):
            raise TypeError("message must be a Message")

        self.messages.append(message)
        return message

    def add_system(self, content):
        return self.add(Message("system", content))

    def add_user(self, content):
        return self.add(Message("user", content))

    def add_assistant(self, content):
        return self.add(Message("assistant", content))
