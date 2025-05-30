import json
import time
import traceback
from typing import Awaitable, Callable, Literal, Optional, TypedDict

from loguru import logger
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_bolt.async_app import AsyncApp, AsyncSay

from util.setting.slack_settings import SlackSettings


class SlackMessage(TypedDict):
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
        # 監視対象のスレッド ID を保持するセット
        # app_mention で開始されるか、DM で開始された thread_ts を記録
        # TODO: 複数ワーカーでは共有できない -> Redis などに有効期限付きで登録して共有する
        self.active_threads: set[str] = set()

        self.event("message")(self._handle_message)
        self.event("app_mention")(self._handle_app_mention)

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

    async def _handle_message(self, body: dict, say: AsyncSay) -> None:
        """message イベントを処理する

        Args:
            body (dict): リクエストボディ
            say (AsyncSay): メッセージ送信
        """
        logger.info(f"Handle message:\n{json.dumps(body, indent=2)}")
        start_time = time.perf_counter()

        event: dict = body.get("event", {})
        user_id: str = event.get("user", "")
        bot_id: str = event.get("bot_id", "")
        ts: str = event.get("ts", "")
        thread_ts: str = event.get("thread_ts", ts)
        text: str = event.get("text", "")
        channel_id: str = event.get("channel", "")
        channel_type: str = event.get("channel_type", "")

        if bot_id:
            logger.info(f"Ignoring bot message (ID: {bot_id}).")
            return

        if not user_id:
            logger.info("Ignoring message without user ID.")
            return

        if user_id == self._bot_id:
            # 自分自身からのメンションは来ないかも
            logger.info(f"Ignoring message from self (ID: {user_id}).")
            return

        is_mentioned = self._is_bot_mentioned(text)
        is_direct_msg = channel_type == "im"
        is_active_thread = thread_ts in self.active_threads
        should_process = is_mentioned or is_direct_msg or is_active_thread

        if not should_process:
            logger.debug(
                f"Message from user {user_id} in channel {channel_id} ignored "
                f"(not mentioned, not DM, not in active thread): '{text}'"
            )
            return

        logger.info(
            f"Processing message from user {user_id} in channel {channel_id}"
            f"{f' (thread: {thread_ts})' if thread_ts != ts else ''}: '{text}'"
            f" | mentioned: {is_mentioned}, DM: {is_direct_msg}, active_thread: {is_active_thread}"
        )

        if (is_mentioned or is_direct_msg) and not is_active_thread:
            # 監視スレッドに登録する
            self.active_threads.add(thread_ts)
            logger.debug(f"Thread {thread_ts} added to active_threads.")

        await self._process_message(text, channel_id, thread_ts, ts, say)

        logger.info(
            f"Handle message done (executed in {time.perf_counter() - start_time:.2f}s)"
        )

    async def _handle_app_mention(self, body: dict, say: AsyncSay) -> None:
        """app_mention イベントを処理する

        Args:
            body (dict): リクエストボディ
            say (AsyncSay): メッセージ送信
        """
        logger.info("Handle app mention")

    async def _process_message(
        self, text: str, channel_id: str, thread_ts: str, ts: str, say: AsyncSay
    ) -> None:
        try:
            await self.client.reactions_add(
                channel=channel_id, name="eyes", timestamp=ts
            )
        except Exception as e:
            logger.error(f"Add reaction error: {e}")

        history: list[SlackMessage] = []

        if thread_ts != ts:
            # スレッドの場合はメッセージ履歴を取得する
            history = await self._get_thread_history(channel_id, thread_ts)

        res = ""

        try:
            res = await self._chat_callback(text, history)
            logger.debug(f"Response: {res}")

            if not res:
                res = "エラーが発生しました。しばらくしてから再度お試しください。"
        except Exception as e:
            logger.error(f"Error processing chat: {e}")
            logger.debug(traceback.format_exc())
            res = "エラーが発生しました。しばらくしてから再度お試しください。"

        await say(text=res, thread_ts=thread_ts)

    def _is_bot_mentioned(self, text: str) -> bool:
        if not self._bot_id:
            return False

        # <@U123456789> 形式のメンションをチェック
        # TODO: [event][blocks] リスト内の [elements] リスト内の [user_id] でも分かるかも
        return f"<@{self._bot_id}>" in text

    async def _get_thread_history(
        self, channel_id: str, thread_ts: str
    ) -> list[SlackMessage]:
        history: list[SlackMessage] = []

        try:
            # 最新 20 件まで取得
            res = await self.client.conversations_replies(
                channel=channel_id, ts=thread_ts, limit=20
            )
            logger.debug(
                f"Thread history:\n{json.dumps(res.data, indent=2, ensure_ascii=False)}"
            )

            msgs: list[dict] = res.get("messages", [])
            for msg in msgs:
                user_id = msg.get("user")
                bot_id = msg.get("bot_id")
                text = msg.get("text", "")

                if user_id == self._bot_id or bot_id:
                    history.append({"role": "bot", "content": text})
                elif user_id:
                    history.append({"role": "user", "content": text})

            return history
        except Exception as e:
            logger.error(f"Error getting thread history: {e}")
            logger.debug(traceback.format_exc())
            return history
