from pathlib import Path

from miskit.tool import Tool
from miskit import file_process

_DEFAULT_MAX_ENTRIES = 200


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

    def __init__(self, workspace=None, restrict_to_workspace=True,
                 run_as_user=None, max_entries=_DEFAULT_MAX_ENTRIES):
        self.workspace = Path(workspace).expanduser() if workspace is not None else None
        self.restrict_to_workspace = restrict_to_workspace
        self.run_as_user = run_as_user
        self.max_entries = max_entries
        if self.workspace is not None:
            self.workspace.mkdir(parents=True, exist_ok=True)

    def run(self, arguments):
        requested_path = str(arguments.get("path", ".")).strip() or "."
        try:
            path = self.resolve_path(requested_path)
            raw = file_process.list_dir(path,
                                        run_as_user=self.run_as_user)
        except ValueError as error:
            return f"Could not list files: {error}"
        except OSError as error:
            return f"Could not list files: {error}"

        entries = sorted(raw, key=lambda item: (not item[1], item[0].lower()))
        total = len(entries)
        entries = entries[:self.max_entries]

        lines = [f"Files in {requested_path}:"]
        for name, is_dir in entries:
            label = name + "/" if is_dir else name
            lines.append(f"- {label}")

        if len(lines) == 1:
            lines.append("(empty)")

        if total > self.max_entries:
            lines.append(f"\n[{total - self.max_entries} more entries not shown]")

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
    run_as_user = services.get("run_as_user")
    return ListFilesTool(
        workspace=workspace,
        restrict_to_workspace=bool(restrict_to_workspace),
        run_as_user=run_as_user,
        max_entries=int(config.get("maxEntries", _DEFAULT_MAX_ENTRIES)),
    )
