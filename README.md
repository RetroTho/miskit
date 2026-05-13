# miskit

A small, extensible AI agent.

## Project Layout

- `core/` contains the main `miskit` package.
- `core/src/miskit/runner.py` owns the conversation loop.
- `core/src/miskit/tools/` contains built-in tools.
- `core/src/miskit/channels/` contains built-in chat channels.
- `core/src/miskit/providers/` contains built-in model providers.
- `plugins/` contains optional provider, channel, and tool packages.

## Local Use

Install the core package in editable mode:

```sh
python3 -m pip install -e core
```

Run the terminal chat:

```sh
miskit chat
```

On first run, Miskit creates `~/.miskit/config.json`. Add a provider API key or configure a plugin provider there.
