import asyncio
import argparse

from miskit.heartbeat import HeartbeatTasks
from miskit.runtime import build_channel
from miskit.runtime import build_runtime
from miskit.runtime import channel_name
from miskit.runtime import connect_cron
from miskit.runtime import heartbeat_path


async def run_chat(instance=None, write=print):
    runtime = build_runtime(instance, write=write)
    if runtime is None:
        return

    if channel_name(runtime.config) != "terminal":
        raise ValueError("miskit chat only supports the terminal channel. Use miskit serve.")

    channel = build_channel(runtime.config)
    connect_cron(
        runtime.cron,
        runtime.runner,
        write=write,
        channel=channel,
        heartbeat_file=HeartbeatTasks(heartbeat_path(runtime.instance)),
    )
    await runtime.cron.start()
    try:
        await channel.run(runtime.runner)
    finally:
        await runtime.cron.stop()


async def run_server(instance=None, stop_event=None, write=print):
    runtime = build_runtime(instance, write=write)
    if runtime is None:
        return

    if channel_name(runtime.config) == "terminal":
        raise ValueError("miskit serve does not support the terminal channel. Use miskit chat.")

    channel = build_channel(runtime.config)
    connect_cron(
        runtime.cron,
        runtime.runner,
        write=write,
        channel=channel,
        heartbeat_file=HeartbeatTasks(heartbeat_path(runtime.instance)),
    )

    if stop_event is None:
        stop_event = asyncio.Event()

    write("Miskit server running. Press Ctrl-C to stop.")
    await runtime.cron.start()
    channel_task = asyncio.create_task(channel.run(runtime.runner))
    stop_task = asyncio.create_task(stop_event.wait())
    try:
        done, _ = await asyncio.wait(
            [channel_task, stop_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        if channel_task in done:
            channel_task.result()
    finally:
        for task in (channel_task, stop_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(channel_task, stop_task, return_exceptions=True)
        await runtime.cron.stop()


async def run(instance=None):
    await run_chat(instance)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", choices=["chat", "serve"], default="chat")
    parser.add_argument("--instance", "-i", help="Miskit instance directory")
    args = parser.parse_args()

    try:
        if args.command == "serve":
            asyncio.run(run_server(args.instance))
        else:
            asyncio.run(run_chat(args.instance))
    except ValueError as error:
        print(f"Error: {error}")
        raise SystemExit(1) from error
    except KeyboardInterrupt:
        print("\nStopped.")
