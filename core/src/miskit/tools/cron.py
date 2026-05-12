from miskit.heartbeat import HEARTBEAT_JOB_ID
from miskit.tool import Tool

def _truncate(text, limit):
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[output truncated at {limit} characters]"


class CronTool(Tool):
    name = "cron"
    description = "Schedule one-time or recurring tasks for Miskit to run later as cron jobs."
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "list", "remove", "history"],
                "description": "Use add to schedule a task, list to show tasks, remove to delete one, or history to view past cron job results.",
            },
            "message": {
                "type": "string",
                "description": "The task Miskit should run when the scheduled time arrives.",
            },
            "at": {
                "type": "string",
                "description": (
                    "ISO datetime for one-time execution, like 2026-05-01T15:30:00-07:00. "
                    "Use the current time from Runtime Metadata to compute relative times like "
                    "'in 10 minutes' or 'tomorrow'. Optional for recurring jobs."
                ),
            },
            "everySeconds": {
                "type": "integer",
                "description": "Positive number of seconds between recurring runs.",
            },
            "name": {
                "type": "string",
                "description": "Optional short name for the scheduled task.",
            },
            "job_id": {
                "type": "string",
                "description": "A job id. For remove: the job to delete (heartbeat cannot be removed). For history: show the full turn details for that specific job run.",
            },
            "limit": {
                "type": "integer",
                "description": "Number of past cron jobs to show (default 10). Only used with the history action.",
            },
        },
        "required": ["action"],
    }

    def __init__(self, cron, log=None, max_output_chars=20_000):
        self.cron = cron
        self.log = log
        self.max_output_chars = max_output_chars

    def run(self, arguments):
        action = str(arguments.get("action", "")).strip()

        if action == "add":
            return self._add(arguments)
        if action == "list":
            return self._list()
        if action == "remove":
            return self._remove(arguments)
        if action == "history":
            return self._history(arguments)

        return "Unknown cron action. Use add, list, remove, or history."

    def _add(self, arguments):
        message = str(arguments.get("message", "")).strip()
        at = str(arguments.get("at", "")).strip()
        name = str(arguments.get("name", "")).strip()
        every_seconds = arguments.get("everySeconds", arguments.get("every_seconds"))

        if not message:
            return "Error: cron add requires message."

        if every_seconds is not None:
            try:
                job = self.cron.add_recurring_job(
                    name=name,
                    every_seconds=every_seconds,
                    message=message,
                    at=at or None,
                )
            except ValueError as error:
                return f"Error: {error}"

            return (
                f"Created recurring job '{job.name}' (id: {job.id}) "
                f"every {job.every_seconds} seconds."
            )

        if not at:
            return "Error: cron add requires at."

        try:
            job = self.cron.add_job(name=name, at=at, message=message)
        except ValueError as error:
            return f"Error: {error}"

        return f"Created job '{job.name}' (id: {job.id}) for {job.at.isoformat()}."

    def _list(self):
        jobs = self.cron.list_jobs()
        if not jobs:
            return "No scheduled jobs."

        lines = ["Scheduled jobs:"]
        for job in jobs:
            lines.append(f"- {job.name} (id: {job.id}, at: {job.at.isoformat()})")
            if job.every_seconds is not None:
                lines.append(f"  Repeats every: {job.every_seconds} seconds")
            lines.append(f"  Message: {job.message}")

        return "\n".join(lines)

    def _remove(self, arguments):
        job_id = str(arguments.get("job_id", "")).strip()
        if not job_id:
            return "Error: cron remove requires job_id."

        if job_id == HEARTBEAT_JOB_ID:
            return "Error: heartbeat is managed by config and cannot be removed with the cron tool."

        if self.cron.remove_job(job_id):
            return f"Removed job {job_id}."

        return f"Job {job_id} not found."

    def _history(self, arguments):
        if self.log is None:
            return "No cron log available."

        job_id = str(arguments.get("job_id", "")).strip()
        if job_id:
            return self._history_detail(job_id)

        limit = arguments.get("limit", 10)
        entries = self.log.read(limit=limit)
        if not entries:
            return "No past cron jobs recorded."

        lines = [f"Last {len(entries)} cron job(s):"]
        for entry in entries:
            lines.append(f"\n[{entry['timestamp']}] {entry['job_name']} (id: {entry['job_id']})")
            for message in reversed(entry.get("messages", [])):
                if message.get("role") == "assistant":
                    lines.append(f"  {message.get('content', '').strip()}")
                    break
        return "\n".join(lines)

    def _history_detail(self, job_id):
        entry = self.log.read_by_job_id(job_id)
        if entry is None:
            return f"No cron job found with id: {job_id}"

        lines = [
            f"Cron job: {entry['job_name']} (id: {entry['job_id']})",
            f"Timestamp: {entry['timestamp']}",
        ]
        for message in entry.get("messages", []):
            role = message.get("role", "unknown")
            if message.get("name"):
                role = f"{role} {message['name']}"
            lines.append(f"\n{role}: {message.get('content', '')}")
            for tc in message.get("tool_calls", []):
                lines.append(f"  -> tool call: {tc['name']}({tc['arguments']})")
        return _truncate("\n".join(lines), self.max_output_chars)


def create_tool(config, services=None):
    services = services or {}
    cron = services.get("cron")
    if cron is None:
        raise ValueError("cron tool requires a cron service")

    context_tokens = services.get("context_tokens", 8000)
    return CronTool(cron, log=services.get("cron_log"), max_output_chars=context_tokens * 5 // 2)
