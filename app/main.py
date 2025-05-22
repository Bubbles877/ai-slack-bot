import asyncio
import sys
import traceback
from typing import Optional

import uvicorn
from loguru import logger
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp

from app.http_server import HTTPServer
from app.settings import Settings
from app.slack_bot import SlackBot
from util.setting.slack_settings import SlackSettings


class Main:
    def __init__(self, settings: Settings, slack_settings: SlackSettings):
        self._settings = settings
        self._slack_settings = slack_settings

        self._setup_logger(self._settings.log_level)

        logger.debug(f"Settings:\n{self._settings.model_dump_json(indent=2)}")

        self._bot = SlackBot(settings=self._slack_settings, enable_logging=True)
        self._http_server: Optional[HTTPServer] = None

        if not self._slack_settings.is_socket_mode:
            self._http_server = HTTPServer(
                request_handler=self._bot.request_handler(),
                setup_callback=self.setup,
                cleanup_callback=self.cleanup,
                enable_logging=True,
            )

    async def setup(self) -> None:
        """セットアップする"""
        logger.debug("Setting up...")

        await self._bot.setup()

        logger.debug("Setup complete")

    async def cleanup(self) -> None:
        """終了処理をする"""
        logger.debug("Cleaning up...")

        # TODO: 仮
        await asyncio.sleep(1)

        logger.debug("Cleanup complete")

    # def bot(self) -> SlackBot:
    #     """Slack ボットを取得する

    #     Returns:
    #         SlackBot: Slack ボット
    #     """
    #     return self._bot

    def slack_app(self) -> AsyncApp:
        """Slack App を取得する

        Returns:
            AsyncApp: Slack App
        """
        return self._bot

    def server_app(self) -> Optional[HTTPServer]:
        """サーバーアプリを取得する

        Returns:
            Optional[HTTPServer]: サーバーアプリ
        """
        return self._http_server

    @staticmethod
    def _setup_logger(log_level: str) -> None:
        logger.remove()  # default: stderr
        logger.add(sys.stdout, level=log_level)
        logger.add(
            "log/app_{time}.log",
            level=log_level,
            diagnose=log_level == "DEBUG",
            enqueue=True,
            rotation="1 day",
            retention="7 days",
        )


async def _socket_mode_main(main: Main, app_token: Optional[str]) -> None:
    logger.info("Socket mode starting...")

    await main.setup()

    handler = AsyncSocketModeHandler(main.slack_app(), app_token)

    # TODO: Ctrl + C で例外吐く
    try:
        await handler.start_async()
    except Exception as e:
        logger.error(f"Error: {e}")
        logger.debug(traceback.format_exc())

    await handler.close_async()
    await main.cleanup()


def _http_server_main(settings: Settings) -> None:
    logger.info("HTTP server starting...")

    uvicorn.run(
        app="main:main.server_app",
        host="0.0.0.0",
        port=settings.port if settings.port else 80,
        reload=settings.is_development,
        factory=True,
    )


logger.info(f"App main: {__name__=}")

main: Optional[Main] = None
settings = Settings()
slack_settings = SlackSettings()

# if __name__ == "__main__":
#     try:
#         main.run()
#     except KeyboardInterrupt:
#         logger.info("KeyboardInterrupt: Shutting down...")
#     except Exception as e:
#         logger.error(f"Error: {e}")
#         logger.debug(traceback.format_exc())

if __name__ == "__main__":
    if slack_settings.is_socket_mode:
        main = Main(settings, slack_settings)
        asyncio.run(_socket_mode_main(main, slack_settings.app_token))
    else:
        _http_server_main(settings)
else:
    # Uvicorn や Gunicorn で実行する場合
    main = Main(settings, slack_settings)
