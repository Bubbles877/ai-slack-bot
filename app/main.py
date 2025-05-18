import asyncio
import time

import uvicorn
from loguru import logger
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from app.http_server import HTTPServer
from app.settings import Settings
from app.slack_bot import SlackBot
from util.setting.slack_settings import SlackSettings

settings = Settings()
slack_settings = SlackSettings()

bot = SlackBot(settings=slack_settings, enable_logging=True)
api = HTTPServer(request_handler=bot.request_handler(), enable_logging=True)


async def _main() -> None:
    start_time = time.perf_counter()
    handler = AsyncSocketModeHandler(bot, slack_settings.app_token)
    await handler.start_async()
    await handler.close_async()

    logger.info(
        f"App main end (executed in {(time.perf_counter() - start_time) / 60:.1f}m)"
    )


if __name__ == "__main__":
    try:
        if slack_settings.is_socket_mode:
            logger.info("Socket mode starting...")
            asyncio.run(_main())
        else:
            logger.info("HTTP server starting...")
            uvicorn.run(
                # api,
                app="main:api",
                host="0.0.0.0",
                port=settings.port if settings.port else 80,
                reload=settings.is_development,
            )
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt: Shutting down...")
    except Exception as e:
        logger.error(f"Error: {e}")
