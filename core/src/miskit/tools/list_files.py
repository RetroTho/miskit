from pathlib import Path

from miskit.tool import Tool


class ListFilesTool(Tool):
    name = "list_files"
    description = "List files inside Miskit's workspace."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Folder to list. Relative paths are resolved inside Miskit's workspace.",
            },
        },
    }

    def __init__(self, workspace=None, restrict_to_workspace=True):
        self.workspace = Path(workspace).expanduser() if workspace is not None else None
        self.restrict_to_workspace = restrict_to_workspace
        if self.workspace is not None:
            self.workspace.mkdir(parents=True, exist_ok=True)

    def run(self, arguments):
        requested_path = str(arguments.get("path", ".")).strip() or "."
        try:
            path = self.resolve_path(requested_path)
            entries = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        except ValueError as error:
            return f"Could not list files: {error}"
        except OSError as error:
            return f"Could not list files: {error}"

        lines = [f"Files in {requested_path}:"]
        for entry in entries:
            name = entry.name + "/" if entry.is_dir() else entry.name
            lines.append(f"- {name}")

        if len(lines) == 1:
            lines.append("(empty)")

        return "\n".join(lines)

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
    return ListFilesTool(workspace=workspace, restrict_to_workspace=bool(restrict_to_workspace))
