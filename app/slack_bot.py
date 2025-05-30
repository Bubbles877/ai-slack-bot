import asyncio
import json
import time
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
        # app_mention されたスレッドの thread_ts を保持するセット
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

    async def _handle_message(self, body: dict, say: AsyncSay) -> None:
        """'message' イベントを処理する

        Args:
            body (dict): リクエストボディ
            say (AsyncSay): メッセージ送信
        """
        logger.info(f"Message:\n{json.dumps(body, indent=2)}")
        start_time = time.perf_counter()

        event: dict = body.get("event", {})
        user_id: str = event.get("user", "")
        ts: str = event.get("ts", "")
        # thread_ts: str = event.get("thread_ts", "")
        thread_ts: str = event.get("thread_ts", ts)
        text: str = event.get("text", "")
        channel_id: str = event.get("channel", "")
        bot_id: str = event.get("bot_id", "")
        channel_type: str = event.get("channel_type", "")

        is_thread = bool(thread_ts and thread_ts != ts)

        if bot_id:
            logger.info(f"Bot message (bot_id: {bot_id}), ignoring.")
            return

        if not user_id:
            logger.debug("Message without user_id, ignoring.")
            return

        if user_id == self._bot_id:
            # 自分自身からのメンションは来ないかも
            logger.info(f"Ignoring message from self (user_id: {user_id}).")
            return

        # # ボットへのメンションがあるかチェック
        # is_bot_mentioned = self._is_bot_mentioned(text)

        # DM の場合は常に応答
        is_direct_message = channel_type == "im"

        # スレッド内でボットが以前に応答したことがあるかチェック
        # is_active_thread = thread_ts and thread_ts in self.active_threads
        is_active_thread = thread_ts in self.active_threads

        # if is_bot_mentioned or is_direct_message or is_active_thread:
        if not is_direct_message and not is_active_thread:
            logger.debug(
                f"Message from user {user_id} in channel {channel_id} ignored "
                f"(not DM, not in active thread): '{text}'"
            )
            return

        logger.info(
            f"Processing message from user {user_id} in channel {channel_id}"
            f"{f' (thread: {thread_ts})' if thread_ts else ''}: '{text}'"
            # f" | mentioned: {is_bot_mentioned}, DM: {is_direct_message}, active_thread: {is_active_thread}"
            f" | DM: {is_direct_message}, active_thread: {is_active_thread}"
        )

        # # 応答を決定するスレッドタイムスタンプ
        # response_thread_ts = thread_ts if thread_ts else ts

        # アクティブスレッドとして記録
        if not is_active_thread:
            self.active_threads.add(thread_ts)
            logger.debug(f"Thread {thread_ts} added to active_threads.")

        # 受け付けリアクションを追加
        try:
            await self.client.reactions_add(
                channel=channel_id,
                name="eyes",
                timestamp=ts,
            )
        except Exception as e:
            logger.error(f"Add reaction error: {e}")

        # 遅延処理（リアクション追加後に少し待つ）
        await asyncio.sleep(1)

        # メッセージ履歴を取得（スレッドの場合）
        history: list[SlackMessage] = []
        if is_thread:
            history = await self._get_thread_history(channel_id, thread_ts)

        try:
            res = await self._chat_callback(text, history)
            logger.debug(f"Response: {res}")

            if not res:
                res = "エラーが発生しました。しばらくしてから再度お試しください。"

            await say(
                text=f"<@{user_id}>\n{res}",
                thread_ts=thread_ts,
            )
            logger.debug(
                f"Response sent to thread {thread_ts} in channel {channel_id}."
            )
        except Exception as e:
            logger.error(f"Error processing chat: {e}")
            await say(
                text=f"<@{user_id}>\n申し訳ございません。処理中にエラーが発生しました。",
                thread_ts=thread_ts,
            )

        logger.info(
            f"Message processing done (executed in {time.perf_counter() - start_time:.2f}s)"
        )

    async def _handle_app_mentions(self, body: dict, say: AsyncSay) -> None:
        """'app_mention' イベントを処理する

        メンションある場合は、'message' と 'app_mention' が続けて来る。

        Args:
            body (dict): リクエストボディ
            say (AsyncSay): メッセージ送信
        """
        logger.info(f"App mentions:\n{json.dumps(body, indent=2)}")
        start_time = time.perf_counter()

        event: dict = body.get("event", {})
        user_id: str = event.get("user", "")
        ts: str = event.get("ts", "")  # 1748596312.340719
        # thread_ts: str = event.get("thread_ts", "")
        thread_ts: str = event.get("thread_ts", ts)
        text: str = event.get("text", "")
        channel: str = event.get("channel", "")

        # is_active_thread = thread_ts and thread_ts in self.active_threads
        if thread_ts in self.active_threads:
            logger.info(
                f"Thread {thread_ts} is already active, ignoring app mention from user {user_id}."
            )
            return

        self.active_threads.add(thread_ts)
        logger.debug(f"Thread {thread_ts} added to active_threads.")

        # TODO: この先の処理は共通化する

        try:
            await self.client.reactions_add(
                channel=channel,
                name="eyes",
                timestamp=thread_ts,
            )
        except Exception as e:
            logger.error(f"Add reaction error: {e}")

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
            thread_ts=thread_ts,
        )

        logger.info(
            f"App mention done (executed in {time.perf_counter() - start_time:.2f}s)"
        )

    # def _is_bot_mentioned(self, text: str) -> bool:
    #     """ボットがメンションされているかチェックする

    #     Args:
    #         text (str): メッセージテキスト

    #     Returns:
    #         bool: メンションされている場合 True
    #     """
    #     if not self._bot_id:
    #         return False

    #     # <@U123456789> 形式のメンションをチェック
    #     # TODO: [event][blocks] リスト内の [elements] リスト内の [user_id] でも分かるかも
    #     return f"<@{self._bot_id}>" in text

    async def _get_thread_history(
        self, channel_id: str, thread_ts: str
    ) -> list[SlackMessage]:
        """スレッドの履歴を取得する

        Args:
            channel_id (str): チャンネルID
            thread_ts (str): スレッドタイムスタンプ

        Returns:
            list[SlackMessage]: メッセージ履歴
        """
        try:
            response = await self.client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                limit=20,  # 最新20件まで取得
            )
            # logger.debug(f"Thread history response: {response}")
            # 詳しくログを出力する
            logger.debug(
                f"Thread history response: {json.dumps(response, indent=2, ensure_ascii=False)}"
            )

            msgs: list[SlackMessage] = []
            for msg in response.get("messages", []):  # type: dict
                user_id = msg.get("user")
                bot_id = msg.get("bot_id")
                text = msg.get("text", "")

                if user_id == self._bot_id or bot_id:
                    # ボットのメッセージ
                    msgs.append({"role": "bot", "content": text})
                elif user_id:
                    # ユーザーのメッセージ
                    msgs.append({"role": "user", "content": text})

            return msgs
        except Exception as e:
            logger.error(f"Error getting thread history: {e}")
            return []
