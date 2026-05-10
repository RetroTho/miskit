import subprocess
from pathlib import Path

# File operations backed by subprocess.
# When run_as_user is set each command is prefixed with
# "sudo -u <user> --" so it runs as that OS user.


def _argv(command, run_as_user=None):
    """Prepend sudo when a run_as_user is configured."""
    if run_as_user:
        return ["sudo", "-u", run_as_user, "--"] + command
    return command


def read_text(path, run_as_user=None):
    """Read *path* as UTF-8 text via subprocess."""
    argv = _argv(["cat", "--", str(path)], run_as_user)
    result = subprocess.run(argv, capture_output=True)

    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise OSError(message or f"failed to read {path}")

    return result.stdout.decode("utf-8")


def write_text(path, content, run_as_user=None):
    """Write UTF-8 *content* to *path* via subprocess.

    Creates parent directories when they do not exist.
    """
    parent = str(Path(path).parent)
    mkdir_argv = _argv(["mkdir", "-p", "--", parent], run_as_user)
    subprocess.run(mkdir_argv, capture_output=True)

    tee_argv = _argv(["tee", "--", str(path)], run_as_user)
    result = subprocess.run(tee_argv, input=content.encode("utf-8"),
                            capture_output=True)

    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise OSError(message or f"failed to write {path}")


def is_file(path, run_as_user=None):
    """Return True if *path* is an existing regular file."""
    argv = _argv(["test", "-f", str(path)], run_as_user)
    result = subprocess.run(argv, capture_output=True)
    return result.returncode == 0


def list_dir(path, run_as_user=None):
    """List directory entries via subprocess.

    Returns a list of (name, is_directory) tuples.
    """
    argv = _argv(["ls", "-1", "-p", "--", str(path)], run_as_user)
    result = subprocess.run(argv, capture_output=True, text=True,
                            errors="replace")

    if result.returncode != 0:
        message = result.stderr.strip()
        raise OSError(message or f"failed to list {path}")

    entries = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.endswith("/"):
            entries.append((line[:-1], True))
        else:
            entries.append((line, False))

    return entries
