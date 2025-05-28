import asyncio
from typing import Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from loguru import logger
from pydantic import SecretStr

from util.setting.llm_settings import LLMSettings


def enable_logging(enable: bool):
    """ログ出力を有効にする

    Args:
        enable (bool): ログ出力を有効にするかどうか
    """
    if enable:
        logger.enable(__name__)
    else:
        logger.disable(__name__)


def create_llm(settings: LLMSettings) -> Optional[BaseChatModel]:
    """LLM を生成する

    Args:
        settings (LLMSettings): LLM 設定

    Returns:
        Optional[BaseChatModel]: LLM
    """
    logger.debug(
        f"Create LLM:\n{settings.model_dump_json(indent=2, exclude={'api_key'})}"
    )

    llm: Optional[BaseChatModel] = None

    match settings.provider:
        case "azure":
            llm = AzureChatOpenAI(
                model=settings.name,
                azure_deployment=settings.deploy_name,
                azure_endpoint=settings.endpoint,
                api_key=SecretStr(settings.api_key) if settings.api_key else None,
                api_version=settings.api_ver,
                temperature=settings.temperature,
            )
        case "openai":
            llm = ChatOpenAI(
                model=settings.name,
                base_url=settings.endpoint,
                api_key=SecretStr(settings.api_key) if settings.api_key else None,
                temperature=settings.temperature,
            )
        case _:
            logger.error(f"Unsupported LLM provider: {settings.provider}")

    return llm


async def acreate_llm(settings: LLMSettings) -> Optional[BaseChatModel]:
    """LLM を生成する (非同期)

    Args:
        settings (LLMSettings): LLM 設定

    Returns:
        Optional[BaseChatModel]: LLM
    """
    return await asyncio.to_thread(create_llm, settings)
