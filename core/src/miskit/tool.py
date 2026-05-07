from importlib import import_module
from importlib.metadata import entry_points


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
    for module_name in _candidate_module_names(name):
        try:
            module = import_module(module_name)
            break
        except ImportError:
            continue
    else:
        raise ValueError(f"unknown tool: {name}")

    if not hasattr(module, "create_tool"):
        raise ValueError(f"tool must define create_tool: {name}")

    return module


def _candidate_module_names(name):
    # Check installed plugins first (entry point names map to a module path).
    for ep in entry_points(group="miskit.tools"):
        if ep.name == name:
            yield ep.value
            break
    # Allow a full dotted module path (e.g. "mypackage.tools.custom").
    if "." in name:
        yield name
    else:
        # Fall back to built-in tools (e.g. "read_file" → miskit.tools.read_file).
        yield f"miskit.tools.{name}"
