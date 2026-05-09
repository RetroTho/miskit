import subprocess
from pathlib import Path

from miskit.tool import Tool

# Runs subprocesses on the host — not sandboxed unless run_as_user is set.

_DEFAULT_TIMEOUT = 60
_DEFAULT_MAX_OUTPUT_CHARS = 20_000


def _truncate(text, limit):
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[output truncated at {limit} characters]"


def _resolve_cwd(workspace, restrict, relative):
    relative = str(relative or "").strip()

    if not relative:
        if workspace is not None:
            return Path(workspace).expanduser().resolve()
        return None

    if workspace is None:
        return Path(relative).expanduser().resolve()

    base = Path(workspace).expanduser()
    path = Path(relative).expanduser()

    if not restrict:
        return path.resolve()

    if path.is_absolute():
        raise ValueError("cwd must be a relative path inside the workspace")

    resolved = (base / path).resolve()
    root = base.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError("cwd must stay inside the workspace")

    return resolved


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
                 timeout=_DEFAULT_TIMEOUT,
                 max_output_chars=_DEFAULT_MAX_OUTPUT_CHARS,
                 run_as_user=None):
        self.workspace = workspace
        self.restrict_to_workspace = restrict_to_workspace
        self.timeout = timeout
        self.max_output_chars = max_output_chars
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
            cwd = _resolve_cwd(self.workspace, self.restrict_to_workspace,
                               cwd_raw)
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

        return _truncate("\n".join(parts), self.max_output_chars)


def create_tool(config, services=None):
    services = services or {}
    return ExecuteTool(
        workspace=services.get("workspace"),
        restrict_to_workspace=bool(
            config.get("restrictToWorkspace",
                        services.get("restrict_to_workspace", True))),
        timeout=float(config.get("timeout", _DEFAULT_TIMEOUT)),
        max_output_chars=int(config.get("maxOutputChars",
                                        _DEFAULT_MAX_OUTPUT_CHARS)),
        run_as_user=config.get("runAsUser"),
    )
