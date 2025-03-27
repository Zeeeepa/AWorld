# coding: utf-8
# Copyright (c) 2025 inclusionAI.

import abc
import traceback
from typing import Dict, Tuple, Any, TypeVar, Generic, List, Union

from pydantic import BaseModel

from aworld.config.conf import ToolConfig, load_config
from aworld.core.envs.tool_action import ToolAction
from aworld.core.envs.action_factory import ActionFactory
from aworld.core.common import Observation, ActionModel, ActionResult, Tools
from aworld.core.factory import Factory
from aworld.logs.util import logger

AgentInput = TypeVar("AgentInput")
ToolInput = TypeVar("ToolInput")


class Tool(Generic[AgentInput, ToolInput]):
    """The basic generic classes of tools in the environment, with two parameterized types: AgentInput and ToolInput.

    We follow the gym/gymnasium protocol to be compatible with gym games, can also build special env tool in the framework.
    """
    __metaclass__ = abc.ABCMeta

    def __init__(self, conf: Union[Dict[str, Any], BaseModel], **kwargs) -> None:
        self.conf = conf
        if isinstance(conf, BaseModel):
            self.dict_conf = conf.model_dump()
        else:
            self.dict_conf = conf
        for k, v in kwargs.items():
            setattr(self, k, v)
        self._name = self.dict_conf.get("name", self.__class__.__name__)
        action_executor.register(name=self.name(), tool=self)
        self.action_executor = action_executor

    def name(self):
        """Tool unique name."""
        return self._name

    @abc.abstractmethod
    def reset(self, *, seed: int | None = None, options: Dict[str, str] | None = None) -> Tuple[
        AgentInput, dict[str, Any]]:
        """Resets the initial internal state, returning an initial state and extended info."""

    @abc.abstractmethod
    def step(self, action: ToolInput, **kwargs) -> Tuple[AgentInput, float, bool, bool, Dict[str, Any]]:
        """Run one step of the tool's in env using the actions.

        Args:
            action(ToolInput): Actions provided by the agent to update the observation.
        Return:
            Quintuple，key information: AgentInput and extended info dict.
        """

    @abc.abstractmethod
    def finished(self) -> bool:
        """The final execution status of the task from agent instructions."""

    @abc.abstractmethod
    def close(self) -> None:
        """Close the tool resources in the environment."""

    def render(self):
        """For interface compatibility."""
        pass


class AsyncTool(Generic[AgentInput, ToolInput]):
    """The basic generic classes of tools in the environment, with two parameterized types: AgentInput and ToolInput.

    We follow the gym/gymnasium protocol to be compatible with gym games, can also build special env tool in the framework.
    """
    __metaclass__ = abc.ABCMeta

    def __init__(self, conf: Union[Dict[str, Any], BaseModel], **kwargs) -> None:
        self.conf = conf
        if isinstance(conf, BaseModel):
            self.dict_conf = conf.model_dump()
        else:
            self.dict_conf = conf
        for k, v in kwargs.items():
            setattr(self, k, v)
        action_executor.register(name=self.name(), tool=self)
        self.action_executor = action_executor

    @abc.abstractmethod
    def name(self):
        """Tool unique name."""

    @abc.abstractmethod
    async def reset(self, *, seed: int | None = None, options: Dict[str, str] | None = None) -> Tuple[
        AgentInput, dict[str, Any]]:
        """Resets the initial internal state, returning an initial state and extended info."""

    @abc.abstractmethod
    async def step(self, action: ToolInput, **kwargs) -> Tuple[AgentInput, float, bool, bool, Dict[str, Any]]:
        """Run one step of the tool's in env using the actions.

        Args:
            action(ToolInput): Actions provided by the agent to update the observation.
        Return:
            Quintuple，key information: AgentInput and extended info dict.
        """

    @abc.abstractmethod
    async def finished(self) -> bool:
        """The final execution status of the task from agent instructions."""

    @abc.abstractmethod
    async def close(self) -> None:
        """Close the tool resources in the environment."""

    async def render(self):
        """For interface compatibility."""
        pass


class ToolsManager(Factory):
    def __init__(self, type_name: str = None):
        super(ToolsManager, self).__init__(type_name)
        self._tool_with_action = {}
        self._tool_conf = {}

    def __call__(self, name: str = None, *args, **kwargs):
        if name is None:
            return self

        asyn = kwargs.pop("asyn", False)
        name = "async_" + name if asyn else name

        conf = self._tool_conf.get(name)
        user_conf = kwargs.pop('conf', None)
        if user_conf:
            if isinstance(user_conf, BaseModel):
                conf.update(user_conf.model_dump())
            elif isinstance(user_conf, dict):
                conf.update(user_conf)
            else:
                logger.warning(f"Unknown conf type: {type(user_conf)}, ignored!")

        # must is a dict
        conf['name'] = name
        if name in self._cls:
            tool = self._cls[name](conf=conf, **kwargs)
        else:
            # default browser env tool
            logger.warning("Empty tool name, default use 'browser'")
            asyn = kwargs.get('async', False)
            if asyn:
                name = "async_" + Tools.BROWSER.value
            else:
                name = Tools.BROWSER.value
            tool = self._cls[name](conf=conf, **kwargs)
        action_executor.register(name, tool)
        return tool

    def get_tool_action(self, tool: str, asyn: bool = False):
        if asyn:
            tool = "async_" + tool
        return self._tool_with_action.get(tool)

    def register(self, name: str, desc: str, supported_action: ToolAction, conf_file_name: str = None, **kwargs):
        """Register a tool to tool factory.

        Args:
            name: Tool name
            desc: Tool description
            supported_action: Tool abilities
            conf_file_name: Default tool config
        """
        res = super(ToolsManager, self).register(name, desc, **kwargs)
        asyn = kwargs.pop("asyn", False)
        prefix = "async_" if asyn else ""
        conf_file_name = conf_file_name if conf_file_name else f"{name}_tool.yaml"
        conf = load_config(conf_file_name, kwargs.get("dir"))
        if not conf:
            logger.warning(f"can not load conf from {conf_file_name}")
            # use general tool config
            conf = ToolConfig()
        name = prefix + name
        self._tool_with_action[name] = supported_action
        self._tool_conf[name] = conf
        return res


ToolFactory = ToolsManager("env_tool_type")


class ToolActionExecutor(object):
    __metaclass__ = abc.ABCMeta

    def __init__(self, tool: Tool[Observation, List[ActionModel]] = None):
        self.tool = tool
        self.tools: Dict[str, Tool[Observation, List[ActionModel]]] = {}

    def register(
            self,
            name: str,
            tool: Union[Tool[Observation, List[ActionModel]], AsyncTool[Observation, List[ActionModel]]]):
        self.tools[name] = tool

    @abc.abstractmethod
    def execute_action(self, actions: List[ActionModel], **kwargs) -> Tuple[List[ActionResult], Any]:
        """"""
        return self.execute_env_action(actions, self.tool, **kwargs)

    @abc.abstractmethod
    async def async_execute_action(self, actions: List[ActionModel], **kwargs) -> Tuple[List[ActionResult], Any]:
        """"""
        return await self.async_execute_env_action(actions, self.tool, **kwargs)

    @abc.abstractmethod
    def execute_env_action(self,
                           actions: List[ActionModel],
                           tool: Tool[Observation, List[ActionModel]],
                           **kwargs) -> Tuple[List[ActionResult], Any]:
        """"""
        action_results = []
        ctx = None
        for action in actions:
            if action is None:
                logger.warning("empty action, ignore it.")
                continue

            if tool is None:
                tool_name = action.tool_name
                tool = self.tools.get(tool_name)
                if tool is None:
                    tool = ToolFactory(tool_name, conf=kwargs.get("conf", ToolConfig()))
                    self.tools[tool_name] = tool

            try:
                action_result, ctx = self.do_act(action, tool, **kwargs)
                action_results.append(action_result)
            except:
                logger.warning(traceback.format_exc())
        return action_results, ctx

    async def async_execute_env_action(self,
                                       actions: List[ActionModel],
                                       tool: Tool[Observation, List[ActionModel]],
                                       **kwargs) -> Tuple[List[ActionResult], Any]:
        """"""
        action_results = []
        ctx = None
        for action in actions:
            if action is None:
                logger.warning("empty action, ignore it.")
                continue

            if tool is None:
                tool_name = "async_" + action.tool_name
                tool = self.tools.get(tool_name)
                if tool is None:
                    tool = ToolFactory(tool_name, conf=kwargs.get("conf", ToolConfig()))
                    self.tools[tool_name] = tool
            try:
                action_result, ctx = await self.async_do_act(action, tool, **kwargs)
                action_results.append(action_result)
            except:
                logger.warning(traceback.format_exc())
        return action_results, ctx

    def do_act(self, action_model: ActionModel, tool: Tool[Observation, List[ActionModel]], **kwargs):
        action_name = action_model.action_name
        if action_name not in ActionFactory:
            action_name = action_model.tool_name + action_model.action_name
            if action_name not in ActionFactory:
                raise ValueError(f'Action {action_name} not found in ActionFactory')

        action = ActionFactory(action_name)
        action_result, page = action.act(action_model, tool=tool, **kwargs)
        logger.info(f"{tool.name()}-{action_name} execute finished")
        return action_result, page

    async def async_do_act(self, action_model: ActionModel, tool: Tool[Observation, List[ActionModel]],
                           **kwargs):
        action_name = action_model.action_name
        if action_name not in ActionFactory:
            action_name = action_model.tool_name + action_model.action_name
            if action_name not in ActionFactory:
                raise ValueError(f'Action {action_name} not found in ActionFactory')

        action = ActionFactory(action_name)
        action_result, page = await action.async_act(action_model, tool=tool, **kwargs)
        logger.info(f"{tool.name()}-{action_name} execute finished")
        return action_result, page


action_executor = ToolActionExecutor()
