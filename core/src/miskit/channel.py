from importlib import import_module
from importlib.metadata import entry_points


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
    for module_name in _candidate_module_names(name):
        try:
            module = import_module(module_name)
            break
        except ImportError:
            continue
    else:
        raise ValueError(f"unknown channel: {name}")

    if not hasattr(module, "create_channel"):
        raise ValueError(f"channel must define create_channel: {name}")

    return module


def _candidate_module_names(name):
    # Check installed plugins first (e.g. miskit-imessage registers "imessage").
    for ep in entry_points(group="miskit.channels"):
        if ep.name == name:
            yield ep.value
            break
    # Allow a full dotted module path (e.g. "mypackage.channels.custom").
    if "." in name:
        yield name
    else:
        # Fall back to built-in channels (e.g. "terminal" → miskit.channels.terminal).
        yield f"miskit.channels.{name}"
