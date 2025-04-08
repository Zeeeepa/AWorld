# coding: utf-8
# Copyright (c) 2025 inclusionAI.

import abc
import copy
import json
import traceback
import uuid
from typing import Generic, TypeVar, Dict, Any, List, Tuple, Union

from openai import Stream
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openpyxl.styles.builtins import output

from aworld.core.agent.agent_desc import get_agent_desc
from aworld.core.envs.tool_desc import get_tool_desc
from aworld.logs.util import logger
from aworld.models.llm import get_llm_model
from pydantic import BaseModel

from aworld.config.conf import AgentConfig, load_config, ConfigDict
from aworld.core.common import Observation, ActionModel
from aworld.core.factory import Factory
from aworld.models.utils import tool_desc_transform, agent_desc_transform
from aworld.utils.common import convert_to_snake, is_abstract_method

INPUT = TypeVar('INPUT')
OUTPUT = TypeVar('OUTPUT')


def is_agent_by_name(name: str) -> bool:
    return name in AgentFactory


class AgentStatus:
    # Init status
    START = 0
    # Agent is running for monitor or collection
    RUNNING = 1
    # Agent reject the task
    REJECT = 2
    # Agent is idle
    IDLE = 3
    # Agent meets exception
    ERROR = 4
    # End of one agent step
    DONE = 5
    # End of one task step
    FINISHED = 6


class AgentResult(BaseModel):
    current_state: Any
    actions: List[ActionModel]
    is_call_tool: bool = True


class Agent(Generic[INPUT, OUTPUT]):
    __metaclass__ = abc.ABCMeta

    def __init__(self, conf: Union[Dict[str, Any], ConfigDict, AgentConfig], **kwargs):
        self.conf = conf
        if isinstance(conf, ConfigDict):
            pass
        elif isinstance(conf, Dict):
            self.conf = ConfigDict(conf)
        elif isinstance(conf, AgentConfig):
            # To add flexibility
            self.conf = ConfigDict(conf.model_dump())
        else:
            logger.warning(f"Unknown conf type: {type(conf)}")

        self._name = kwargs.pop("name", self.conf.get("name", convert_to_snake(self.__class__.__name__)))
        # Unique flag based agent name
        self.id = f"{self.name()}_{uuid.uuid1().hex[0:6]}"
        self.task = None
        # An agent can use the tool list
        self.tool_names: List[str] = kwargs.pop("tool_names", [])
        # An agent can delegate tasks to other agent
        self.handoffs: List[str] = kwargs.pop("agent_names", [])
        # Supported MCP server
        self.mcp_servers: List[str] = kwargs.pop("mcp_servers", [])
        self.trajectory: List[Tuple[INPUT, Dict[str, Any], AgentResult]] = []
        # all tools that the agent can use. note: string name/id only
        self._tools = []
        self.state = AgentStatus.START
        self._finished = False

        for k, v in kwargs.items():
            setattr(self, k, v)

    def name(self) -> str:
        """Agent name that must be implemented in subclasses"""
        return self._name

    @abc.abstractmethod
    def policy(self, observation: INPUT, info: Dict[str, Any] = None, **kwargs) -> OUTPUT:
        """The strategy of an agent can be to decide which tools to use in the environment, or to delegate tasks to other agents.

        Args:
            observation: The state observed from tools in the environment.
            info: Extended information is used to assist the agent to decide a policy.
        """

    @abc.abstractmethod
    async def async_policy(self, observation: INPUT, info: Dict[str, Any] = None, **kwargs) -> OUTPUT:
        """The strategy of an agent can be to decide which tools to use in the environment, or to delegate tasks to other agents.

        Args:
            observation: The state observed from tools in the environment.
            info: Extended information is used to assist the agent to decide a policy.
        """

    def reset(self, options: Dict[str, Any]):
        """Clean agent instance state and reset."""
        if options is None:
            options = {}
        self.task = options.get("task")
        self.tool_names = options.get("tool_names")
        self.handoffs = options.get("agent_names", [])
        self.trajectory = []
        self._finished = False

    async def async_reset(self, options: Dict[str, Any]):
        """Clean agent instance state and reset."""
        self.task = options.get("task")

    @property
    def finished(self) -> bool:
        """Agent finished the thing, default is True."""
        return self._finished


class BaseAgent(Agent[Observation, Union[Observation, List[ActionModel]]]):
    """Basic agent for unified protocol within the framework."""

    def __init__(self, conf: Union[Dict[str, Any], ConfigDict, AgentConfig], **kwargs):
        super(BaseAgent, self).__init__(conf, **kwargs)
        self.model_name = conf.llm_config.llm_model_name if conf.llm_config.llm_model_name else conf.llm_model_name
        self._llm = None
        self.memory = []
        self.system_prompt: str = kwargs.pop("system_prompt") if kwargs.get("system_prompt") else conf.system_prompt
        self.agent_prompt: str = kwargs.get("agent_prompt") if kwargs.get("agent_prompt") else conf.agent_prompt
        self.output_prompt: str =  kwargs.get("output_prompt") if kwargs.get("output_prompt") else conf.output_prompt

    @property
    def llm(self):
        # lazy
        if self._llm is None:
            conf = self.conf.llm_config if self.conf.llm_config.llm_provider else self.conf
            self._llm = get_llm_model(conf)
        return self._llm

    def desc_transform(self):
        """Transform of descriptions of supported tools, agents, and MCP servers in the framework to support function calls of LLM."""

        # Stateless tool
        self.tools = tool_desc_transform(get_tool_desc(),
                                         tools=self.tool_names if self.tool_names else [])
        # Agents as tool
        agents_desc = agent_desc_transform(get_agent_desc(),
                                           agents=self.handoffs if self.handoffs else [])
        self.tools.extend(agents_desc)
        # MCP servers are tool

    def messages_transform(self,
                           content: str,
                           image_urls: List[str] = None,
                           sys_prompt: str = None,
                           agent_prompt: str = None,
                           output_prompt: str = None,
                           max_step: int = 100,
                           **kwargs):
        """Transform the original content to LLM messages of native format.

        Args:
            content: User content.
            image_urls: List of images encoded using base64.
            sys_prompt: Agent system prompt.
            max_step: The maximum list length obtained from memory.
        Returns:
            Message list for LLM.
        """
        messages = []
        if sys_prompt:
            messages.append({'role': 'system', 'content': sys_prompt})

        if agent_prompt:
            content = agent_prompt.format(task=content)
        if output_prompt:
            content += output_prompt

        cur_msg = {'role': 'user', 'content': content}
        # query from memory, TODO: memory.query()
        histories = self.memory[-max_step:]
        if histories:
            for history in histories:
                if history.tool_calls:
                    messages.append({'role': 'assistant', 'content': '', 'tool_calls': history.tool_calls})
                else:
                    messages.append({'role': 'assistant', 'content': history.content})

            if histories[-1].tool_calls:
                tool_id = histories[-1].tool_calls[0].id
                if tool_id:
                    cur_msg['tool_call_id'] = tool_id

        if image_urls:
            urls = [{'type': 'text', 'text': content}]
            for image_url in image_urls:
                urls.append({'type': 'image_url', 'image_url': {"url": image_url}})

            cur_msg['content'] = urls
        messages.append(cur_msg)
        return messages

    def response_parse(self, resp: ChatCompletion | Stream[ChatCompletionChunk]) -> AgentResult:
        """Default parse response by LLM."""
        results = []
        if not resp or not resp.choices:
            logger.warning("LLM no valid response!")
            return AgentResult(actions=[], current_state=None)

        is_call_tool = False
        content = resp.choices[0].message.content
        if resp.choices[0].message.tool_calls:
            is_call_tool = True
            for tool_call in resp.choices[0].message.tool_calls:
                full_name: str = tool_call.function.name
                if not full_name:
                    logger.warning("tool call response no tool name.")
                    continue

                params = json.loads(tool_call.function.arguments)
                # format in framework
                names = full_name.split("__")
                tool_name = names[0]
                if is_agent_by_name(tool_name):
                    results.append(ActionModel(agent_name=tool_name, params=params, policy_info=content))
                else:
                    action_name = names[1] if len(names) > 1 else None
                    results.append(ActionModel(tool_name=tool_name,
                                               action_name=action_name,
                                               params=params,
                                               policy_info=content))
        else:
            if content:
                content = content.replace("```json", "").replace("```", "")
            # no tool call, agent name is itself.
            results.append(ActionModel(agent_name=self.name(), policy_info=content))
        return AgentResult(actions=results, current_state=None, is_call_tool=is_call_tool)

    @abc.abstractmethod
    def policy(self, observation: Observation, info: Dict[str, Any] = {}, **kwargs) -> Union[
        List[ActionModel], None]:
        """The strategy of an agent can be to decide which tools to use in the environment, or to delegate tasks to other agents.

        Args:
            observation: The state observed from tools in the environment.
            info: Extended information is used to assist the agent to decide a policy.

        Returns:
            ActionModel sequence from agent policy
        """

    @abc.abstractmethod
    async def async_policy(self, observation: Observation, info: Dict[str, Any] = {}, **kwargs) -> Union[
        List[ActionModel], None]:
        """The strategy of an agent can be to decide which tools to use in the environment, or to delegate tasks to other agents.

        Args:
            observation: The state observed from tools in the environment.
            info: Extended information is used to assist the agent to decide a policy.

        Returns:
            ActionModel sequence from agent policy
        """


class AgentManager(Factory):
    def __init__(self, type_name: str = None):
        super(AgentManager, self).__init__(type_name)
        self._agent_conf = {}

    def __call__(self, name: str = None, *args, **kwargs):
        if name is None:
            return self

        conf = self._agent_conf.get(name)
        if not conf:
            logger.warning(f"{name} not find conf in tool factory")
            conf = dict()
        elif isinstance(conf, BaseModel):
            conf = conf.model_dump()

        user_conf = kwargs.pop('conf', None)
        if user_conf:
            if isinstance(user_conf, BaseModel):
                conf.update(user_conf.model_dump())
            elif isinstance(user_conf, dict):
                conf.update(user_conf)
            else:
                logger.warning(f"Unknown conf type: {type(user_conf)}, ignored!")

        conf['name'] = name
        conf = ConfigDict(conf)
        if name in self._cls:
            agent = self._cls[name](conf=conf, **kwargs)
        else:
            raise ValueError(f"Can not find {name} agent!")
        return agent

    def register(self, name: str, desc: str, conf_file_name: str = None, **kwargs):
        """Register a tool to tool factory.

        Args:
            name: Tool name
            desc: Tool description
            supported_action: Tool abilities
            conf_file_name: Default tool config
        """
        res = super(AgentManager, self).register(name, desc, **kwargs)
        conf_file_name = conf_file_name if conf_file_name else f"{name}.yaml"
        conf = load_config(conf_file_name, kwargs.get("dir"))
        if not conf:
            logger.warning(f"{conf_file_name} not find, will use default")
            # use general tool config
            conf = AgentConfig().model_dump()
        self._agent_conf[name] = conf
        return res


AgentFactory = AgentManager("agent_type")


class AgentExecutor(object):
    """The default executor for agent execution can be used for sequential execution by the user."""

    def __init__(self, agent: BaseAgent = None):
        self.agent = agent
        self.agents: Dict[str, BaseAgent] = {}

    def register(self, name: str, agent: BaseAgent):
        self.agents[name] = agent

    def execute(self, observation: Observation, **kwargs) -> List[ActionModel]:
        """"""
        return self.execute_agent(observation, self.agent, **kwargs)

    async def async_execute(self, observation: Observation, **kwargs) -> List[ActionModel]:
        """"""
        return await self.async_execute_agent(observation, self.agent, **kwargs)

    def execute_agent(self,
                      observation: Observation,
                      agent: BaseAgent,
                      **kwargs) -> List[ActionModel]:
        """The synchronous execution process of the agent with some hooks.

        Args:
            observation: Observation source from a tool or an agent.
            agent: The special agent instance.
        """
        agent = self._get_or_create_agent(observation.to_agent_name, agent, kwargs.get('conf'))

        if is_abstract_method(agent, 'policy'):
            agent.desc_transform()
            images = observation.images
            if not images and observation.image:
                images = [observation.image]
            messages = agent.messages_transform(content=observation.content,
                                                image_urls=images,
                                                sys_prompt=agent.system_prompt,
                                                agent_prompt=agent.agent_prompt,
                                                output_prompt=agent.output_prompt)
            llm_response = None
            try:
                llm_response = agent.llm.chat.completions.create(
                    messages=messages,
                    model=agent.model_name,
                    **{'temperature': 0, 'tools': agent.tools},
                )
                logger.info(f"Execute response: {llm_response.choices[0].message}")
            except Exception as e:
                logger.warn(traceback.format_exc())
                raise e
            finally:
                if llm_response:
                    if llm_response.choices is None:
                        logger.info(f"llm result is None, info: {llm_response.model_extra}")
                    ob = copy.deepcopy(observation)
                    agent.memory.append((ob, llm_response))
                else:
                    logger.error(f"{agent.name()} failed to get LLM response")
                    raise RuntimeError(f"{agent.name()} failed to get LLM response")

            agent_result = agent.response_parse(llm_response)
            if not agent_result.is_call_tool:
                agent._finished = True
            return agent_result.actions
        else:
            try:
                actions = agent.policy(observation, kwargs)
                return actions
            except:
                logger.warning(traceback.format_exc())
                return [ActionModel(agent_name=agent.name())]

    async def async_execute_agent(self,
                                  observation: Observation,
                                  agent: BaseAgent,
                                  **kwargs) -> List[ActionModel]:
        """The asynchronous execution process of the agent.

        Args:
            observation: Observation source from a tool or an agent.
            agent: The special agent instance.
        """
        agent = self._get_or_create_agent(observation.to_agent_name, agent, kwargs.get('conf'))

        if is_abstract_method(agent, 'async_policy'):
            return [ActionModel(tool_name="", action_name="")]
        else:
            try:
                actions = await agent.async_policy(observation, kwargs)
                return actions
            except:
                logger.warning(traceback.format_exc())
                return [ActionModel(agent_name=agent.name())]

    def _get_or_create_agent(self, name: str, agent: BaseAgent = None, conf=None):
        if agent is None:
            agent = self.agents.get(name)
            if agent is None:
                agent = AgentFactory(name, conf=conf if conf else AgentConfig())
                self.agents[name] = agent
        return agent


agent_executor = AgentExecutor()
