from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class FlowStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ResourceType(StrEnum):
    MCP_SERVER = "mcp_server"
    KNOWLEDGE_BASE = "knowledge_base"
    EXTERNAL_TOOL = "external_tool"


class AgentSourceType(StrEnum):
    SYSTEM_TEMPLATE = "system_template"
    USER_DEFINED = "user_defined"
    WORKSPACE_SHARED = "workspace_shared"


class Position(BaseModel):
    x: float
    y: float


class AgentBinding(BaseModel):
    agent_id: str
    agent_version: int | None = None


class ConditionRule(BaseModel):
    field: str
    operator: str
    value: Any


class ConditionBranch(BaseModel):
    """条件分支定义"""
    id: str
    label: str
    condition_value: str | None = None
    target_node_id: str | None = None


class LLMClassifyConfig(BaseModel):
    """LLM分类配置"""
    model: str = "gpt-4.1-mini"
    prompt: str | None = None
    categories: list[str] = Field(default_factory=list)
    output_key: str = "category"


class RegexPattern(BaseModel):
    """正则匹配模式"""
    pattern: str
    branch_id: str


class StartNodeData(BaseModel):
    label: str | None = None


class AgentNodeData(BaseModel):
    label: str
    agent_binding: AgentBinding
    input_mapping: dict[str, Any] = Field(default_factory=dict)
    output_mapping: dict[str, Any] = Field(default_factory=dict)
    max_retry: int = 0
    on_fail: str | None = None


class TeamNodeData(BaseModel):
    label: str
    description: str | None = None
    member_agent_ids: list[str] = Field(default_factory=list)
    strategy: Literal["parallel", "sequential"] = "parallel"
    input_mapping: dict[str, Any] = Field(default_factory=dict)
    output_mapping: dict[str, Any] = Field(default_factory=dict)
    max_retry: int = 0
    on_fail: str | None = None


class ConditionNodeData(BaseModel):
    label: str
    condition_type: Literal["expression", "llm_classify", "regex", "json_schema", "simple"] = "simple"
    input_source: str = "{{input.user_message}}"

    # 不同条件类型的配置
    expression: str | None = None
    llm_config: LLMClassifyConfig | None = None
    regex_patterns: list[RegexPattern] = Field(default_factory=list)
    json_schema: dict[str, Any] = Field(default_factory=dict)

    # 分支配置
    branches: list[ConditionBranch] = Field(default_factory=list)
    default_branch_id: str | None = None

    # 兼容旧版本的简单条件
    condition: ConditionRule | None = None


class EndNodeData(BaseModel):
    label: str | None = None


class StartNode(BaseModel):
    id: str
    type: Literal["start"]
    position: Position
    data: StartNodeData = Field(default_factory=StartNodeData)


class AgentNode(BaseModel):
    id: str
    type: Literal["agent"]
    position: Position
    data: AgentNodeData


class TeamNode(BaseModel):
    id: str
    type: Literal["team"]
    position: Position
    data: TeamNodeData


class ConditionNode(BaseModel):
    id: str
    type: Literal["condition"]
    position: Position
    data: ConditionNodeData


class EndNode(BaseModel):
    id: str
    type: Literal["end"]
    position: Position
    data: EndNodeData = Field(default_factory=EndNodeData)


FlowNode = StartNode | AgentNode | TeamNode | ConditionNode | EndNode


class FlowEdge(BaseModel):
    id: str
    source: str
    target: str
    source_handle: str | None = None
    target_handle: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class FlowDefinition(BaseModel):
    nodes: list[FlowNode]
    edges: list[FlowEdge]


class ModelConfig(BaseModel):
    provider: str
    model: str
    temperature: float | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class RetryPolicy(BaseModel):
    max_retries: int = 1
    retry_backoff_seconds: int = 3


class AgentSummary(BaseModel):
    id: str
    name: str
    description: str | None = None
    source_type: AgentSourceType = AgentSourceType.USER_DEFINED
    owner_user_id: str | None = None
    workspace_id: str | None = None
    role: str | None = None
    status: str = "active"
    stream: bool = False
    debug: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AgentDetail(AgentSummary):
    model_config = ConfigDict(populate_by_name=True)

    system_prompt: str | None = None
    instructions: str | None = None
    llm_config: ModelConfig = Field(alias="model_config")
    tool_ids: list[str] = Field(default_factory=list)
    skill_ids: list[str] = Field(default_factory=list)
    knowledge_ids: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = 120
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    version: int = 1


class AgentCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: str | None = None
    role: str | None = None
    system_prompt: str | None = None
    instructions: str | None = None
    source_type: AgentSourceType = AgentSourceType.USER_DEFINED
    owner_user_id: str | None = None
    workspace_id: str | None = None
    llm_config: ModelConfig = Field(alias="model_config")
    tool_ids: list[str] = Field(default_factory=list)
    skill_ids: list[str] = Field(default_factory=list)
    knowledge_ids: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = 120
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    stream: bool = False
    debug: bool = False


class AgentUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    description: str | None = None
    role: str | None = None
    system_prompt: str | None = None
    instructions: str | None = None
    llm_config: ModelConfig | None = Field(default=None, alias="model_config")
    tool_ids: list[str] | None = None
    skill_ids: list[str] | None = None
    knowledge_ids: list[str] | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    timeout_seconds: int | None = None
    retry_policy: RetryPolicy | None = None
    stream: bool | None = None
    debug: bool | None = None
    status: str | None = None


class ResourceSummary(BaseModel):
    id: str
    name: str
    type: ResourceType
    description: str | None = None
    status: str = "active"


class FlowSummary(BaseModel):
    id: str
    name: str
    description: str | None = None
    owner_user_id: str | None = None
    workspace_id: str | None = None
    status: FlowStatus = FlowStatus.DRAFT
    latest_version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FlowCreateRequest(BaseModel):
    name: str
    description: str | None = None
    owner_user_id: str | None = None
    workspace_id: str | None = None
    definition: FlowDefinition


class FlowVersionDetail(FlowSummary):
    definition: FlowDefinition


class RunStepResult(BaseModel):
    id: str
    node_id: str
    node_type: str
    status: StepStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class RunCreateRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    user_id: str | None = None
    session_id: str | None = None
    stream: bool = False


class AgentRunCreateRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    user_id: str | None = None
    session_id: str | None = None
    stream: bool = False


class RunSummary(BaseModel):
    id: str
    flow_id: str
    flow_version: int
    status: RunStatus
    created_at: datetime | None = None


class RunEvent(BaseModel):
    id: str
    run_id: str
    event_type: str
    created_at: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class RunDetail(BaseModel):
    id: str
    flow_id: str
    flow_version: int
    status: RunStatus
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    steps: list[RunStepResult] = Field(default_factory=list)
    events: list[RunEvent] = Field(default_factory=list)


class SuccessResponse(BaseModel, Generic[T]):
    success: Literal[True] = True
    data: T
    meta: dict[str, Any] = Field(default_factory=dict)


class ErrorPayload(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    success: Literal[False] = False
    error: ErrorPayload
