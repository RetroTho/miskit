from importlib import import_module


class Channel:
    @classmethod
    def load(cls, config):
        return load_channel(config)

    async def run(self, runner):
        raise NotImplementedError("channels must define run")

    async def send(self, content):
        raise NotImplementedError("channels must define send")


def load_channel(config):
    name = config.get("name")
    if not name:
        raise ValueError("channel.name is required")

    module = load_channel_module(name)
    return module.create_channel(config)


def load_channel_module(name):
    try:
        module = import_module(channel_module_name(name))
    except ImportError as error:
        raise ValueError(f"unknown channel: {name}") from error

    if not hasattr(module, "create_channel"):
        raise ValueError(f"channel must define create_channel: {name}")

    return module


def channel_module_name(name):
    if "." in name:
        return name

    return f"miskit.channels.{name}"
