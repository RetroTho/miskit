from miskit import file_process
from miskit.tools.workspace_tool import WorkspaceTool


class ReadFileTool(WorkspaceTool):
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

    def run(self, arguments):
        requested_path = str(arguments.get("path", "")).strip()
        if not requested_path:
            return "Could not read file: path is required."

        try:
            path = self.workspace.resolve(requested_path)
            text = file_process.read_text(path, run_as_user=self.run_as_user)
        except ValueError as error:
            return f"Could not read file: {error}"
        except OSError as error:
            return f"Could not read file: {error}"
        except UnicodeDecodeError:
            return "Could not read file: it is not a UTF-8 text file."

        return f"Contents of {requested_path}:\n\n{text}"


def create_tool(config, services=None):
    return ReadFileTool(**ReadFileTool.kwargs_from_config(config, services))
