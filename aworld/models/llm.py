import os
import time
from pathlib import Path

from langchain_anthropic import ChatAnthropic
from openai import OpenAI
from langchain_core.language_models.base import (
    LanguageModelInput,
)
from langchain_core.messages import (
    AIMessage,
    SystemMessage,
    BaseMessage, ChatMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_mistralai import ChatMistralAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_openai import AzureChatOpenAI, ChatOpenAI

from typing import (
    Any,
    Optional,
)

from aworld.config.conf import AgentConfig
from aworld.env_secrets import secrets


class DeepSeekR1ChatOpenAI(ChatOpenAI):

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.client = OpenAI(
            base_url=kwargs.get("base_url"),
            api_key=kwargs.get("api_key") or secrets.deep_seek_api_key
        )

    async def ainvoke(
            self,
            input: LanguageModelInput,
            config: Optional[RunnableConfig] = None,
            *,
            stop: Optional[list[str]] = None,
            **kwargs: Any,
    ) -> AIMessage:
        message_history = []
        for input_ in input:
            if isinstance(input_, SystemMessage):
                message_history.append({"role": "system", "content": input_.content})
            elif isinstance(input_, AIMessage):
                message_history.append({"role": "assistant", "content": input_.content})
            else:
                message_history.append({"role": "user", "content": input_.content})

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=message_history
        )

        reasoning_content = response.choices[0].message.reasoning_content
        content = response.choices[0].message.content
        return AIMessage(content=content, reasoning_content=reasoning_content)

    def invoke(
            self,
            input: LanguageModelInput,
            config: Optional[RunnableConfig] = None,
            *,
            stop: Optional[list[str]] = None,
            **kwargs: Any,
    ) -> AIMessage:
        message_history = []
        for input_ in input:
            if isinstance(input_, SystemMessage):
                message_history.append({"role": "system", "content": input_.content})
            elif isinstance(input_, AIMessage):
                message_history.append({"role": "assistant", "content": input_.content})
            else:
                message_history.append({"role": "user", "content": input_.content})

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=message_history
        )

        reasoning_content = response.choices[0].message.reasoning_content
        content = response.choices[0].message.content
        return AIMessage(content=content, reasoning_content=reasoning_content)


class DeepSeekR1ChatOllama(ChatOllama):

    async def ainvoke(
            self,
            input: LanguageModelInput,
            config: Optional[RunnableConfig] = None,
            *,
            stop: Optional[list[str]] = None,
            **kwargs: Any,
    ) -> AIMessage:
        org_ai_message = await super().ainvoke(input=input)
        org_content = org_ai_message.content
        reasoning_content = org_content.split("</think>")[0].replace("<think>", "")
        content = org_content.split("</think>")[1]
        if "**JSON Response:**" in content:
            content = content.split("**JSON Response:**")[-1]
        return AIMessage(content=content, reasoning_content=reasoning_content)

    def invoke(
            self,
            input: LanguageModelInput,
            config: Optional[RunnableConfig] = None,
            *,
            stop: Optional[list[str]] = None,
            **kwargs: Any,
    ) -> AIMessage:
        org_ai_message = super().invoke(input=input)
        org_content = org_ai_message.content
        reasoning_content = org_content.split("</think>")[0].replace("<think>", "")
        content = org_content.split("</think>")[1]
        if "**JSON Response:**" in content:
            content = content.split("**JSON Response:**")[-1]
        return AIMessage(content=content, reasoning_content=reasoning_content)


PROVIDER_DISPLAY_NAMES = {
    "openai": "OpenAI",
    "azure_openai": "Azure OpenAI",
    "anthropic": "Anthropic",
    "deepseek": "DeepSeek",
    "google": "Google",
    "alibaba": "Alibaba",
    "moonshot": "MoonShot"
}


def get_llm_model(conf: AgentConfig, **kwargs):
    provider = conf.llm_provider
    if provider not in ["ollama"]:
        env_var = f"{provider.upper()}_API_KEY"
        api_key = conf.llm_api_key if conf.llm_api_key else os.getenv(env_var, "")
        if not api_key:
            raise ValueError(f"Can not found {provider} api key! Please set the `{env_var}` "
                             f"environment variable or provide it in the UI.")
        kwargs["api_key"] = api_key
        kwargs['base_url'] = conf.llm_base_url

    if provider == "anthropic":
        if not kwargs.get("base_url", ""):
            base_url = "https://api.anthropic.com"
        else:
            base_url = kwargs.get("base_url")

        return ChatAnthropic(
            model_name=kwargs.get("model_name", "claude-3-5-sonnet-20241022"),
            temperature=kwargs.get("temperature", 0.0),
            base_url=base_url,
            api_key=api_key or secrets.claude_api_key,
        )
    elif provider == 'mistral':
        if not kwargs.get("base_url", ""):
            base_url = os.getenv("MISTRAL_ENDPOINT", "https://api.mistral.ai/v1")
        else:
            base_url = kwargs.get("base_url")
        if not kwargs.get("api_key", ""):
            api_key = os.getenv("MISTRAL_API_KEY", "")
        else:
            api_key = kwargs.get("api_key")

        return ChatMistralAI(
            model=kwargs.get("model_name", "mistral-large-latest"),
            temperature=kwargs.get("temperature", 0.0),
            base_url=base_url,
            api_key=api_key or secrets.mistral_api_key,
        )
    elif provider == "openai":
        if not kwargs.get("base_url", ""):
            base_url = os.getenv("OPENAI_ENDPOINT")
        else:
            base_url = kwargs.get("base_url")

        return ChatOpenAI(
            model=kwargs.get("model_name", "gpt-4o"),
            temperature=kwargs.get("temperature", 0.0),
            base_url=base_url,
            api_key=api_key or secrets.openai_api_key,
        )
    elif provider == "deepseek":
        if not kwargs.get("base_url", ""):
            base_url = os.getenv("DEEPSEEK_ENDPOINT", "")
        else:
            base_url = kwargs.get("base_url")

        if kwargs.get("model_name", "deepseek-chat") == "deepseek-reasoner":
            return DeepSeekR1ChatOpenAI(
                model=kwargs.get("model_name", "deepseek-reasoner"),
                temperature=kwargs.get("temperature", 0.0),
                base_url=base_url,
                api_key=api_key or secrets.deep_seek_api_key,
            )
        else:
            return ChatOpenAI(
                model=kwargs.get("model_name", "deepseek-chat"),
                temperature=kwargs.get("temperature", 0.0),
                base_url=base_url,
                api_key=api_key or secrets.deep_seek_api_key,
            )
    elif provider == "google":
        return ChatGoogleGenerativeAI(
            model=kwargs.get("model_name", "gemini-2.0-flash-exp"),
            temperature=kwargs.get("temperature", 0.0),
            google_api_key=api_key or secrets.google_api_key,
        )
    elif provider == "ollama":
        if not kwargs.get("base_url", ""):
            base_url = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434")
        else:
            base_url = kwargs.get("base_url")

        if "deepseek-r1" in kwargs.get("model_name", "qwen2.5:7b"):
            return DeepSeekR1ChatOllama(
                model=kwargs.get("model_name", "deepseek-r1:14b"),
                temperature=kwargs.get("temperature", 0.0),
                num_ctx=kwargs.get("num_ctx", 32000),
                base_url=base_url,
            )
        else:
            return ChatOllama(
                model=kwargs.get("model_name", "qwen2.5:7b"),
                temperature=kwargs.get("temperature", 0.0),
                num_ctx=kwargs.get("num_ctx", 32000),
                num_predict=kwargs.get("num_predict", 1024),
                base_url=base_url,
            )
    elif provider == "azure_openai":
        if not kwargs.get("base_url", ""):
            base_url = os.getenv("AZURE_OPENAI_ENDPOINT", "")
        else:
            base_url = kwargs.get("base_url")
        api_version = kwargs.get("api_version", "") or os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")
        return AzureChatOpenAI(
            model=kwargs.get("model_name", "gpt-4o"),
            temperature=kwargs.get("temperature", 0.0),
            api_version=api_version,
            azure_endpoint=base_url,
            api_key=api_key or secrets.azure_openai_api_key,
        )
    elif provider == "alibaba":
        if not kwargs.get("base_url", ""):
            base_url = os.getenv("ALIBABA_ENDPOINT", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        else:
            base_url = kwargs.get("base_url")

        return ChatOpenAI(
            model=kwargs.get("model_name", "qwen-plus"),
            temperature=kwargs.get("temperature", 0.0),
            base_url=base_url,
            api_key=api_key or secrets.qwen_api_key,
        )

    elif provider == "moonshot":
        return ChatOpenAI(
            model=kwargs.get("model_name", "moonshot-v1-32k-vision-preview"),
            temperature=kwargs.get("temperature", 0.0),
            base_url=os.getenv("MOONSHOT_ENDPOINT"),
            api_key=os.getenv("MOONSHOT_API_KEY") or secrets.moonshot_api_key,
        )
    else:
        raise ValueError(f"Unsupported provider: {provider}")


# Predefined model names for common providers
model_names = {
    "antgpt": ["gpt-4o"],
    "anthropic": ["claude-3-5-sonnet-20241022", "claude-3-5-sonnet-20240620", "claude-3-opus-20240229"],
    "openai": ["gpt-4o", "gpt-4", "gpt-3.5-turbo", "o3-mini", "gpt-4o-mini"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "ollama": ["qwen2.5:7b", "qwen2.5:14b", "qwen2.5:32b", "qwen2.5-coder:14b", "qwen2.5-coder:32b", "llama2:7b",
               "deepseek-r1:14b", "deepseek-r1:32b"],
    "alibaba": ["qwen-plus", "qwen-max", "qwen-turbo", "qwen-long"],
}
