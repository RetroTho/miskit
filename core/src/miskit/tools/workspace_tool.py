from miskit.tool import Tool
from miskit.workspace import Workspace


class WorkspaceTool(Tool):
    def __init__(self, workspace=None, restrict_to_workspace=True, run_as_user=None):
        if isinstance(workspace, Workspace):
            self.workspace = workspace
        else:
            self.workspace = Workspace(workspace, restrict=restrict_to_workspace)
        self.run_as_user = run_as_user

    @classmethod
    def kwargs_from_config(cls, config, services=None):
        services = services or {}
        return {
            "workspace": Workspace.from_tool_config(config, services),
            "run_as_user": services.get("run_as_user"),
        }
