from miskit.registry import load_module
from miskit.registry import require_attribute


class Channel:
    @classmethod
    def load(cls, config, image_store=None):
        return load_channel(config, image_store=image_store)

    async def run(self, runner):
        raise NotImplementedError("channels must define run")

    async def send(self, content):
        raise NotImplementedError("channels must define send")


def load_channel(config, image_store=None):
    name = config.get("name")
    if not name:
        raise ValueError("channel.name is required")

    module = load_channel_module(name)
    return module.create_channel(config, image_store=image_store)


def load_channel_module(name):
    module = load_module(
        name,
        group="miskit.channels",
        builtins_prefix="miskit.channels",
        kind="channel",
    )
    return require_attribute(module, "create_channel", kind="channel", name=name)
