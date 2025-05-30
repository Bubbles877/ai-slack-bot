import json
import time
from typing import Awaitable, Callable, Literal, Optional, TypedDict

from loguru import logger
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_bolt.async_app import AsyncApp, AsyncSay

from util.setting.slack_settings import SlackSettings


class SlackMessage(TypedDict):
    # role: str  # "user" または "bot" を想定
    role: Literal["user", "bot"]
    content: str


class SlackBot(AsyncApp):
    """Slack Bot"""

    def __init__(
        self,
        settings: SlackSettings,
        chat_callback: Callable[[str, Optional[list[SlackMessage]]], Awaitable[str]],
        enable_logging: bool = False,
    ):
        """初期化

        Args:
            slack_settings (SlackSettings): Slack 設定
            chat_callback (Callable[[str, Optional[list[SlackMessage]]], Awaitable[str]]): 会話のコールバック
            enable_logging (bool, optional): ログ出力を有効にするかどうか, Defaults to False.
        """
        super().__init__(
            token=settings.bot_token, signing_secret=settings.signing_secret
        )

        if enable_logging:
            logger.enable(__name__)
        else:
            logger.disable(__name__)

        self._settings = settings
        self._chat_callback = chat_callback

        logger.debug(f"Settings:\n{self._settings.model_dump_json(indent=2)}")

        self._req_handler = AsyncSlackRequestHandler(self)

        self._bot_id: Optional[str] = None
        # app_mention で開始されたスレッドの event_ts を保持するセット
        # TODO: 複数ワーカーでは共有できない -> Redis などで共有する
        self.active_threads: set[str] = set()

        self.event("app_mention")(self._handle_app_mentions)
        self.event("message")(self._handle_message)

    async def setup(self) -> None:
        """セットアップする"""
        logger.debug("Setting up...")

        res = await self.client.auth_test()
        self._bot_id = res.get("user_id", "")
        logger.debug(f"Bot ID: {self._bot_id}")
        logger.debug("Setup done.")

    def request_handler(self) -> AsyncSlackRequestHandler:
        """リクエストハンドラー

        Returns:
            AsyncSlackRequestHandler: リクエストハンドラー
        """
        return self._req_handler

    async def _handle_app_mentions(self, body: dict, say: AsyncSay) -> None:
        """'app_mention' イベントを処理する

        Args:
            body (dict): リクエストボディ
            say (AsyncSay): メッセージ送信
        """
        # logger.info(f"App mentions: {body}")
        logger.info(f"App mentions:\n{json.dumps(body, indent=2)}")
        start_time = time.perf_counter()

        event: dict = body.get("event", {})
        user_id = event.get("user", "")
        # event_ts = event.get("ts", "")  # 1748596312.340719
        text = event.get("text", "")
        channel = event.get("channel", "")
        event_ts = event.get("event_ts", "")  # 1748596312.340719

        if event_ts:
            self.active_threads.add(event_ts)
            logger.info(f"Thread {event_ts} added to active_threads by user {user_id}.")

        try:
            await self.client.reactions_add(
                channel=channel,
                name="eyes",
                timestamp=event_ts,
            )
        except Exception as e:
            logger.error(f"Add reaction error: {e}")

        # if not self._bot_id:
        #     auth: dict = body.get("authorizations", [{}])[0]
        #     logger.info(f"Auth: {json.dumps(auth, indent=2)}")
        #     if auth.get("is_bot"):
        #         bot_user_id = auth.get("user_id")
        #         logger.info(f"Bot user ID: {bot_user_id}")
        #         if bot_user_id != self._bot_id:
        #             logger.warning(
        #                 f"Bot user ID {bot_user_id} does not match the bot ID {self._bot_id}."
        #             )

        # TODO: 仮
        # await asyncio.sleep(2)

        if user_id == self._bot_id:
            # 自分自身からのメンションは来ないかも
            logger.info(f"Ignoring app mention from self (user_id: {user_id}).")
            return

        history: list[SlackMessage] = []

        res = await self._chat_callback(text, history)
        logger.debug(f"Response: {res}")

        if not res:
            res = "エラーが発生しました。しばらくしてから再度お試しください。"
        await say(
            text=f"<@{user_id}>\n{res}",
            thread_ts=event_ts,
        )
        logger.debug(f"Response sent to thread {event_ts} in channel {channel}.")
        # await say(
        #     text=f"<@{user_id}> さん、メンションありがとうございます！このスレッドで続きをどうぞ。",
        #     thread_ts=event_ts,
        # )

        logger.info(
            f"App mention done (executed in {time.perf_counter() - start_time:.2f}s)"
        )

    async def _handle_message(self, body: dict, say: AsyncSay) -> None:
        """'message' イベントを処理する

        Args:
            body (dict): リクエストボディ
            say (AsyncSay): メッセージ送信
        """
        # logger.info(f"Message: {body}")
        logger.info(f"Message:\n{json.dumps(body, indent=2)}")

        event: dict = body.get("event", {})
        user_id: str = event.get("user", "")
        ts: str = event.get("ts", "")
        thread_ts: str = event.get("thread_ts", "")
        text: str = event.get("text", "")
        channel_id: str = event.get("channel", "")
        event_ts: str = event.get("event_ts", "")
        bot_id: str = event.get("bot_id", "")
        # event_subtype = event.get("subtype") # message_changed, thread_broadcast など

        # TODO: "channel_type": "im" ならメンションなくても返答するとか

        if bot_id:
            logger.info(f"Bot message (bot_id: {bot_id}), ignoring.")
            return

        if user_id and thread_ts and thread_ts in self.active_threads:
            logger.info(
                f"Message from user {user_id} in active thread {thread_ts} (channel {channel_id}): '{text}'"
            )

            if "ありがとう" in text:
                await say(text="どういたしまして！", thread_ts=thread_ts)
            elif "進捗" in text:
                await say(text="順調に進んでいます。", thread_ts=thread_ts)
            elif text.lower() == "終了":
                await say(
                    text="このスレッドでの対応を終了します。ありがとうございました。",
                    thread_ts=thread_ts,
                )

                if thread_ts in self.active_threads:
                    self.active_threads.remove(thread_ts)
                    logger.info(f"Thread {thread_ts} removed from active_threads.")
            else:
                await say(
                    text=f"スレッド内で「{text}」と発言しましたね。",
                    thread_ts=thread_ts,
                )
        elif user_id and thread_ts:
            logger.debug(
                f"Message from user {user_id} in non-active thread {thread_ts} (channel {channel_id}): '{text}'"
            )
        elif user_id:
            logger.debug(
                f"Message from user {user_id} in channel {channel_id} (not in a thread): '{text}'"
            )
