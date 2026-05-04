from miskit.provider import Provider
from miskit_codex.auth import login_codex
from miskit_codex.model import CodexModel


class CodexProvider(Provider):
    def create_model(self, config):
        return CodexModel.from_config(config)

    def setup(self, write=print, read=input):
        return login_codex(write=write, read=read)


provider = CodexProvider()
