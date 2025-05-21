from contextlib import asynccontextmanager
from typing import Awaitable, Callable, Optional

from fastapi import FastAPI, Request, Response
from loguru import logger
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler


class HTTPServer(FastAPI):
    """HTTP サーバー"""

    def __init__(
        self,
        request_handler: AsyncSlackRequestHandler,
        setup_callback: Optional[Callable[[], Awaitable[None]]] = None,
        cleanup_callback: Optional[Callable[[], Awaitable[None]]] = None,
        enable_logging: bool = False,
    ):
        """初期化

        Args:
            request_handler (AsyncSlackRequestHandler): リクエストハンドラー
            setup_callback (Optional[Callable[[], Awaitable[None]]], optional): セットアップのコールバック, Defaults to None.
            cleanup_callback (Optional[Callable[[], Awaitable[None]]], optional): 終了処理のコールバック, Defaults to None.
            enable_logging (bool, optional): ログ出力を有効にするかどうか, Defaults to False.
        """
        super().__init__(lifespan=self._lifespan_manager)

        if enable_logging:
            logger.enable(__name__)
        else:
            logger.disable(__name__)

        self._req_handler = request_handler
        self._setup_callback = setup_callback
        self._cleanup_callback = cleanup_callback

        self.add_api_route("/status", self._handle_status, methods=["GET"])
        self.add_api_route("/slack/events", self.handle_events, methods=["POST"])

        # self.state.

    @asynccontextmanager
    async def _lifespan_manager(self, app: FastAPI):
        # アプリケーション起動時に実行される
        if self._setup_callback:
            logger.info("Setting up...")
            await self._setup_callback()

            logger.info("Setup done.")

        yield

        # アプリケーション終了時に実行される
        if self._cleanup_callback:
            logger.info("Cleaning up...")
            await self._cleanup_callback()
            logger.info("Cleanup done.")

    async def _handle_status(self, req: Request) -> dict:
        """ステータス取得リクエストを処理する

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

    async def handle_events(self, req: Request) -> Response:
        """イベントを処理する

        Args:
            req (Request): リクエスト

        Returns:
            Response: レスポンス
        """
        return await self._req_handler.handle(req)
