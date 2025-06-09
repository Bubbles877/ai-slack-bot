import asyncio
import sys
import traceback
from typing import Optional

import uvicorn
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from loguru import logger
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp

import util.llm_utils as llm_utils
from app.http_server import HTTPServer
from app.resource_loader import ResourceLoader
from app.settings import Settings
from app.slack_bot import SlackBot, SlackMessage
from util.llm_chat import LLMChat
from util.setting.llm_settings import LLMSettings
from util.setting.slack_settings import SlackSettings


class Main:
    def __init__(
        self,
        settings: Settings,
        slack_settings: SlackSettings,
        llm_settings: LLMSettings,
    ):
        self._settings = settings
        self._slack_settings = slack_settings
        self._llm_settings = llm_settings

        self._setup_logger(self._settings.log_level)

        logger.debug(f"Settings:\n{self._settings.model_dump_json(indent=2)}")

        self._resource_loader = ResourceLoader(enable_logging=True)

        self._slack_bot = SlackBot(
            self._slack_settings, self._chat, enable_logging=True
        )
        self._http_server: Optional[HTTPServer] = None

        if not self._slack_settings.is_socket_mode:
            self._http_server = HTTPServer(
                request_handler=self._slack_bot.request_handler(),
                setup_callback=self.setup,
                cleanup_callback=self.cleanup,
                enable_logging=True,
            )

        llm_utils.enable_logging(enable=True)

        if not (llm := llm_utils.create_llm(self._llm_settings)):
            raise RuntimeError("Failed to create LLM")

        self._llm_chat = LLMChat(
            llm, self._settings.llm_max_messages, enable_logging=True
        )

    async def setup(self) -> None:
        """セットアップする"""
        logger.debug("Setting up...")

        llm_instructions = await self._resource_loader.load_plane_text(
            self._settings.llm_instruction_file_path
        )
        self._llm_chat.configure(llm_instructions)

        await self._slack_bot.setup()

        logger.debug("Setup complete")

    async def cleanup(self) -> None:
        """終了処理をする"""
        logger.debug("Cleaning up...")

        logger.debug("Cleanup complete")

    def slack_app(self) -> AsyncApp:
        """Slack App を取得する

        Returns:
            AsyncApp: Slack App
        """
        return self._slack_bot

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

    async def _chat(
        self, user_message: str, history: Optional[list[SlackMessage]] = None
    ) -> str:
        logger.debug(f"(User) {user_message}")
        hist: Optional[list[AnyMessage]] = None

        if history:
            hist = self._to_llm_messages(history)

        ai_res = await self._llm_chat.ainvoke(user_message, hist)
        logger.debug(f"(AI) {ai_res}")
        return ai_res

    @staticmethod
    def _to_llm_messages(messages: list[SlackMessage]) -> list[AnyMessage]:
        msgs: list[AnyMessage] = []

        for msg in messages:
            role = msg.get("role", "")
            bot_name = msg.get("bot_name", "")
            content = msg.get("content", "")

            match role:
                case "user":
                    msgs.append(HumanMessage(content=content))
                case "bot":
                    msgs.append(
                        AIMessage(
                            content=content, additional_kwargs={"bot name": bot_name}
                        )
                    )
                case "other bot":
                    if settings.llm_includes_other_bot_messages:
                        msgs.append(
                            HumanMessage(
                                content=f"[Bot: {bot_name}] {content}",
                                additional_kwargs={"bot name": bot_name},
                            )
                        )
                case "other":
                    pass
                case _:
                    logger.warning(f"Unknown role: {role}")

        return msgs


async def _socket_mode_main(main: Main, app_token: Optional[str]) -> None:
    logger.info("Socket mode starting...")

    await main.setup()

    handler = AsyncSocketModeHandler(main.slack_app(), app_token)

    try:
        await handler.start_async()
    except asyncio.CancelledError:
        logger.info("Socket mode handler cancelled")
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt")
    except Exception as e:
        logger.error(f"Socket mode handler error: {e}")
        logger.debug(traceback.format_exc())

    await handler.close_async()
    await main.cleanup()


def _http_server_main(settings: Settings) -> None:
    logger.info("HTTP server starting...")

    try:
        uvicorn.run(
            app="main:server_app",
            host="0.0.0.0",
            port=settings.port if settings.port else 80,
            reload=settings.is_development,
        )
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt")
    except Exception as e:
        logger.error(f"HTTP server error: {e}")
        logger.debug(traceback.format_exc())


logger.info(f"App main: {__name__=}")

settings = Settings()
slack_settings = SlackSettings()
llm_settings = LLMSettings()

if __name__ == "__main__":
    # python app/main.py で実行する場合
    if slack_settings.is_socket_mode:
        main = Main(settings, slack_settings, llm_settings)
        asyncio.run(_socket_mode_main(main, slack_settings.app_token))
    else:
        _http_server_main(settings)
else:
    # Uvicorn からモジュールとしてインポートされて実行する場合
    if slack_settings.is_socket_mode:
        # HTTP サーバーを動かすのでソケットモードの場合はエラー
        logger.error(
            "Socket mode is not supported in HTTP server mode. "
            "Please set `SLACK_IS_SOCKET_MODE` to False in the settings."
        )
        raise RuntimeError("Socket mode is not supported in HTTP server mode.")

    main = Main(settings, slack_settings, llm_settings)
    # Uvicorn が参照する ASGI アプリケーションインスタンス
    server_app = main.server_app()
