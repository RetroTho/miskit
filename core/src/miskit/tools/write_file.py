from pathlib import Path

from miskit.tool import Tool
from miskit import file_process


class WriteFileTool(Tool):
    name = "write_file"
    description = (
        "Write UTF-8 text to a file. Overwrites the whole file if it exists. "
        "Creates parent folders as needed. To change part of a file, use edit_file."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path. Relative paths are resolved inside Miskit's workspace.",
            },
            "content": {
                "type": "string",
                "description": "Full new file contents.",
            },
        },
        "required": ["path", "content"],
    }

    def __init__(self, workspace=None, restrict_to_workspace=True,
                 run_as_user=None):
        self.workspace = Path(workspace).expanduser() if workspace is not None else None
        self.restrict_to_workspace = restrict_to_workspace
        self.run_as_user = run_as_user
        if self.workspace is not None:
            self.workspace.mkdir(parents=True, exist_ok=True)

    def run(self, arguments):
        requested_path = str(arguments.get("path", "")).strip()
        content = arguments.get("content")
        if content is None:
            content = ""
        elif not isinstance(content, str):
            content = str(content)

        if not requested_path:
            return "Could not write file: path is required."

        try:
            path = self.resolve_path(requested_path)
            file_process.write_text(path, content,
                                    run_as_user=self.run_as_user)
        except ValueError as error:
            return f"Could not write file: {error}"
        except OSError as error:
            return f"Could not write file: {error}"

        return f"Wrote {len(content)} characters to {requested_path}"

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
    restrict_to_workspace = config.get(
        "restrictToWorkspace",
        services.get("restrict_to_workspace", True),
    )
    run_as_user = services.get("run_as_user")
    return WriteFileTool(
        workspace=workspace,
        restrict_to_workspace=bool(restrict_to_workspace),
        run_as_user=run_as_user,
    )
