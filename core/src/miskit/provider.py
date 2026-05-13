from miskit.registry import load_module
from miskit.registry import require_attribute


class Provider:
    def create_model(self, config):
        raise NotImplementedError("providers must define create_model")


def load_model(config):
    provider_name = config.get("name")
    if not provider_name:
        raise ValueError("provider.name is required")

    provider = load_provider(provider_name)
    return provider.create_model(config)


def load_provider(name):
    module = load_module(
        name,
        group="miskit.providers",
        builtins_prefix="miskit.providers",
        kind="provider",
        allow_direct=True,
    )
    provider = module
    if hasattr(module, "provider"):
        provider = module.provider

    return require_attribute(provider, "create_model", kind="provider", name=name)
