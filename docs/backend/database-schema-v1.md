# Agent Studio Database Schema v1

## 1. 目标

这份文档定义 Agent Studio 第一版数据库表设计草案。

数据库选型为 PostgreSQL。

设计原则：

- 先满足 v1 闭环
- 兼顾后续扩展
- 能查用户创建的 Agent
- 能查 Flow 快照
- 能查运行轨迹
- 不把所有结构塞进一个大 JSON

## 2. 命名约定

本项目产品层使用 `Flow` 命名，后端语义上等同于 `Workflow`。
数据库继续使用 `flows / flow_versions`，避免和当前代码骨架冲突。

## 3. 表清单

第一版建议最少包含以下 11 张表：

- `flows`
- `flow_versions`
- `agents`
- `skills`
- `resources`
- `agent_skills`
- `agent_resources`
- `runs`
- `run_steps`
- `run_events`
- `knowledge_documents`

## 4. flows

用于存 Flow 主对象。

建议字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | varchar(64) | 主键 |
| name | varchar(255) | Flow 名称 |
| description | text | 描述 |
| owner_user_id | varchar(64) | 创建者 |
| workspace_id | varchar(64) | 工作空间 |
| status | varchar(32) | `draft/published/archived` |
| latest_version | integer | 最新版本号 |
| created_at | timestamptz | 创建时间 |
| updated_at | timestamptz | 更新时间 |

## 5. flow_versions

用于保存 Flow 可执行快照。

建议字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | varchar(64) | 主键 |
| flow_id | varchar(64) | 关联 `flows.id` |
| version | integer | 版本号 |
| status | varchar(32) | `draft/published` |
| version_note | varchar(255) | 版本备注 |
| input_schema_json | jsonb | Flow 输入契约 |
| output_schema_json | jsonb | Flow 输出契约 |
| definition_json | jsonb | 节点和边定义 |
| created_at | timestamptz | 创建时间 |

约束建议：

- `unique(flow_id, version)`

## 6. agents

用于保存用户创建的 Agent 配置。

建议字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | varchar(64) | 主键 |
| name | varchar(255) | Agent 名称 |
| slug | varchar(128) | 唯一标识 |
| description | text | 描述 |
| source_type | varchar(32) | `system_template/user_defined/workspace_shared` |
| owner_user_id | varchar(64) | 创建者 |
| workspace_id | varchar(64) | 工作空间 |
| role | varchar(128) | Agent 角色 |
| system_prompt | text | 系统提示词 |
| instructions | text | 执行说明 |
| model_provider | varchar(64) | 模型提供方 |
| model_name | varchar(128) | 模型名 |
| model_config_json | jsonb | 模型附加配置 |
| input_schema_json | jsonb | 输入契约 |
| output_schema_json | jsonb | 输出契约 |
| tool_ids_json | jsonb | 已绑定工具 IDs |
| knowledge_ids_json | jsonb | 已绑定知识库 IDs |
| timeout_seconds | integer | 超时设置 |
| retry_policy_json | jsonb | 重试策略 |
| version | integer | Agent 版本 |
| status | varchar(32) | `active/inactive` |
| created_at | timestamptz | 创建时间 |
| updated_at | timestamptz | 更新时间 |

这里把常用查询字段拆出来，不把整个 Agent 配置都藏进 JSON。

## 7. skills

用于保存 Skill 定义。

## 8. resources

用于统一承载外部能力资源。

第一版 `type` 建议支持：

- `mcp_server`
- `knowledge_base`
- `external_tool`

## 9. agent_skills / agent_resources

用于保存 Agent 的绑定关系。

## 10. runs

用于保存一次 Flow 执行实例。

建议字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | varchar(64) | 主键 |
| flow_id | varchar(64) | 关联 `flows.id` |
| flow_version_id | varchar(64) | 关联 `flow_versions.id` |
| status | varchar(32) | `queued/running/completed/failed/cancelled` |
| trigger_type | varchar(32) | `manual/api` |
| user_id | varchar(64) | 触发用户 |
| session_id | varchar(64) | 会话 ID |
| input_json | jsonb | 输入 |
| runtime_context_json | jsonb | 运行时上下文 |
| output_json | jsonb | 最终输出 |
| error_message | text | 错误信息 |
| started_at | timestamptz | 开始时间 |
| finished_at | timestamptz | 结束时间 |
| created_at | timestamptz | 创建时间 |
| updated_at | timestamptz | 更新时间 |

## 11. run_steps

用于保存节点级执行记录。

建议字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | varchar(64) | 主键 |
| run_id | varchar(64) | 关联 `runs.id` |
| node_id | varchar(64) | Flow 节点 id |
| node_key | varchar(128) | 节点逻辑 key |
| node_type | varchar(32) | 节点类型 |
| agent_id | varchar(64) | 当前执行的 Agent |
| step_index | integer | 执行顺序 |
| attempt | integer | 第几次执行 |
| status | varchar(32) | `pending/running/completed/failed/skipped` |
| input_json | jsonb | 节点输入 |
| output_json | jsonb | 节点输出 |
| resolved_config_json | jsonb | 实际解析后的执行配置 |
| error_message | text | 错误信息 |
| usage_json | jsonb | token 和调用统计 |
| started_at | timestamptz | 开始时间 |
| finished_at | timestamptz | 结束时间 |
| created_at | timestamptz | 创建时间 |
| updated_at | timestamptz | 更新时间 |

## 12. run_events

用于保存流式事件和调试事件。

建议字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | bigserial | 主键 |
| run_id | varchar(64) | 关联 `runs.id` |
| run_step_id | varchar(64) | 可选关联步骤 |
| event_type | varchar(64) | 事件类型 |
| event_payload | jsonb | 事件负载 |
| created_at | timestamptz | 创建时间 |

## 13. knowledge_documents

用于记录知识库中的源文档。

第一版可以先不拆 chunk 表和 embedding 表，但要给后续预留扩展空间。

## 14. 关系图

```txt
flows 1---n flow_versions
flows 1---n runs
flow_versions 1---n runs
agents n---n skills
agents n---n resources
runs 1---n run_steps
runs 1---n run_events
resources 1---n knowledge_documents
```

## 15. 落地建议

优先顺序：

1. 先建 `agents / flows / flow_versions / runs / run_steps`
2. 再建 `run_events`
3. 最后补 `skills / resources / knowledge_documents`

这样可以最快跑通“用户创建 Agent -> 用户编排 Flow -> 触发 Run -> 记录步骤”的闭环。
