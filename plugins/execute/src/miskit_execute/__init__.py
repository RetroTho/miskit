import subprocess
from pathlib import Path

from miskit.tool import Tool

# Runs subprocesses on the host as the same OS user as Miskit — not sandboxed. Only enable when you trust callers.

_DEFAULT_TIMEOUT = 60
_DEFAULT_MAX_OUTPUT_CHARS = 20_000


def _truncate(text, limit):
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[output truncated at {limit} characters]"


def _resolve_cwd(workspace, restrict_to_workspace, cwd_hint):
    relative = str(cwd_hint or "").strip()
    if relative:
        if workspace is None:
            return Path(relative).expanduser().resolve()
        return _resolve_cwd_under_workspace(workspace, restrict_to_workspace, relative)
    if workspace is not None:
        return Path(workspace).expanduser().resolve()
    return None


def _resolve_cwd_under_workspace(workspace, restrict_to_workspace, relative):
    path = Path(relative).expanduser()
    base = Path(workspace).expanduser()

    if not restrict_to_workspace:
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
        "Run a real program on the host machine with the same permissions as the Miskit process "
        "(not sandboxed — it can access files, network, and devices the user can). "
        "Be careful: a mistaken or malicious invocation can delete or corrupt data, leak secrets, harm the system, or compromise accounts — only run programs and arguments you understand and intend. "
        "Pass argv with the program first, then each argument. "
        "No shell is started: pipes, globs, and $() are not expanded by a shell, but the program itself can still do anything it is allowed to do."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "argv": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Program name or path, then arguments. Double-check before running — wrong values can damage or expose the user's data or system.",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory, relative to the workspace when restrictions apply. Defaults to the workspace. Double-check before running — wrong values can damage or expose the user's data or system.",
            },
        },
        "required": ["argv"],
    }

    def __init__(self, workspace=None, restrict_to_workspace=True, timeout=_DEFAULT_TIMEOUT, max_output_chars=_DEFAULT_MAX_OUTPUT_CHARS):
        self.workspace = Path(workspace).expanduser() if workspace is not None else None
        self.restrict_to_workspace = restrict_to_workspace
        self.timeout = timeout
        self.max_output_chars = max_output_chars

    def run(self, arguments):
        raw_argv = arguments.get("argv")
        if not isinstance(raw_argv, list) or len(raw_argv) < 1:
            return "Execute needs argv with at least a program name."

        argv = []
        for index, item in enumerate(raw_argv):
            if not isinstance(item, str):
                return "Execute argv entries must be strings."
            if index == 0:
                program = item.strip()
                if not program:
                    return "Execute needs a non-empty program name."
                argv.append(program)
            else:
                argv.append(item)

        cwd_raw = arguments.get("cwd")
        if cwd_raw is not None and not isinstance(cwd_raw, str):
            return "Execute cwd must be a string."

        try:
            cwd = _resolve_cwd(self.workspace, self.restrict_to_workspace, cwd_raw if cwd_raw else None)
        except ValueError as error:
            return f"Could not run program: {error}"

        try:
            completed = subprocess.run(
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

        lines = [f"exit code: {completed.returncode}", ""]

        if completed.stdout:
            lines.extend(["stdout:", completed.stdout.rstrip("\n"), ""])

        if completed.stderr:
            lines.extend(["stderr:", completed.stderr.rstrip("\n")])

        return _truncate("\n".join(lines).strip(), self.max_output_chars)


def create_tool(config, services=None):
    services = services or {}
    workspace = services.get("workspace")
    restrict = config.get("restrictToWorkspace", services.get("restrict_to_workspace", True))
    timeout = float(config.get("timeout", _DEFAULT_TIMEOUT))
    max_output_chars = int(config.get("maxOutputChars", _DEFAULT_MAX_OUTPUT_CHARS))

    return ExecuteTool(
        workspace=workspace,
        restrict_to_workspace=bool(restrict),
        timeout=timeout,
        max_output_chars=max_output_chars,
    )
