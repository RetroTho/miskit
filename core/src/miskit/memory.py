from pathlib import Path

_MAX_ENTRIES_PER_CATEGORY = 50


class Memory:
    identity = """# Miskit

You are Miskit, a small and helpful AI assistant.
Use the memory below when it is relevant to the conversation.
Do not mention the memory unless it helps answer the user."""

    files = {
        "user": "user.md",
        "bot": "bot.md",
        "notes": "notes.md",
    }

    titles = {
        "user": "User",
        "bot": "Bot",
        "notes": "Notes",
    }

    def __init__(self, folder):
        self.folder = Path(folder)

    def setup(self):
        self.folder.mkdir(parents=True, exist_ok=True)

        for category in self.files:
            path = self._path(category)
            if not path.exists():
                title = self.titles[category]
                path.write_text(f"# {title}\n\n", encoding="utf-8")

    def read(self):
        parts = []

        for category in self.files:
            path = self._path(category)
            if path.exists():
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    parts.append(text)

        return "\n\n".join(parts)

    def system_prompt(self):
        memory_text = self.read()
        if not memory_text:
            return self.identity

        return f"{self.identity}\n\n# Memory\n\n{memory_text}"

    def add(self, category, text):
        self._check_category(category)

        if len(self.entries(category)) >= _MAX_ENTRIES_PER_CATEGORY:
            raise ValueError(
                f"{category} memory is full ({_MAX_ENTRIES_PER_CATEGORY} entries). "
                "Remove or update an existing entry before adding a new one."
            )

        self.setup()
        with self._path(category).open("a", encoding="utf-8") as file:
            file.write(f"- {text}\n")

    def entries(self, category=None):
        self.setup()
        categories = list(self.files)
        if category is not None:
            self._check_category(category)
            categories = [category]

        entries = []
        for current_category in categories:
            count = 0
            lines = self._path(current_category).read_text(encoding="utf-8").splitlines()
            for line_number, line in enumerate(lines):
                text = parse_memory_line(line)
                if text is None:
                    continue

                count += 1
                entries.append({
                    "id": f"{current_category}:{count}",
                    "category": current_category,
                    "line_number": line_number,
                    "text": text,
                })

        return entries

    def update(self, memory_id, text):
        text = str(text).strip()
        if not text:
            raise ValueError("memory update requires text")

        entry = self._entry(memory_id)
        lines = self._path(entry["category"]).read_text(encoding="utf-8").splitlines()
        lines[entry["line_number"]] = f"- {text}"
        self._write_lines(entry["category"], lines)

    def remove(self, memory_id):
        entry = self._entry(memory_id)
        lines = self._path(entry["category"]).read_text(encoding="utf-8").splitlines()
        del lines[entry["line_number"]]
        self._write_lines(entry["category"], lines)

    def _path(self, category):
        return self.folder / self.files[category]

    def _entry(self, memory_id):
        text = str(memory_id).strip()
        parts = text.split(":", 1)
        if len(parts) != 2:
            raise ValueError("memory_id must look like user:1")

        category, number = parts
        self._check_category(category)

        try:
            index = int(number) - 1
        except ValueError as error:
            raise ValueError("memory_id must look like user:1") from error

        entries = self.entries(category)
        if index < 0 or index >= len(entries):
            raise ValueError("memory_id was not found")

        return entries[index]

    def _write_lines(self, category, lines):
        self._path(category).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    def _check_category(self, category):
        if category not in self.files:
            raise ValueError("category must be user, bot, or notes")


def parse_memory_line(line):
    text = line.strip()
    if text.startswith("- "):
        return text[2:].strip()
    return None
