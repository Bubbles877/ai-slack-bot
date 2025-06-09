from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class SlackSettings(BaseSettings):
    """Slack 設定

    環境変数から設定を読み込んで管理します。
    """

    is_socket_mode: Optional[bool] = None
    app_token: Optional[str] = None
    bot_token: str
    signing_secret: Optional[str] = None
    max_thread_messages: int = 15

    # 注: 変えたい場合はコンストラクタで "_env_file" などで指定
    model_config = SettingsConfigDict(
        extra="ignore",
        env_prefix="SLACK_",
        env_file=".env",
        env_file_encoding="utf-8",
    )
