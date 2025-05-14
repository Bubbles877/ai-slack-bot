import json
from typing import Optional

import uvicorn
from fastapi import FastAPI, Request
from loguru import logger
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler

_api: Optional[FastAPI] = None


class HTTPServer:
    """HTTP サーバー"""

    def __init__(
        self,
        port: Optional[int],
        request_handler: AsyncSlackRequestHandler,
        enable_logging: bool = False,
    ):
        """初期化

        Args:
            port (Optional[int]): ポート番号
            request_handler (AsyncSlackRequestHandler): リクエストハンドラー
            enable_logging (bool, optional): ログ出力を有効にするかどうか, Defaults to False.
        """
        if enable_logging:
            logger.enable(__name__)
        else:
            logger.disable(__name__)

        self._port = port
        self._req_handler = request_handler

        global _api
        self._api = FastAPI()
        _api = self._api
        # self._api.include_router(self._req_handler.app.router)

        @self._api.post("/slack/events")
        async def endpoint(req: Request):
            return await self._req_handler.handle(req)

        @self._api.get("/status")
        async def status(req: Request):
            """ステータス取得"""
            logger.info(f"status called: {req}")
            logger.info(f"status called: {repr(req)}")
            return json.dumps({"status": "healthy"})

    def run(self) -> None:
        """実行する"""
        uvicorn.run(
            # api,
            # app=self._api,
            # app="app.main:api",
            # app="main:api",
            # app="app.http_server:_api",
            app=f"{__name__}:_api",
            host="0.0.0.0",
            port=self._port if self._port else 80,
            reload=True,  # TODO: 本番環境では無効化
        )
