from miskit import file_process
from miskit.tools.workspace_tool import WorkspaceTool


class WriteFileTool(WorkspaceTool):
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
            path = self.workspace.resolve(requested_path)
            file_process.write_text(path, content,
                                    run_as_user=self.run_as_user)
        except ValueError as error:
            return f"Could not write file: {error}"
        except OSError as error:
            return f"Could not write file: {error}"

        return f"Wrote {len(content)} characters to {requested_path}"


def create_tool(config, services=None):
    return WriteFileTool(**WriteFileTool.kwargs_from_config(config, services))
