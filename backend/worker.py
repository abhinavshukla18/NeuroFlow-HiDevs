"""Background worker. Placeholder: connects to Postgres and Redis and stays alive."""

import asyncio
import logging
import signal

from redis.asyncio import Redis

from config import get_settings
from db import pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("neuroflow.worker")


async def main() -> None:
    settings = get_settings()
    stop = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await pool.create_pool()
    redis = Redis.from_url(settings.redis_url)
    await redis.ping()
    logger.info("Worker started. Waiting for jobs (none implemented yet).")

    try:
        await stop.wait()
    finally:
        await redis.aclose()
        await pool.close_pool()
        logger.info("Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())