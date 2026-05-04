from miskit.heartbeat import HEARTBEAT_JOB_ID
from miskit.tool import Tool


class CronTool(Tool):
    name = "cron"
    description = "Schedule one-time or recurring tasks for Miskit to run later as cron jobs."
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "list", "remove"],
                "description": "Use add to schedule a task, list to show tasks, or remove to delete one.",
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
                "description": "The job id to remove. The heartbeat job is managed by config and cannot be removed.",
            },
        },
        "required": ["action"],
    }

    def __init__(self, cron):
        self.cron = cron

    def run(self, arguments):
        action = str(arguments.get("action", "")).strip()

        if action == "add":
            return self._add(arguments)
        if action == "list":
            return self._list()
        if action == "remove":
            return self._remove(arguments)

        return "Unknown cron action. Use add, list, or remove."

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


def create_tool(config, services=None):
    services = services or {}
    cron = services.get("cron")
    if cron is None:
        raise ValueError("cron tool requires a cron service")

    return CronTool(cron)
