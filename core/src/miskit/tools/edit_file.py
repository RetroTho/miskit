from pathlib import Path

from miskit.tool import Tool
from miskit import file_process


class EditFileTool(Tool):
    name = "edit_file"
    description = (
        "Edit a UTF-8 text file by replacing one occurrence of old_text with new_text. "
        "If old_text matches more than once, either add surrounding lines so the match is unique "
        "or set replace_all to true to change every match."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path. Relative paths are resolved inside Miskit's workspace.",
            },
            "old_text": {
                "type": "string",
                "description": "Exact text to find and replace.",
            },
            "new_text": {
                "type": "string",
                "description": "Text to put in place of old_text.",
            },
            "replace_all": {
                "type": "boolean",
                "description": "If true, replace every occurrence of old_text.",
            },
        },
        "required": ["path", "old_text", "new_text"],
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
        old_text = arguments.get("old_text")
        new_text = arguments.get("new_text")

        if old_text is None:
            old_text = ""
        elif not isinstance(old_text, str):
            old_text = str(old_text)

        if new_text is None:
            new_text = ""
        elif not isinstance(new_text, str):
            new_text = str(new_text)

        replace_all = bool(arguments.get("replace_all", False))

        if not requested_path:
            return "Could not edit file: path is required."

        if old_text == "":
            return "Could not edit file: old_text cannot be empty."

        try:
            path = self.resolve_path(requested_path)
        except ValueError as error:
            return f"Could not edit file: {error}"

        if not file_process.is_file(path, run_as_user=self.run_as_user):
            return f"Could not edit file: not a file or does not exist: {requested_path}"

        try:
            content = file_process.read_text(path,
                                             run_as_user=self.run_as_user)
        except OSError as error:
            return f"Could not edit file: {error}"
        except UnicodeDecodeError:
            return "Could not edit file: it is not a UTF-8 text file."

        count = content.count(old_text)
        if count == 0:
            return "Could not edit file: old_text was not found."

        if count > 1 and not replace_all:
            return (
                "Could not edit file: old_text matches more than once. "
                "Add more surrounding lines so only one match is found, or set replace_all to true."
            )

        if replace_all:
            new_content = content.replace(old_text, new_text)
        else:
            start = content.find(old_text)
            new_content = content[:start] + new_text + content[start + len(old_text) :]

        try:
            file_process.write_text(path, new_content,
                                    run_as_user=self.run_as_user)
        except OSError as error:
            return f"Could not edit file: {error}"

        return f"Edited {requested_path}"

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
    return EditFileTool(
        workspace=workspace,
        restrict_to_workspace=bool(restrict_to_workspace),
        run_as_user=run_as_user,
    )
