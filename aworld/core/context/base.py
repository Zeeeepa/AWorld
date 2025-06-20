# coding: utf-8
# Copyright (c) 2025 inclusionAI.
from collections import Counter, OrderedDict
from typing import Dict, List, Any, Optional, Callable, TypedDict
from threading import local
from dataclasses import dataclass

from aworld.config import ConfigDict
from aworld.config.conf import ContextRuleConfig, ModelConfig
from aworld.core.context.session import Session
from aworld.core.singleton import InheritanceSingleton
from aworld.utils.common import nest_dict_counter

@dataclass
class ContextUsage:
    total_context_length: int = 128000
    used_context_length: int = 0
    def __init__(self, total_context_length: int = 128000, used_context_length: int = 0):
        self.total_context_length = total_context_length
        self.used_context_length = used_context_length

@dataclass
class AgentContext(dict):
    """Agent context containing both configuration and runtime state.
    
    AgentContext is the core context management class in the AWorld architecture, used to store and manage
    the complete state information of an Agent, including configuration data and runtime state. Its main functions are:
    
    1. **State Restoration**: Save all state information during Agent execution, supporting Agent state restoration and recovery
    2. **Configuration Management**: Store Agent's immutable configuration information (such as agent_id, system_prompt, etc.)
    3. **Runtime State Tracking**: Manage Agent's mutable state during execution (such as messages, step, tools, etc.)
    4. **LLM Prompt Management**: Manage and maintain the complete prompt context required for LLM calls, including system prompts, historical messages, etc.
    5. **LLM Call Intervention**: Provide complete control over the LLM call process through Hook and ContextProcessor
    
    ## Lifecycle
    The lifecycle of AgentContext is completely consistent with the Agent instance:
    - **Creation**: Created during Agent initialization, containing initial configuration
    - **Runtime**: Continuously update runtime state during Agent execution
    - **Destruction**: Destroyed along with Agent instance destruction
    ```
    ┌─────────────────────── AWorld Runner ─────────────────────────┐
    |  ┌──────────────────── Agent Execution ────────────────────┐  │
    │  │  ┌────────────── Step 1 ─────────────┐ ┌── Step 2 ──┐   │  │
    │  │  │  [LLM Call]     [Tool Call(s)]    │
    │  │  │  [       Context Update      ]    │
    ```
    
    ## Field Classification
    - **Immutable Configuration Fields**: agent_id, agent_name, agent_desc, system_prompt, 
      agent_prompt, tool_names, context_rule
    - **Mutable Runtime Fields**: tools, step, messages, context_usage
    
    ## LLM Call Intervention Mechanism
    AgentContext implements complete control over LLM calls through the following mechanisms:
    
    1. **Hook System**:
       - pre_llm_call_hook: Context preprocessing before LLM call
       - post_llm_call_hook: Result post-processing after LLM call
       - pre_tool_call_hook: Context adjustment before tool call
       - post_tool_call_hook: State update after tool call
    
    2. **PromptProcessor**:
       - Prompt Optimization: Optimize prompt content based on context length limitations
       - Message Compression: Intelligently compress historical messages to fit model context window
       - Context Rules: Apply context_rule for customized context processing
    
    ## Usage Scenarios
    1. **Agent Initialization**: Create AgentContext containing configuration information
    2. **LLM Call Control**: Pass as info parameter in policy(), async_policy() methods to control LLM behavior
    3. **Hook Callbacks**: Access and modify LLM call context in various Hooks, use PromptProcessor for prompt optimization and context processing
    4. **State Recovery**: Recover Agent's complete state from persistent storage
    """
    
    # ===== Immutable Configuration Fields =====
    agent_id: str = None
    agent_name: str = None
    agent_desc: str = None
    system_prompt: str = None
    agent_prompt: str = None
    tool_names: List[str] = None
    model_config: ModelConfig = None
    context_rule: ContextRuleConfig = None

    # ===== Mutable Configuration Fields =====
    tools: List[str] = None
    step: int = 0
    messages: List[Dict[str, Any]] = None
    context_usage: ContextUsage = None

    def __init__(self, 
                 agent_id: str = None,
                 agent_name: str = None,
                 agent_desc: str = None,
                 system_prompt: str = None,
                 agent_prompt: str = None,
                 tool_names: List[str] = None,
                 model_config: ModelConfig = None,
                 context_rule: ContextRuleConfig = None,
                 tools: List[str] = None,
                 step: int = 0,
                 messages: List[Dict[str, Any]] = None,
                 context_usage: ContextUsage = None,
                 **kwargs):
        # Configuration fields
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.agent_desc = agent_desc
        self.system_prompt = system_prompt
        self.agent_prompt = agent_prompt
        self.tool_names = tool_names if tool_names is not None else []
        self.model_config = model_config
        self.context_rule = context_rule
        
        # Runtime state fields
        self.tools = tools if tools is not None else []
        self.step = step
        self.messages = messages if messages is not None else []
        self.context_usage = context_usage if context_usage is not None else ContextUsage()
        
        # Additional fields for backward compatibility
        self._init(**kwargs)

    def _init(self, **kwargs):
        self._task_id = kwargs.get('task_id')
    
    def set_model_config(self, model_config: ModelConfig):
        self.model_config = model_config

    def set_messages(self, messages: List[Dict[str, Any]]):
        self.messages = messages

    def set_tools(self, tools: List[str]):
        self.tools = tools
    
    def increment_step(self) -> int:
        self.step += 1
        return self.step
    
    def set_step(self, step: int):
        self.step = step
    
    def update_context_usage(self, used_context_length: int = None, total_context_length: int = None):
        if used_context_length is not None:
            self.context_usage.used_context_length = used_context_length
        if total_context_length is not None:
            self.context_usage.total_context_length = total_context_length

    def get_context_usage_ratio(self) -> float:
        """Get context usage ratio"""
        if self.context_usage.total_context_length <= 0:
            return 0.0
        return self.context_usage.used_context_length / self.context_usage.total_context_length

class Context(InheritanceSingleton):
    """Single instance, can use construction or `instance` static method to create or get `Context` instance.

    Examples:
        >>> context = Context()
    or
        >>> context = Context.instance()
    """

    def __init__(self,
                 user: str = None,
                 *,
                 task_id: str = None,
                 trace_id: str = None,
                 session: Session = None,
                 engine: str = None):
        self._user = user
        self._init(task_id=task_id, trace_id=trace_id, session=session, engine=engine)

    def _init(self, *, task_id: str = None, trace_id: str = None, session: Session = None, engine: str = None):
        self._task_id = task_id
        self._engine = engine
        self._trace_id = trace_id
        self._session: Session = session
        self.context_info = ConfigDict()
        self.agent_info = ConfigDict()
        self.trajectories = OrderedDict()
        self._token_usage = {
            "completion_tokens": 0,
            "prompt_tokens": 0,
            "total_tokens": 0,
        }
        self._agent_context_map = {}
        # TODO swarm topology
        # TODO EventManager
        # TODO workspace

        self._event_manager = None

    def add_token(self, usage: Dict[str, int]):
        self._token_usage = nest_dict_counter(self._token_usage, usage)

    def reset(self, **kwargs):
        self._init(**kwargs)
        self._agent_context_map = {}

    def check_agent_id(self, agent_id: str):
        if agent_id is None:
            raise ValueError("agent_id is required")

    def set_agent_context(self, agent_id: str, agent_context: AgentContext):
        self.check_agent_id(agent_id)
        self._agent_context_map[agent_id] = agent_context

    def get_agent_context(self, agent_id: str) -> Optional[AgentContext]:
        self.check_agent_id(agent_id)
        return self._agent_context_map.get(agent_id, None)

    def clear_agent_context(self, agent_id: str):
        self.check_agent_id(agent_id)
        self._agent_context_map[agent_id] = None

    @property
    def trace_id(self):
        return self._trace_id

    @trace_id.setter
    def trace_id(self, trace_id):
        self._trace_id = trace_id

    @property
    def token_usage(self):
        return self._token_usage

    @property
    def engine(self):
        return self._engine

    @engine.setter
    def engine(self, engine: str):
        self._engine = engine

    @property
    def user(self):
        return self._user

    @user.setter
    def user(self, user):
        if user is not None:
            self._user = user

    @property
    def task_id(self):
        return self._task_id

    @task_id.setter
    def task_id(self, task_id):
        if task_id is not None:
            self._task_id = task_id

    @property
    def session_id(self):
        if self.session:
            return self.session.session_id
        else:
            return None

    @property
    def session(self):
        return self._session

    @session.setter
    def session(self, session: Session):
        self._session = session

    @property
    def event_manager(self):
        return self._event_manager

    @event_manager.setter
    def event_manager(self, event_manager: 'EventManager'):
        self._event_manager = event_manager

    @property
    def record_path(self):
        return "."

    @property
    def is_task(self):
        return True

    @property
    def enable_visible(self):
        return False

    @property
    def enable_failover(self):
        return False

    @property
    def enable_cluster(self):
        return False
