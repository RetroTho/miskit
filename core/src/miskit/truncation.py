from pathlib import Path
from string import hexdigits
from uuid import uuid4


class TruncationStore:
    def __init__(self, root):
        self.root = Path(root)

    def setup(self):
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, text):
        self.setup()
        store_id = str(uuid4())[:8]
        (self.root / f"{store_id}.txt").write_text(text, encoding="utf-8")
        return store_id

    def read(self, store_id, offset=0):
        store_id = str(store_id)
        if not store_id or any(char not in hexdigits for char in store_id):
            raise ValueError(f"invalid truncation id: {store_id}")
        path = self.root / f"{store_id}.txt"
        if not path.exists():
            raise ValueError(f"truncation id not found: {store_id}")
        text = path.read_text(encoding="utf-8")
        return text[offset:]
