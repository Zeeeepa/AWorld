import logging
import os
import json

from aworld.cmd import ChatCompletionRequest
from aworld.cmd.utils.aworld_ui import OpenAworldUI
from aworld.config.conf import AgentConfig, TaskConfig
from aworld.core.agent.llm_agent import Agent
from aworld.core.task import Task
from aworld.output.ui.base import AworldUI
from aworld.runner import Runners

logger = logging.getLogger(__name__)


class AWorldAgent:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def name(self):
        return "Powerful playwright agent"

    def description(self):
        return "Powerful playwright agent docs"

    async def run(self, prompt: str = None, request: ChatCompletionRequest = None):
        llm_provider = os.getenv("LLM_PROVIDER_PLAYWRIGHT", "openai")
        llm_model_name = os.getenv("LLM_MODEL_NAME_PLAYWRIGHT")
        llm_api_key = os.getenv("LLM_API_KEY_PLAYWRIGHT")
        llm_base_url = os.getenv("LLM_BASE_URL_PLAYWRIGHT")
        llm_temperature = os.getenv("LLM_TEMPERATURE_WEATHER", 0.0)

        if not llm_model_name or not llm_api_key or not llm_base_url:
            raise ValueError(
                "LLM_MODEL_NAME, LLM_API_KEY, LLM_BASE_URL must be set in your envrionment variables"
            )

        agent_config = AgentConfig(
            llm_provider=llm_provider,
            llm_model_name=llm_model_name,
            llm_api_key=llm_api_key,
            llm_base_url=llm_base_url,
            llm_temperature=llm_temperature,
        )

        path_cwd = os.path.dirname(os.path.abspath(__file__))
        mcp_path = os.path.join(path_cwd, "mcp.json")
        with open(mcp_path, "r") as f:
            mcp_config = json.load(f)

        super_agent = Agent(
            conf=agent_config,
            name="powerful_agent",
            system_prompt="You are a powerful weather agent, you can use playwright to do anything you want",
            mcp_config=mcp_config,
            mcp_servers=mcp_config.get("mcpServers", {}).keys(),
        )

        if prompt is None and request is not None:
            prompt = request.messages[-1].content

        task = Task(
            input=prompt,
            agent=super_agent,
            conf=TaskConfig(max_steps=20),
        )

        rich_ui = OpenAworldUI()
        async for output in Runners.streamed_run_task(task).stream_events():
            logger.info(f"Agent Output: {output}")
            res = await AworldUI.parse_output(output, rich_ui)
            for item in res if isinstance(res, list) else [res]:
                yield item
