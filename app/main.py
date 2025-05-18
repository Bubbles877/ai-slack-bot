import asyncio
import sys
import time
import traceback
from typing import Optional

import uvicorn
from loguru import logger
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from app.http_server import HTTPServer
from app.settings import Settings
from app.slack_bot import SlackBot
from util.setting.slack_settings import SlackSettings


class Main:
    def __init__(self):
        self._settings = Settings()
        self._slack_settings = SlackSettings()

        self._setup_logger(self._settings.log_level)

        logger.debug(f"Settings:\n{self._settings.model_dump_json(indent=2)}")
        logger.debug(
            f"Slack Settings:\n{self._slack_settings.model_dump_json(indent=2)}"
        )

        self._bot = SlackBot(settings=self._slack_settings, enable_logging=True)
        self._api: Optional[HTTPServer] = None

        if not self._slack_settings.is_socket_mode:
            self._api = HTTPServer(
                request_handler=self._bot.request_handler(), enable_logging=True
            )

    def api(self) -> Optional[HTTPServer]:
        """HTTPサーバーを取得する

        Returns:
            Optional[HTTPServer]: HTTPサーバー
        """
        return self._api

    def run(self) -> None:
        """実行する

        コマンドラインから Uvicorn や Gunicorn で実行する場合はこのメソッドの呼び出しは不要です。
        """
        start_time = time.perf_counter()

        if self._slack_settings.is_socket_mode:
            asyncio.run(self._socket_mode_main())
        else:
            self._http_server_main()

        logger.info(
            f"App main end (executed in {(time.perf_counter() - start_time) / 60:.1f}m)"
        )

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

    def _http_server_main(self) -> None:
        logger.info("HTTP server starting...")
        uvicorn.run(
            # api,
            app="main:main.api",
            host="0.0.0.0",
            port=self._settings.port if self._settings.port else 80,
            reload=self._settings.is_development,
            factory=True,
        )

    async def _socket_mode_main(self) -> None:
        logger.info("Socket mode starting...")

        handler = AsyncSocketModeHandler(self._bot, self._slack_settings.app_token)

        try:
            await handler.start_async()
        except Exception as e:
            logger.error(f"Error: {e}")

        await handler.close_async()


main = Main()

logger.info(f"App main start: {__name__=}")

if __name__ == "__main__":
    try:
        main.run()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt: Shutting down...")
    except Exception as e:
        logger.error(f"Error: {e}")
        logger.debug(traceback.format_exc())
