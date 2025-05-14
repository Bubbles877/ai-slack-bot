import asyncio
import time

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


# # TODO: HTTP 起動用処理をクラスに分ける
# api = FastAPI()


# @api.post("/slack/events")
# async def endpoint(req: Request):
#     return await req_handler.handle(req)


# @api.get("/status")
# async def status(req: Request):
#     """HTTP 起動の疎通確認用のエンドポイント"""
#     logger.info(f"status called: {req}")
#     return json.dumps({"status": "healthy"})


async def _main() -> None:
    start_time = time.perf_counter()
    # await AsyncSocketModeHandler(app, slack_settings.app_token).start_async()
    handler = AsyncSocketModeHandler(app, slack_settings.app_token)
    await handler.start_async()
    await handler.close_async()

    logger.info(
        f"App main end (executed in {(time.perf_counter() - start_time) / 60:.1f}m)"
    )


if __name__ == "__main__":
    try:
        if slack_settings.is_socket_mode:
            # AsyncSocketModeHandler(app, slack_settings.app_token).start_async()
            # asyncio.run(AsyncSocketModeHandler(app, slack_settings.app_token).start_async())
            asyncio.run(_main())
        else:
            # uvicorn.run(
            #     # api,
            #     # app="app.main:api",
            #     app="main:api",
            #     host="0.0.0.0",
            #     port=settings.port if settings.port else 80,
            #     reload=True,  # TODO: 本番環境では無効化
            # )
            # pass
            http_server = HTTPServer(
                port=settings.port,
                request_handler=req_handler,
                enable_logging=settings.log_level == "DEBUG",
            )
            http_server.run()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt: Shutting down...")
    except Exception as e:
        logger.error(f"Error: {e}")
