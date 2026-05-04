from pathlib import Path

from miskit.tool import Tool


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read a UTF-8 text file from Miskit's workspace."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The path of the file to read. Relative paths are resolved inside Miskit's workspace.",
            },
        },
        "required": ["path"],
    }

    def __init__(self, workspace=None, restrict_to_workspace=True):
        self.workspace = Path(workspace).expanduser() if workspace is not None else None
        self.restrict_to_workspace = restrict_to_workspace
        if self.workspace is not None:
            self.workspace.mkdir(parents=True, exist_ok=True)

    def run(self, arguments):
        requested_path = str(arguments.get("path", "")).strip()
        if not requested_path:
            return "Could not read file: path is required."

        try:
            path = self.resolve_path(requested_path)
            text = path.read_text(encoding="utf-8")
        except ValueError as error:
            return f"Could not read file: {error}"
        except OSError as error:
            return f"Could not read file: {error}"
        except UnicodeDecodeError:
            return "Could not read file: it is not a UTF-8 text file."

        return f"Contents of {requested_path}:\n\n{text}"

    def resolve_path(self, path):
        path = Path(path).expanduser()
        if self.workspace is None or not self.restrict_to_workspace:
            return path

        if not path.is_absolute():
            path = self.workspace / path

        resolved = path.resolve()
        workspace = self.workspace.resolve()
        if resolved != workspace and workspace not in resolved.parents:
            raise ValueError("path must stay inside the workspace")

        return resolved


def create_tool(config, services=None):
    services = services or {}
    workspace = services.get("workspace")
    restrict_to_workspace = config.get("restrictToWorkspace", services.get("restrict_to_workspace", True))
    return ReadFileTool(workspace=workspace, restrict_to_workspace=bool(restrict_to_workspace))
