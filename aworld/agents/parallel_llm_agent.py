# coding: utf-8
# Copyright (c) 2025 inclusionAI.
from typing import List, Dict, Any, Callable

from aworld.agents.llm_agent import Agent
from aworld.config import RunConfig
from aworld.core.common import Observation, ActionModel


class ParallelizableAgent(Agent):
    """Support for parallel agents in the swarm.

    The parameters of the extension function are the agent itself, which can obtain internal information of the agent.
    `aggregate_func` function example:
    >>> def agg(agent: ParallelizableAgent, res: Dict[str, List[ActionModel]]):
    >>>     ...
    """
    agents: List[Agent] = []
    # The function of aggregating the results of the parallel execution of agents.
    aggregate_func: Callable[..., Any] = None

    async def async_policy(self, observation: Observation, info: Dict[str, Any] = {}, **kwargs) -> List[ActionModel]:
        from aworld.core.task import Task
        from aworld.runners.utils import choose_runners, execute_runner

        tasks = []
        for agent in self.agents:
            tasks.append(Task(input=observation, agent=agent))

        runners = await choose_runners(tasks)
        res = await execute_runner(runners, RunConfig())

        if self.aggregate_func:
            return self.aggregate_func(self, res)

        results = []
        for k, v in res.items():
            results.append(ActionModel(agent_name=self.id(), policy_info=v.answer))
        return results

    def finished(self) -> bool:
        return all([agent.finished for agent in self.agents])
