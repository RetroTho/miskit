from pathlib import Path


class Workspace:
    def __init__(self, root=None, restrict=True):
        self.root = Path(root).expanduser() if root is not None else None
        self.restrict = bool(restrict)
        if self.root is not None:
            self.root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_tool_config(cls, config, services=None):
        services = services or {}
        restrict = config.get(
            "restrictToWorkspace",
            services.get("restrict_to_workspace", True),
        )
        return cls(services.get("workspace"), restrict=restrict)

    def resolve(self, value, *, default=None, label="path"):
        text = str(value or "").strip()
        if not text:
            if default is None:
                raise ValueError(f"{label} is required")
            text = default

        path = Path(text).expanduser()
        if self.root is None or not self.restrict:
            return path.resolve()

        if not path.is_absolute():
            path = self.root / path

        resolved = path.resolve()
        root = self.root.resolve()
        if resolved != root and root not in resolved.parents:
            raise ValueError(f"{label} must stay inside the workspace")
        return resolved

    def default_cwd(self):
        if self.root is None:
            return None
        return self.root.resolve()
