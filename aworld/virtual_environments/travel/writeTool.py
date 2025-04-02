# coding: utf-8
import traceback
from typing import Any, Tuple, List, Dict

from aworld.core.envs.tool_action import WriteAction
from aworld.core.common import ActionModel, Observation, ActionResult, Tools
from aworld.logs.util import logger
from aworld.core.envs.tool import ToolFactory, Tool
from aworld.config.conf import ToolConfig


@ToolFactory.register(name="write_tool", desc="write tool", supported_action=WriteAction)
class WriteTool(Tool[Observation, List[ActionModel]]):
    def __init__(self, conf: ToolConfig, **kwargs) -> None:
        super(WriteTool, self).__init__(conf, **kwargs)

    def name(self):
        return "write_tool"

    def reset(self, *, seed: int | None = None, options: Dict[str, str] | None = None) -> Tuple[
        Observation, dict[str, Any]]:
        # from options obtain user query
        return Observation(content=options.get("query", None) if options else None), {}

    def step(self, action: List[ActionModel], **kwargs) -> Tuple[Observation, float, bool, bool, Dict[str, Any]]:
        reward = 0
        fail_error = ""
        action_result = None

        invalid_acts: List[int] = []
        for i, act in enumerate(action):
            if act.tool_name != "write_tool":
                logger.warning(f"tool {act.tool_name} is not a write tool!")
                invalid_acts.append(i)

        if invalid_acts:
            for i in invalid_acts:
                action[i] = None

        resp = ""
        try:
            action_result, resp = self.action_executor.execute_action(action, **kwargs)
            reward = 1
        except Exception as e:
            fail_error = str(e)

        terminated = kwargs.get("terminated", False)
        if action_result:
            for res in action_result:
                if res.is_done:
                    terminated = res.is_done
                    self._finish = True

        info = {"exception": fail_error}
        if resp:
            resp = json.dumps(resp)
        else:
            resp = action_result[0].content

        action_result = [ActionResult(content=resp, keep=True, is_done=True)]
        observation = Observation(content=resp)
        observation.action_result = action_result
        return (observation,
                reward,
                terminated,
                kwargs.get("truncated", False),
                info)

    def close(self) -> None:
        pass

    def finished(self) -> bool:
        # one time
        return True