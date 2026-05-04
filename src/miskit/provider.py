from importlib import import_module


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
    try:
        module = import_module(provider_module_name(name))
    except ImportError as error:
        raise ValueError(f"unknown provider: {name}") from error

    provider = module
    if hasattr(module, "provider"):
        provider = module.provider

    if not hasattr(provider, "create_model"):
        raise ValueError(f"provider must define create_model: {name}")

    return provider


def provider_module_name(name):
    if "." in name:
        return name

    return f"miskit.providers.{name}"
