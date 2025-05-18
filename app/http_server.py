from fastapi import FastAPI, Request, Response
from loguru import logger
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler


class HTTPServer(FastAPI):
    """HTTP サーバー"""

    def __init__(
        self,
        request_handler: AsyncSlackRequestHandler,
        enable_logging: bool = False,
    ):
        """初期化

        Args:
            request_handler (AsyncSlackRequestHandler): リクエストハンドラー
            enable_logging (bool, optional): ログ出力を有効にするかどうか, Defaults to False.
        """
        super().__init__()

        if enable_logging:
            logger.enable(__name__)
        else:
            logger.disable(__name__)

        self._req_handler = request_handler

        self.add_api_route("/status", self.status, methods=["GET"])
        self.add_api_route("/slack/events", self.events, methods=["POST"])

    async def status(self, req: Request) -> dict:
        """ステータス取得

        Args:
            req (Request): リクエスト

        Returns:
            dict: ステータス
        """
        logger.info("status")
        logger.info(f"Client host: {req.client.host if req.client else 'Unknown'}")
        logger.info(f"Request headers: {req.headers}")
        logger.info(f"Path parameters: {req.path_params}")
        logger.info(f"Query parameters: {req.query_params}")
        return {"status": "healthy"}

    async def events(self, req: Request) -> Response:
        """イベント

        Args:
            req (Request): リクエスト

        Returns:
            Response: レスポンス
        """
        return await self._req_handler.handle(req)
