import asyncio
import time
from typing import Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    SystemMessage,
    trim_messages,
)
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from loguru import logger


class LLMChat:
    """LLM チャット"""

    def __init__(
        self, llm: BaseChatModel, max_messages: int, enable_logging: bool = False
    ):
        """初期化

        Args:
            llm (BaseChatModel): LLM
            max_messages (int): LLM に渡す会話履歴の最大数 (<0: 無制限)
            enable_logging (bool, optional): ログ出力を有効にするかどうか, Defaults to False.
        """
        if enable_logging:
            logger.enable(__name__)
        else:
            logger.disable(__name__)

        self._llm = llm

        self._msgs_trimmer: Optional[
            RunnableLambda[list[AnyMessage], list[AnyMessage]]
        ] = None

        if max_messages >= 0:
            # システムメッセージ含めて max_messages 件残す
            self._msgs_trimmer = trim_messages(
                max_tokens=max_messages,
                token_counter=len,
                strategy="last",
                allow_partial=False,
                include_system=True,
            )

        self._instructions: str = ""

    def configure(self, instructions: str) -> None:
        """設定する

        Args:
            instructions (str): LLM への指示 (システムプロンプト)
        """
        self._instructions = instructions
        logger.debug(f"Instructions: {self._instructions}")

    def invoke(
        self, message: Optional[str] = None, history: Optional[list[AnyMessage]] = None
    ) -> str:
        """LLM を呼び出す

        Args:
            message (Optional[str]): メッセージ
            history (Optional[list[AnyMessage]]): 会話履歴

        Returns:
            str: LLM の応答メッセージ
        """
        msgs = self._build_messages(message, history)
        logger.debug(f"Input messages: {len(msgs)}")

        prompt = ChatPromptTemplate.from_messages(msgs)
        # prompt.pretty_print()
        chain = prompt | self._llm | StrOutputParser()

        result = ""

        try:
            start_time = time.perf_counter()
            result = chain.invoke({})
            logger.debug(
                f"LLM invocation time: {(time.perf_counter() - start_time):.2f}s"
            )
        except Exception as e:
            logger.error(f"LLM invocation failed: {e}")

        return result

    async def ainvoke(
        self, message: Optional[str] = None, history: Optional[list[AnyMessage]] = None
    ) -> str:
        """LLM を呼び出す (非同期)

        Args:
            message (Optional[str]): メッセージ
            history (Optional[list[AnyMessage]]): 会話履歴

        Returns:
            str: LLM の応答メッセージ
        """
        return await asyncio.to_thread(self.invoke, message, history)

    def _build_messages(
        self, message: Optional[str], history: Optional[list[AnyMessage]]
    ):
        msgs: list[AnyMessage] = [SystemMessage(content=self._instructions)]

        if history:
            msgs.extend(history)
        if message:
            msgs.append(HumanMessage(content=message))
        if self._msgs_trimmer:
            msgs = self._msgs_trimmer.invoke(msgs)

        return msgs
