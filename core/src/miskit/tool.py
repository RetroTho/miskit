from importlib import import_module


class Tool:
    @classmethod
    def load(cls, config, services=None):
        return load_tool(config, services=services)

    @classmethod
    def load_all(cls, configs, services=None):
        tools = []
        for config in configs:
            tools.append(cls.load(config, services=services))
        return tools

    def run(self, arguments):
        raise NotImplementedError("tools must define run")


def load_tool(config, services=None):
    name = config.get("name")
    if not name:
        raise ValueError("tool.name is required")

    module = load_tool_module(name)
    return module.create_tool(config, services=services)


def load_tool_module(name):
    try:
        module = import_module(tool_module_name(name))
    except ImportError as error:
        raise ValueError(f"unknown tool: {name}") from error

    if not hasattr(module, "create_tool"):
        raise ValueError(f"tool must define create_tool: {name}")

    return module


def tool_module_name(name):
    if "." in name:
        return name

    return f"miskit.tools.{name}"
