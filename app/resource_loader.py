import os
from typing import Optional

import aiofiles
from loguru import logger


class ResourceLoader:
    def __init__(self, enable_logging: bool = False):
        """初期化

        Args:
            enable_logging (bool, optional): ログ出力を有効にするかどうか, Defaults to False.
        """
        if enable_logging:
            logger.enable(__name__)
        else:
            logger.disable(__name__)

    async def load_plane_text(self, file_path: Optional[str]) -> str:
        """ファイルからプレーンテキストを読み込む

        Args:
            file_path (Optional[str]): ファイルパス

        Returns:
            str: テキスト
        """
        txt = ""

        if not file_path:
            logger.info("File path not set")
            return txt

        if not os.path.isfile(file_path):
            logger.warning(f"File not found: {file_path}")
            return txt

        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as file:
                txt = await file.read()
        except Exception as e:
            logger.error(f"Failed to load file: {e}")

        return txt
