class Model:
    @classmethod
    def load(cls, config):
        from miskit.provider import load_model

        return load_model(config)

    async def complete(self, messages, tools=None):
        raise NotImplementedError("models must define complete")
