# coding: utf-8
# Copyright (c) 2025 inclusionAI.

from typing import Dict, Any, List

from aworld.core.agent.agent_desc import agent_handoffs_desc
from aworld.core.agent.base import Agent, BaseAgent
from aworld.core.common import ActionModel, Observation
from aworld.logs.util import logger


class Swarm(object):
    """Simple implementation of interactive collaboration between multi-agent and supported env tools."""

    def __init__(self, *args, root_agent: BaseAgent = None, **kwargs):
        self.communicate_agent = root_agent
        if root_agent not in args:
            self._topology = [root_agent] + list(args)
        else:
            self._topology = args
        self._ext_params = kwargs
        self.initialized = False

    def _init(self, **kwargs):
        # prebuild
        valid_agent_pair = []
        for pair in self._topology:
            if isinstance(pair, (list, tuple)):
                if len(pair) != 2:
                    logger.warning(f"{pair} is not a pair value, ignore it.")
                    continue
                else:
                    if not isinstance(pair[0], BaseAgent) or not isinstance(pair[1], BaseAgent):
                        logger.warning(f"agent in {pair} is not a base agent instance, ignore it.")
                        continue
                    valid_agent_pair.append(pair)
            else:
                if not isinstance(pair, BaseAgent):
                    logger.warning(f"agent {pair} is not a base agent instance, ignore it.")
                    continue
                # only one agent, build itself pair
                valid_agent_pair.append((pair, pair))

        if not valid_agent_pair:
            logger.warning("no valid agent pair to build graph.")
            return

        # Agent that communicate with the outside world, the default is the first if the root agent is None.
        if self.communicate_agent is None:
            self.communicate_agent: Agent = valid_agent_pair[0][0]
        # agents in swarm.
        self.agents: Dict[str, BaseAgent] = {}

        # agent handoffs build.
        for pair in valid_agent_pair:
            if pair[0] not in self.agents:
                self.agents[pair[0].name()] = pair[0]
                pair[0].tool_names.extend(self.tools)
            if pair[1] not in self.agents:
                self.agents[pair[1].name()] = pair[1]
                pair[1].tool_names.extend(self.tools)

            pair[0].handoffs.append(pair[1].name())

    def reset(self, tools: List[str] = []):
        """Resets the initial internal state, and init supported tools in agent in swarm.

        Args:
            tools: Tool names that all agents in the swarm can use.
        """
        # can use the tools in the agents in the swarm as a global
        self.tools = tools

        self._init()
        if not self.agents:
            logger.warning("No valid agent in swarm.")
            return

        self.cur_agent = self.communicate_agent
        self.initialized = True

    def _check(self):
        if not self.initialized:
            self.reset()

    def handoffs_desc(self, agent_name: str = None, use_all: bool = False):
        """Get agent description by name for handoffs.

        Args:
            agent_name: Agent unique name.
        Returns:
            Description of agent dict.
        """
        self._check()
        agent: BaseAgent = self.agents.get(agent_name, None)
        return agent_handoffs_desc(agent, use_all)

    def action_to_observation(self, policy: List[ActionModel], observation: List[Observation], strategy: str = None):
        """Based on the strategy, transform the agent's policy into an observation, the case of the agent as a tool.

        Args:
            policy: Agent policy based some messages.
            observation: History of the current observable state in the environment.
            strategy: Transform strategy, default is None. enum?
        """
        self._check()

        if not policy:
            logger.warning("no agent policy, will return origin observation.")
            # get the latest one
            if not observation:
                raise RuntimeError("no observation and policy to transform in swarm, please check your params.")
            return observation[-1]

        if not strategy:
            # default use the first policy
            policy_info = policy[0].policy_info

            if not observation:
                res = Observation(content=policy_info)
            else:
                res = observation[-1]
                res.content = policy_info
            return res
        else:
            logger.warning(f"{strategy} not supported now.")

    def supported_tools(self):
        """Tool names that can be used by all agents in Swarm."""
        self._check()
        return self.tools

    @property
    def finished(self) -> bool:
        """Need all agents in a finished state."""
        self._check()
        return all([agent.finished for _, agent in self.agents.items()])
