# coding: utf-8
# Copyright (c) 2025 inclusionAI.
import time

import traceback

import uuid
from typing import Union, Dict, Any, List
from dataclasses import dataclass, field

from aworld.config.conf import AgentConfig
from pydantic import BaseModel

from aworld.config import ConfigDict
from aworld.core.agent.base import Agent, agent_executor, is_agent_by_name, AgentFactory
from aworld.core.common import Observation, ActionModel
from aworld.core.envs.tool import Tool, ToolFactory
from aworld.core.agent.swarm import Swarm
from aworld.core.envs.tool_desc import is_tool_by_name
from aworld.logs.util import logger, color_log


@dataclass
class TaskModel:
    name: str = uuid.uuid1().hex
    input: Any = None
    conf: Union[Dict[str, Any], BaseModel] = None
    tools: List[Tool] = field(default_factory=list)
    tool_names: List[str] = field(default_factory=list)
    tools_conf: Dict[str, Union[Dict[str, Any], ConfigDict, AgentConfig]] = field(default_factory=dict)
    swarm: Swarm = None
    agent: Agent = None


class Task(object):
    def __init__(self,
                 task: TaskModel = None,
                 agent: Agent = None,
                 swarm: Swarm = None,
                 name: str = uuid.uuid1().hex,
                 input: Any = None,
                 conf: Union[Dict[str, Any], BaseModel] = {},
                 tools: List[Tool] = [],
                 tool_names: List[str] = [],
                 tools_conf: Dict[str, Union[Dict[str, Any], ConfigDict, AgentConfig]] = {},
                 *args,
                 **kwargs):
        """Task instance init.

        Args:
            task: Task model
            agent: Agent instance which want to run.
            swarm: Swarm
            name: Task unique name
            input: A string query or dataset.
            conf: Task config in process.
            tools: Special tools in task run.
        """
        # Prioritize using the task model.
        if task:
            agent = task.agent
            swarm = task.swarm
            name = task.name
            input = task.input
            conf = task.conf
            tools = task.tools
            tool_names = task.tool_names
            if tools is None:
                tools = []
            if tool_names is None:
                tool_names = []

        if not agent and not swarm:
            raise ValueError("agent and swarm all is None.")
        if agent and swarm:
            raise ValueError("agent and swarm choose one only.")
        if agent:
            # uniform agent
            swarm = Swarm(agent)

        if conf is None:
            conf = dict()
        if isinstance(conf, BaseModel):
            conf = conf.model_dump()
        check_input = conf.get("check_input", False)
        if check_input and not input:
            raise ValueError

        self.swarm = swarm
        self.input = input
        self.name = name
        self.conf = conf
        self.tools = {tool.name(): tool for tool in tools} if tools else {}
        tool_names.extend(self.tools.keys())
        # lazy load
        self.tool_names = tool_names
        self.tools_conf = tools_conf

        self.daemon_target = kwargs.pop('daemon_target', None)
        self._use_demon = False if not conf else conf.get('use_demon', False)
        self._exception = None
        for k, v in kwargs.items():
            setattr(self, k, v)

    def before_run(self):
        pass

    def after_run(self):
        pass

    def start(self) -> Any:
        try:
            self.before_run()
            self._daemon_run()
            ret = self.run()
            return 0 if ret is None else ret
        except BaseException as ex:
            self._exception = ex
            # do record or report
            raise ex
        finally:
            self.after_run()

    def _daemon_run(self) -> None:
        if self._use_demon and self.daemon_target and callable(self.daemon_target):
            import threading
            t = threading.Thread(target=self.daemon_target, name="daemon")
            t.setDaemon(True)
            t.start()

    def run(self):
        # init tool state by reset(), and ignore them observation
        observation = None
        info = dict()
        if self.tools:
            for _, tool in self.tools.items():
                # use the observation and info of the last one
                observation, info = tool.reset()

        if observation:
            if not observation.content:
                observation.content = self.input
        else:
            observation = Observation(content=self.input)

        self.swarm.reset(self.tool_names)
        for agent in self.swarm.agents.values():
            agent.reset({"task": observation.content,
                         "tool_names": agent.tool_names,
                         "agent_names": agent.handoffs,
                         "mcp_servers": agent.mcp_servers})
            # global tools
            agent.tool_names.extend(self.tool_names)

        if self.swarm.topology_type == 'social':
            return self._social_process(observation, info)
        elif self.swarm.topology_type == 'sequence':
            return self._sequence_process(observation, info)

    def _sequence_process(self, observation: Observation, info: Dict[str, Any]):
        """Multi-agent sequence general process workflow.

        NOTE: Use the agent‘s finished state(no tool calls) to control the inner loop.
        Args:
            observation: Observation based on env
            info: Extend info by env
        """
        if not observation:
            raise RuntimeError("no observation, check run process")

        start = time.time()
        step = 0
        max_steps = self.conf.get("max_steps", 100)
        msg = None

        for i in range(self.swarm.max_steps):
            for idx, agent in enumerate(self.swarm.ordered_agents):
                observations = [observation]
                policy = None
                cur_agent = agent
                while step < max_steps:
                    terminated = False

                    observation = self.swarm.action_to_observation(policy, observations)
                    policy: List[ActionModel] = cur_agent.executor.execute_agent(observation,
                                                                                 agent=cur_agent,
                                                                                 conf=cur_agent.conf,
                                                                                 step=step)
                    observation.content = None
                    color_log(f"{cur_agent.name()} policy: {policy}")
                    if not policy:
                        logger.warning(f"current agent {cur_agent.name()} no policy to use.")
                        return {"msg": f"current agent {cur_agent.name()} no policy to use.",
                                "steps": step,
                                "success": False,
                                "time_cost": (time.time() - start)}

                    if self.is_agent(policy[0]):
                        status, info = self._agent(agent, observation, policy, step)
                        if status == 'normal':
                            if info:
                                observations.append(observation)
                        elif status == 'break':
                            observation = self.swarm.action_to_observation(policy, observations)
                            break
                        elif status == 'return':
                            return info
                    elif is_tool_by_name(policy[0].tool_name):
                        self._tool_call(policy, observations, step)
                    else:
                        logger.warning(f"Unrecognized policy: {policy[0]}")
                        return {"msg": f"Unrecognized policy: {policy[0]}, need to check prompt or agent / tool.",
                                "response": "",
                                "steps": step,
                                "success": False}
                    step += 1
                    if terminated and agent.finished:
                        logger.info("swarm finished")
                        break
        return {"steps": step,
                "answer": observation.content,
                "observation": observation,
                "msg": msg,
                "success": True if not msg else False}

    def _agent(self, agent: Agent, observation: Observation, policy: List[ActionModel], step: int):
        # only one agent, and get agent from policy
        policy_for_agent = policy[0]
        cur_agent: Agent = self.swarm.agents.get(policy_for_agent.agent_name)
        if not cur_agent:
            raise RuntimeError(f"Can not find {policy_for_agent.agent_name} agent in swarm.")

        status = "normal"
        if cur_agent.name() == agent.name():
            # Current agent is entrance agent, means need to exit to the outer loop
            logger.warning(f"{cur_agent.name()} exit the loop")
            status = "break"
            return status, None

        if agent.handoffs and policy_for_agent.agent_name not in agent.handoffs:
            # Unable to hand off, exit to the outer loop
            status = "return"
            return status, {"msg": f"Can not handoffs {policy_for_agent.agent_name} agent "
                                   f"by {agent.name()} agent.",
                            "response": policy[0].policy_info if policy else "",
                            "steps": step,
                            "success": False}
        # Check if current agent done
        if cur_agent.finished:
            cur_agent._finished = False
            logger.info(f"{cur_agent.name()} agent be be handed off, so finished state reset to False.")

        con = policy_for_agent.policy_info
        if policy_for_agent.params and 'content' in policy_for_agent.params:
            con = policy_for_agent.params['content']
        if observation:
            observation.content = con
        else:
            observation = Observation(content=con)
            return status, observation
        return status, None

    def _tool_call(self, policy: List[ActionModel], observations: List[Observation], step: int):
        msg = None
        # group action by tool name
        tool_mapping = dict()
        # Directly use or use tools after creation.
        for act in policy:
            if not self.tools or (self.tools and act.tool_name not in self.tools):
                # dynamic only use default config in module.
                conf = self.tools_conf.get(act.tool_name)
                tool = ToolFactory(act.tool_name, conf=conf)
                tool.reset()
                tool_mapping[act.tool_name] = []
                self.tools[act.tool_name] = tool
            if act.tool_name not in tool_mapping:
                tool_mapping[act.tool_name] = []
            tool_mapping[act.tool_name].append(act)

        for tool_name, action in tool_mapping.items():
            # Execute action using browser tool and unpack all return values
            observation, reward, terminated, _, info = self.tools[tool_name].step(action)
            observations.append(observation)

            logger.info(f'{action} state: {observation}; reward: {reward}')
            # Check if there's an exception in info
            if info.get("exception"):
                color_log(f"Step {step} failed with exception: {info['exception']}")
                msg = f"Step {step} failed with exception: {info['exception']}"
            logger.info(f"step: {step} finished by tool action.")
        return msg

    def _social_process(self,
                        observation: Observation,
                        info: Dict[str, Any]) -> Dict[str, Any]:
        start = time.time()

        step = 0
        max_steps = self.conf.get("max_steps", 100)
        results = []
        swarm_resp = None
        try:
            while step < max_steps:
                # Loose protocol
                result_dict = self._process(observation=observation, info=info)
                results.append(result_dict)

                swarm_resp = result_dict.get("response")
                logger.info(f"Step: {step} response:\n {result_dict}")

                step += 1
                if self.swarm.finished:
                    logger.info("task done!")
                    break

                if not swarm_resp:
                    logger.warning(f"Step: {step} swarm no valid response")
                    break

                observation = result_dict.get("observation")
                if not observation:
                    observation = Observation(content=swarm_resp)
                else:
                    observation.content = swarm_resp

            time_cost = time.time() - start
            if not results:
                logger.warning("task no result!")
                return {"answer": "",
                        "traceback": traceback.format_exc(),
                        "steps": step,
                        "success": False,
                        "total_time": time_cost}

            answer = results[-1].get('observation').content if results[-1].get('observation') else swarm_resp
            return {"answer": answer,
                    "steps": step,
                    "success": True,
                    "total_time": (time.time() - start)}
        except Exception as e:
            logger.error(f"Task execution failed with error: {str(e)}\n{traceback.format_exc()}")
            return {"msg": str(e),
                    "traceback": traceback.format_exc(),
                    "steps": step,
                    "success": False,
                    "total_time": (time.time() - start)}

    def is_agent(self, policy: ActionModel):
        return is_agent_by_name(policy.tool_name) or (not policy.tool_name and not policy.action_name)

    def _process(self, observation, info) -> Dict[str, Any]:
        """Multi-agent general process workflow.

        NOTE: Use the agent‘s finished state to control the loop, so the agent must carefully set finished state.
        Args:
            observation: Observation based on env
            info: Extend info by env
        """
        if not self.swarm.initialized:
            raise RuntimeError("swarm needs to use `reset` to init first.")

        start = time.time()
        step = 0
        max_steps = self.conf.get("max_steps", 100)
        self.swarm.cur_agent = self.swarm.communicate_agent
        # use communicate agent every time
        policy: List[ActionModel] = self.swarm.cur_agent.executor.execute_agent(observation,
                                                                                agent=self.swarm.cur_agent,
                                                                                conf=self.swarm.cur_agent.conf,
                                                                                step=step)
        if not policy:
            logger.warning(f"current agent {self.swarm.cur_agent.name()} no policy to use.")
            return {"msg": f"current agent {self.swarm.cur_agent.name()} no policy to use.",
                    "steps": step,
                    "success": False,
                    "time_cost": (time.time() - start)}

        msg = None
        response = None
        return_entry = False
        cur_agent = None
        finished = False
        try:
            while step < max_steps:
                terminated = False
                if self.is_agent(policy[0]):
                    status, info = self._social_agent(policy, step)
                    if status == 'normal':
                        self.swarm.cur_agent = self.swarm.agents.get(policy[0].agent_name)
                        policy = info
                    # clear observation
                    observation = None
                elif is_tool_by_name(policy[0].tool_name):
                    status, info = self._social_tool_call(policy, step)
                    if status == 'normal':
                        observation = info
                else:
                    logger.warning(f"Unrecognized policy: {policy[0]}")
                    return {"msg": f"Unrecognized policy: {policy[0]}, need to check prompt or agent / tool.",
                            "response": "",
                            "steps": step,
                            "success": False}

                if status == 'break':
                    return_entry = info
                    break
                elif status == 'return':
                    return info

                step += 1
                if terminated and self.swarm.cur_agent.finished:
                    logger.info("swarm finished")
                    break

                if observation:
                    if cur_agent is None:
                        cur_agent = self.swarm.cur_agent
                    policy = agent_executor.execute_agent(observation,
                                                          agent=cur_agent,
                                                          conf=cur_agent.conf,
                                                          step=step)

            if policy:
                response = policy[0].policy_info if policy[0].policy_info else policy[0].action_name

            # All agents or tools have completed their tasks
            if all(agent.finished for _, agent in self.swarm.agents.items()) or (all(
                    tool.finished for _, tool in self.tools.items()) and len(self.swarm.agents) == 1):
                logger.info("entry agent finished, swarm process finished.")
                finished = True

            if return_entry and not finished:
                # Return to the entrance, reset current agent finished state
                self.swarm.cur_agent._finished = False
            return {"steps": step,
                    "response": response,
                    "observation": observation,
                    "msg": msg,
                    "success": True if not msg else False}
        except Exception as e:
            logger.error(f"Task execution failed with error: {str(e)}\n{traceback.format_exc()}")
            return {
                "msg": str(e),
                "response": "",
                "traceback": traceback.format_exc(),
                "steps": step,
                "success": False
            }

    def _social_agent(self, policy: List[ActionModel], step):
        # only one agent, and get agent from policy
        policy_for_agent = policy[0]
        cur_agent: Agent = self.swarm.agents.get(policy_for_agent.agent_name)
        if not cur_agent:
            raise RuntimeError(f"Can not find {policy_for_agent.agent_name} agent in swarm.")

        if cur_agent.name() == self.swarm.communicate_agent.name():
            # Current agent is entrance agent, means need to exit to the outer loop
            logger.warning("Exit to the outer loop")
            return 'break', True

        if self.swarm.cur_agent.handoffs and policy_for_agent.agent_name not in self.swarm.cur_agent.handoffs:
            # Unable to hand off, exit to the outer loop
            return "return", {"msg": f"Can not handoffs {policy_for_agent.agent_name} agent "
                                     f"by {cur_agent.name()} agent.",
                              "response": policy[0].policy_info if policy else "",
                              "steps": step,
                              "success": False}
        # Check if current agent done
        if cur_agent.finished:
            cur_agent._finished = False
            logger.info(f"{cur_agent.name()} agent be be handed off, so finished state reset to False.")

        observation = Observation(content=policy_for_agent.policy_info)
        agent_policy = cur_agent.executor.execute_agent(observation,
                                                        agent=cur_agent,
                                                        conf=cur_agent.conf,
                                                        step=step)

        if not agent_policy:
            logger.warning(
                f"{observation} can not get the valid policy in {policy_for_agent.agent_name}, exit task!")
            return "return", {"msg": f"{policy_for_agent.agent_name} invalid policy",
                              "response": "",
                              "steps": step,
                              "success": False}
        return 'normal', agent_policy

    def _social_tool_call(self, policy: List[ActionModel], step: int):
        observation = None
        # group action by tool name
        tool_mapping = dict()
        # Directly use or use tools after creation.
        for act in policy:
            if not self.tools or (self.tools and act.tool_name not in self.tools):
                # dynamic only use default config in module.
                conf = self.tools_conf.get(act.tool_name)
                tool = ToolFactory(act.tool_name, conf=conf)
                tool.reset()
                tool_mapping[act.tool_name] = []
                self.tools[act.tool_name] = tool
            if act.tool_name not in tool_mapping:
                tool_mapping[act.tool_name] = []
            tool_mapping[act.tool_name].append(act)

        for tool_name, action in tool_mapping.items():
            # Execute action using browser tool and unpack all return values
            observation, reward, terminated, _, info = self.tools[tool_name].step(action)

            logger.info(f'{action} state: {observation}; reward: {reward}')
            # Check if there's an exception in info
            if info.get("exception"):
                color_log(f"Step {step} failed with exception: {info['exception']}")
            logger.info(f"step: {step} finished by tool action.")

        # The tool results give itself, exit; give to other agents, continue
        tmp_name = policy[0].agent_name
        if self.swarm.cur_agent.name() == self.swarm.communicate_agent.name() and (
                len(self.swarm.agents) == 1 or tmp_name is None or self.swarm.cur_agent.name() == tmp_name):
            return "break", True
        elif policy[0].agent_name:
            policy_for_agent = policy[0]
            cur_agent: Agent = self.swarm.agents.get(policy_for_agent.agent_name)
            if not cur_agent:
                raise RuntimeError(f"Can not find {policy_for_agent.agent_name} agent in swarm.")
            if self.swarm.cur_agent.handoffs and policy_for_agent.agent_name not in self.swarm.cur_agent.handoffs:
                # Unable to hand off, exit to the outer loop
                return "return", {"msg": f"Can not handoffs {policy_for_agent.agent_name} agent "
                                         f"by {cur_agent.name()} agent.",
                                  "response": policy[0].policy_info if policy else "",
                                  "steps": step,
                                  "success": False}
            # Check if current agent done
            if cur_agent.finished:
                cur_agent._finished = False
                logger.info(f"{cur_agent.name()} agent be be handed off, so finished state reset to False.")
        return "normal", observation
