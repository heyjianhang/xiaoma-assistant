"""Optional worker-only process; uses the same durable queues and application services."""

import asyncio
import signal

from .app import create_app
from .settings import Settings


async def main():
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(name, stopped.set)
    settings = Settings().model_copy(update={"background_workers_enabled": True})
    app = create_app(settings)
    try:
        async with app.router.lifespan_context(app):
            await stopped.wait()
    finally:
        for name in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(name)


if __name__ == "__main__":
    asyncio.run(main())
