import json
import time
import traceback
from typing import Awaitable, Callable, Literal, Optional, TypedDict

from loguru import logger
from redis.asyncio import Redis
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_bolt.async_app import AsyncApp, AsyncSay

from util.setting.slack_settings import SlackSettings


class SlackMessage(TypedDict):
    role: Literal["user", "bot", "other_bot", "other"]
    bot_name: Optional[str]
    content: str


class SlackBot(AsyncApp):
    """Slack Bot"""

    def __init__(
        self,
        settings: SlackSettings,
        chat_callback: Callable[[str, Optional[list[SlackMessage]]], Awaitable[str]],
        redis_client: Optional[Redis] = None,
        enable_logging: bool = False,
    ):
        """初期化

        Args:
            settings (SlackSettings): Slack 設定
            chat_callback (Callable[[str, Optional[list[SlackMessage]]], Awaitable[str]]): 会話のコールバック
            redis_client (Optional[Redis], optional): Redis クライアント, Defaults to None.
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
        self._redis_client = redis_client

        logger.debug(
            f"Settings:\n{self._settings.model_dump_json(indent=2, exclude={'app_token', 'bot_token', 'signing_secret'})}"
        )

        self._req_handler = AsyncSlackRequestHandler(self)

        self._bot_user_id: Optional[str] = None

        # 監視対象のスレッドを管理する
        # メンションされるか、ダイレクトメッセージの場合に thread_ts を記録する
        # 複数ワーカー間で共有するため Redis を利用する
        self._active_thread_key_prefix = "slack_bot:active_thread:"
        self._thread_ttl = 3600  # 1 時間の有効期限

        if self._redis_client is None:
            logger.info(
                "Redis client is not provided, using in-memory set for active threads"
            )
            self._active_threads: set[str] = set()

        self.event("message")(self._handle_message)
        self.event("app_mention")(self._handle_app_mention)

    async def setup(self) -> None:
        """セットアップする"""
        logger.debug("Setting up...")

        res = await self.client.auth_test()
        self._bot_user_id = res.get("user_id", "")
        logger.debug(f"Bot ID: {self._bot_user_id}")

        logger.debug("Setup done")

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
        logger.debug(f"Handle message:\n{json.dumps(body, indent=2)}")
        start_time = time.perf_counter()

        event: dict = body.get("event", {})
        user_id: str = event.get("user", "")
        bot_id: str = event.get("bot_id", "")

        if bot_id:
            logger.debug(f"Ignoring bot message (ID: {bot_id})")
            return

        if not user_id:
            logger.debug("Ignoring message without user ID")
            return

        ts: str = event.get("ts", "")
        thread_ts: str = event.get("thread_ts", ts)
        text: str = event.get("text", "")
        channel_id: str = event.get("channel", "")
        channel_type: str = event.get("channel_type", "")

        is_mentioned = False

        if blocks := event.get("blocks"):
            mentioned_users = self._extract_mentioned_users(blocks)
            is_mentioned = self._bot_user_id in mentioned_users

            # 自分の Bot ID にメンションが無く、他のユーザーにメンションがある場合は無視する
            if not is_mentioned and mentioned_users:
                logger.debug(
                    f"Message from user {user_id} in channel {channel_id} ignored "
                    f"(mentions other users {mentioned_users} but not this bot): '{text}'"
                )
                return

        is_direct_msg = channel_type == "im"
        is_active_thread = await self._is_active_thread(thread_ts)
        should_process = is_mentioned or is_direct_msg or is_active_thread

        if not should_process:
            logger.debug(
                f"Message from user {user_id} in channel {channel_id} ignored "
                f"(not mentioned, not DM, not in active thread): '{text}'"
            )
            return

        logger.debug(
            f"Processing message from user {user_id} in channel {channel_id}, thread {thread_ts}"
            f" (Mentioned: {is_mentioned}, DM: {is_direct_msg}, Active thread: {is_active_thread})\n"
            f"{text}"
        )

        if (is_mentioned or is_direct_msg) and not is_active_thread:
            # 監視スレッドとして登録する
            await self._add_active_thread(thread_ts)
            logger.debug(f"Thread {thread_ts} added to active threads")

        await self._process_message(text, channel_id, thread_ts, ts, say)

        logger.debug(
            f"Handle message done (executed in {time.perf_counter() - start_time:.2f}s)"
        )

    async def _handle_app_mention(self, body: dict, say: AsyncSay) -> None:
        """app_mention イベントを処理する

        Args:
            body (dict): リクエストボディ
            say (AsyncSay): メッセージ送信
        """
        logger.debug("Handle app mention")

        # TODO(you):
        #   メンションされた場合のみ応答したい場合は、message イベントを購読せず、
        #   この app_mention イベント用のメソッドで処理すると効率的

    async def _process_message(
        self,
        message: str,
        channel_id: str,
        thread_ts: str,
        message_ts: str,
        say: AsyncSay,
    ) -> None:
        try:
            # 応答に時間が掛かることを想定し、先ず即時にリアクションだけする
            await self.client.reactions_add(
                channel=channel_id, name="eyes", timestamp=message_ts
            )
        except Exception as e:
            logger.error(f"Add reaction error: {e}")

        history: list[SlackMessage] = []

        if thread_ts != message_ts:
            # スレッドの場合はメッセージ履歴を取得する
            history = await self._get_thread_history(channel_id, thread_ts, message_ts)

        res = ""

        try:
            res = await self._chat_callback(message, history)
            logger.debug(f"Response: {res}")

            if not res:
                res = "エラーが発生しました。しばらくしてから再度お試しください。"
        except Exception as e:
            logger.error(f"Error processing chat: {e}")
            logger.debug(traceback.format_exc())
            res = "エラーが発生しました。しばらくしてから再度お試しください。"

        await say(text=res, thread_ts=thread_ts)

    def _extract_mentioned_users(self, blocks: list[dict]) -> set[str]:
        mentioned_users: set[str] = set()

        for block in blocks:
            if block.get("type") != "rich_text":
                continue

            elements = block.get("elements", [])
            for element in elements:
                if element.get("type") != "rich_text_section":
                    continue

                sub_elements = element.get("elements", [])
                for sub_element in sub_elements:
                    if sub_element.get("type") != "user":
                        continue

                    if user_id := sub_element.get("user_id"):
                        mentioned_users.add(user_id)

        return mentioned_users

    async def _get_thread_history(
        self, channel_id: str, thread_ts: str, message_ts: str
    ) -> list[SlackMessage]:
        history: list[SlackMessage] = []

        try:
            res = await self.client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                latest=message_ts,  # イベントで受け取ったメッセージは含めずに履歴を取得する
                limit=self._settings.max_thread_messages,
            )
            logger.debug(
                f"Thread history:\n{json.dumps(res.data, indent=2, ensure_ascii=False)}"
            )

            msgs: list[dict] = res.get("messages", [])
            for msg in msgs:
                user_id: str = msg.get("user", "")
                bot_id: str = msg.get("bot_id", "")
                text: str = msg.get("text", "")
                bot_profile: dict = msg.get("bot_profile", {})
                bot_name: Optional[str] = bot_profile.get("name")

                role: Literal["user", "bot", "other_bot", "other"] = "other"

                if user_id == self._bot_user_id:
                    role = "bot"
                elif bot_id:
                    role = "other_bot"
                elif user_id:
                    role = "user"

                history.append({"role": role, "bot_name": bot_name, "content": text})

            return history
        except Exception as e:
            logger.error(f"Error getting thread history: {e}")
            logger.debug(traceback.format_exc())
            return history

    async def _add_active_thread(self, thread_ts: str) -> None:
        if self._redis_client is None:
            self._active_threads.add(thread_ts)
            return

        try:
            key = f"{self._active_thread_key_prefix}{thread_ts}"
            await self._redis_client.setex(key, self._thread_ttl, "1")
        except Exception as e:
            logger.error(f"Error adding active thread: {e}")

    async def _is_active_thread(self, thread_ts: str) -> bool:
        if self._redis_client is None:
            return thread_ts in self._active_threads

        try:
            key = f"{self._active_thread_key_prefix}{thread_ts}"
            return await self._redis_client.exists(key) == 1
        except Exception as e:
            logger.error(f"Error checking active thread: {e}")
            return False
