from miskit.registry import load_module
from miskit.registry import require_attribute


class Tool:
    @classmethod
    def load(cls, config, services=None):
        return load_tool(config, services=services)

    @classmethod
    def load_all(cls, configs, services=None):
        return [cls.load(config, services=services) for config in configs]

    def run(self, arguments):
        raise NotImplementedError("tools must define run")


def load_tool(config, services=None):
    name = config.get("name")
    if not name:
        raise ValueError("tool.name is required")

    module = load_tool_module(name)
    return module.create_tool(config, services=services)


def load_tool_module(name):
    module = load_module(
        name,
        group="miskit.tools",
        builtins_prefix="miskit.tools",
        kind="tool",
    )
    return require_attribute(module, "create_tool", kind="tool", name=name)
