import asyncio
import time

import uvicorn
from loguru import logger
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp

from app.http_server import HTTPServer
from app.settings import Settings
from util.setting.slack_settings import SlackSettings

settings = Settings()
slack_settings = SlackSettings()

app = AsyncApp(
    token=slack_settings.bot_token, signing_secret=slack_settings.signing_secret
)
# app.client.token = os.getenv("SLACK_BOT_TOKEN")
req_handler = AsyncSlackRequestHandler(app)


@app.event("app_mention")
# async def handle_app_mentions(body, say, logger):
async def handle_app_mentions(body, say):
    logger.info(body)
    await say("What's up?")


@app.event("message")
async def handle_message(body, say):
    logger.info(f"message: {body}")


api = HTTPServer(
    request_handler=req_handler,
    enable_logging=settings.log_level == "DEBUG",
)


async def _main() -> None:
    start_time = time.perf_counter()
    handler = AsyncSocketModeHandler(app, slack_settings.app_token)
    await handler.start_async()
    await handler.close_async()

    logger.info(
        f"App main end (executed in {(time.perf_counter() - start_time) / 60:.1f}m)"
    )


logger.info(f"{__name__=}")

if __name__ == "__main__":
    try:
        if slack_settings.is_socket_mode:
            logger.info("Socket mode is enabled")
            # AsyncSocketModeHandler(app, slack_settings.app_token).start_async()
            # asyncio.run(AsyncSocketModeHandler(app, slack_settings.app_token).start_async())
            asyncio.run(_main())
        else:
            logger.info("HTTP server starting...")
            uvicorn.run(
                # api,
                app="main:api",
                host="0.0.0.0",
                port=settings.port if settings.port else 80,
                reload=True,  # TODO: 本番環境では無効化
            )
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt: Shutting down...")
    except Exception as e:
        logger.error(f"Error: {e}")
