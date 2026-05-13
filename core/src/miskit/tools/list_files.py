from miskit import file_process
from miskit.tools.workspace_tool import WorkspaceTool

_DEFAULT_MAX_ENTRIES = 200


class ListFilesTool(WorkspaceTool):
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
        super().__init__(
            workspace=workspace,
            restrict_to_workspace=restrict_to_workspace,
            run_as_user=run_as_user,
        )
        self.max_entries = max_entries

    def run(self, arguments):
        requested_path = str(arguments.get("path", ".")).strip() or "."
        try:
            path = self.workspace.resolve(requested_path, default=".")
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


def create_tool(config, services=None):
    kwargs = ListFilesTool.kwargs_from_config(config, services)
    return ListFilesTool(
        **kwargs,
        max_entries=int(config.get("maxEntries", _DEFAULT_MAX_ENTRIES)),
    )
