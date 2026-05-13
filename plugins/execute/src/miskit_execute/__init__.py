import subprocess

from miskit.tool import Tool
from miskit.workspace import Workspace

# Runs subprocesses on the host — not sandboxed unless run_as_user is set.

_DEFAULT_TIMEOUT = 60


class ExecuteTool(Tool):
    name = "execute"
    description = (
        "Run a program on the host machine. "
        "Not sandboxed — the program runs with the same permissions as Miskit. "
        "Pass argv with the program first, then each argument. "
        "No shell is started: pipes, globs, and $() are not expanded."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "argv": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Program name or path, followed by arguments.",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory. Defaults to the workspace.",
            },
        },
        "required": ["argv"],
    }

    def __init__(self, workspace=None, restrict_to_workspace=True,
                 timeout=_DEFAULT_TIMEOUT, run_as_user=None):
        if isinstance(workspace, Workspace):
            self.workspace = workspace
        else:
            self.workspace = Workspace(workspace, restrict=restrict_to_workspace)
        self.timeout = timeout
        self.run_as_user = run_as_user

    def run(self, arguments):
        argv = arguments.get("argv")
        if not isinstance(argv, list) or not argv:
            return "argv must be a non-empty list."

        for item in argv:
            if not isinstance(item, str):
                return "Every argv entry must be a string."

        if not argv[0].strip():
            return "Program name cannot be empty."

        argv = [argv[0].strip()] + argv[1:]

        if self.run_as_user:
            argv = ["sudo", "-u", self.run_as_user, "--"] + argv

        cwd_raw = arguments.get("cwd")
        if cwd_raw is not None and not isinstance(cwd_raw, str):
            return "cwd must be a string."

        try:
            cwd = self._cwd(cwd_raw)
        except ValueError as error:
            return f"Could not run program: {error}"

        try:
            result = subprocess.run(
                argv,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                shell=False,
                errors="replace",
            )
        except FileNotFoundError:
            return f"Program not found: {argv[0]!r}"
        except subprocess.TimeoutExpired:
            return f"Program timed out after {self.timeout} seconds."

        parts = [f"exit code: {result.returncode}"]
        if result.stdout:
            parts.extend(["", "stdout:", result.stdout.rstrip()])
        if result.stderr:
            parts.extend(["", "stderr:", result.stderr.rstrip()])

        return "\n".join(parts)

    def _cwd(self, raw):
        if raw is None or not raw.strip():
            return self.workspace.default_cwd()
        return self.workspace.resolve(raw, label="cwd")


def create_tool(config, services=None):
    services = services or {}
    workspace = Workspace.from_tool_config(config, services)
    return ExecuteTool(
        workspace=workspace,
        timeout=float(config.get("timeout", _DEFAULT_TIMEOUT)),
        run_as_user=services.get("run_as_user"),
    )
