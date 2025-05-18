from loguru import logger
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_bolt.async_app import AsyncApp, AsyncSay

from util.setting.slack_settings import SlackSettings


class SlackBot(AsyncApp):
    """Slack Bot"""

    def __init__(self, settings: SlackSettings, enable_logging: bool = False):
        """初期化

        Args:
            slack_settings (SlackSettings): Slack 設定
            enable_logging (bool, optional): ログ出力を有効にするかどうか, Defaults to False.
        """
        super().__init__(
            token=settings.bot_token, signing_secret=settings.signing_secret
        )

        if enable_logging:
            logger.enable(__name__)
        else:
            logger.disable(__name__)

        self.slack_settings = settings

        self.req_handler = AsyncSlackRequestHandler(self)

        self.event("app_mention")(self._handle_app_mentions)
        self.event("message")(self._handle_message)

    def request_handler(self) -> AsyncSlackRequestHandler:
        """リクエストハンドラー

        Returns:
            AsyncSlackRequestHandler: リクエストハンドラー
        """
        return self.req_handler

    async def _handle_app_mentions(self, body: dict, say: AsyncSay) -> None:
        """'app_mention' イベントを処理する

        Args:
            body (dict): リクエストボディ
            say (AsyncSay): メッセージ送信
        """
        logger.info(body)
        await say("What's up?")

    async def _handle_message(self, body: dict, say: AsyncSay) -> None:
        """'message' イベントを処理する

        Args:
            body (dict): リクエストボディ
            say (AsyncSay): メッセージ送信
        """
        logger.info(f"message: {body}")
