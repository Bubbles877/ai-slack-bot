from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """LLM 設定

    環境変数から設定を読み込んで管理します。
    """

    provider: Optional[str] = None
    name: str
    deploy_name: Optional[str] = None
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    api_ver: Optional[str] = None
    temperature: Optional[float] = None

    # 注: 変えたい場合はコンストラクタで "_env_file" などで指定
    model_config = SettingsConfigDict(
        extra="ignore", env_prefix="LLM_", env_file=".env", env_file_encoding="utf-8"
    )
