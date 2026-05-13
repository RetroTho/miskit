from miskit.tool import Tool


class ReadMoreTool(Tool):
    name = "read_more"
    description = "Read more of a truncated tool output by its id."
    input_schema = {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "The truncation id from a truncated output.",
            },
            "offset": {
                "type": "integer",
                "description": "Character offset to start reading from (default: 0).",
            },
        },
        "required": ["id"],
    }

    def __init__(self, store):
        self.store = store

    def run(self, arguments):
        store_id = str(arguments.get("id", "")).strip()
        if not store_id:
            return "Error: read_more requires id."

        offset = arguments.get("offset", 0)
        if not isinstance(offset, int) or offset < 0:
            offset = 0

        try:
            return self.store.read(store_id, offset=offset)
        except ValueError as error:
            return f"Error: {error}"


def create_tool(config, services=None):
    services = services or {}
    store = services.get("truncation_store")
    if store is None:
        raise ValueError("read_more tool requires a truncation_store service")
    return ReadMoreTool(store)
