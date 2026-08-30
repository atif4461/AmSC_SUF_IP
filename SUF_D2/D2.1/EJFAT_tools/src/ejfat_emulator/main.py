from __future__ import annotations

import asyncio

import uvicorn

from .api import API_PORT, app
from .runtime import lb_process_manager


async def run() -> None:
    lb_process_manager.ensure_started()
    config = uvicorn.Config(app=app, host="0.0.0.0", port=API_PORT, log_level="info")
    server = uvicorn.Server(config=config)
    try:
        await server.serve()
    finally:
        lb_process_manager.stop()


if __name__ == "__main__":
    asyncio.run(run())
