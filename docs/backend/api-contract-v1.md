# Agent Studio API Contract v1

## 1. 目标

这份文档定义 Agent Studio 第一版的后端 API 协议。

目标不是一次性覆盖所有未来能力，而是先稳定以下闭环：

- Flow 配置
- Agent 配置
- Resource 绑定
- Flow 运行
- Run 结果查询

## 2. 统一约定

### 2.1 Base Path

```txt
/api/v1
```

### 2.2 响应包裹格式

所有成功响应统一返回：

```json
{
  "success": true,
  "data": {},
  "meta": {}
}
```

所有失败响应统一返回：

```json
{
  "success": false,
  "error": {
    "code": "FLOW_NOT_FOUND",
    "message": "Flow not found",
    "details": {}
  }
}
```

### 2.3 通用字段

所有主资源建议统一包含：

```json
{
  "id": "flow_01",
  "created_at": "2026-04-16T10:00:00Z",
  "updated_at": "2026-04-16T10:00:00Z"
}
```

### 2.4 枚举值原则

枚举值统一使用稳定的小写下划线风格。

例如：

- `draft`
- `published`
- `agent`
- `condition`
- `knowledge_base`

## 3. Flow API

## 3.1 创建 Flow

`POST /api/v1/flows`

请求：

```json
{
  "name": "Customer Support Flow",
  "description": "Basic support triage flow"
}
```

响应：

```json
{
  "success": true,
  "data": {
    "id": "flow_01",
    "name": "Customer Support Flow",
    "description": "Basic support triage flow",
    "status": "draft",
    "latest_version": 1,
    "created_at": "2026-04-16T10:00:00Z",
    "updated_at": "2026-04-16T10:00:00Z"
  }
}
```

## 3.2 查询 Flow 列表

`GET /api/v1/flows`

响应：

```json
{
  "success": true,
  "data": [
    {
      "id": "flow_01",
      "name": "Customer Support Flow",
      "status": "draft",
      "latest_version": 2,
      "updated_at": "2026-04-16T10:00:00Z"
    }
  ],
  "meta": {
    "total": 1
  }
}
```

## 3.3 查询 Flow 详情

`GET /api/v1/flows/{flow_id}`

## 3.4 创建 FlowVersion

`POST /api/v1/flows/{flow_id}/versions`

请求：

```json
{
  "version_note": "initial version",
  "definition": {
    "nodes": [
      {
        "id": "node_start",
        "type": "start",
        "position": {
          "x": 120,
          "y": 180
        },
        "data": {}
      },
      {
        "id": "node_agent_1",
        "type": "agent",
        "position": {
          "x": 360,
          "y": 180
        },
        "data": {
          "label": "Triage Agent",
          "agent_binding": {
            "agent_id": "agent_01"
          }
        }
      },
      {
        "id": "node_end",
        "type": "end",
        "position": {
          "x": 620,
          "y": 180
        },
        "data": {}
      }
    ],
    "edges": [
      {
        "id": "edge_01",
        "source": "node_start",
        "target": "node_agent_1"
      },
      {
        "id": "edge_02",
        "source": "node_agent_1",
        "target": "node_end"
      }
    ]
  }
}
```

响应：

```json
{
  "success": true,
  "data": {
    "id": "flow_version_02",
    "flow_id": "flow_01",
    "version": 2,
    "status": "draft",
    "version_note": "initial version",
    "definition": {
      "nodes": [],
      "edges": []
    },
    "created_at": "2026-04-16T10:00:00Z"
  }
}
```

## 3.5 查询最新 FlowVersion

`GET /api/v1/flows/{flow_id}/versions/latest`

## 4. Agent API

## 4.1 创建 Agent

`POST /api/v1/agents`

请求：

```json
{
  "name": "Triage Agent",
  "description": "Classify incoming user messages",
  "system_prompt": "You are a support triage agent.",
  "model_config": {
    "provider": "openai",
    "model": "gpt-4.1",
    "temperature": 0.2
  }
}
```

## 4.2 查询 Agent 列表

`GET /api/v1/agents`

## 4.3 查询 Agent 详情

`GET /api/v1/agents/{agent_id}`

响应应包含：

- Agent 基础信息
- 模型配置
- 绑定的 skills
- 绑定的 resources

## 4.4 更新 Agent

`PATCH /api/v1/agents/{agent_id}`

请求支持局部更新。

## 4.5 绑定 Skill

`POST /api/v1/agents/{agent_id}/skills`

请求：

```json
{
  "skill_id": "skill_01"
}
```

## 4.6 绑定 Resource

`POST /api/v1/agents/{agent_id}/resources`

请求：

```json
{
  "resource_id": "resource_01"
}
```

## 5. Skill API

第一版 Skill 以配置和绑定为主。

## 5.1 创建 Skill

`POST /api/v1/skills`

请求：

```json
{
  "name": "Search Docs",
  "description": "Search internal docs",
  "kind": "toolset",
  "config": {
    "entrypoint": "search_docs"
  }
}
```

## 5.2 查询 Skill 列表

`GET /api/v1/skills`

## 6. Resource API

第一版 Resource 统一承载：

- `mcp_server`
- `knowledge_base`
- `external_tool`

## 6.1 创建 Resource

`POST /api/v1/resources`

请求：

```json
{
  "name": "Default KB",
  "type": "knowledge_base",
  "description": "Primary product documentation",
  "config": {
    "embedding_provider": "openai",
    "index_name": "default_kb"
  }
}
```

## 6.2 查询 Resource 列表

`GET /api/v1/resources`

支持按 `type` 过滤。

## 6.3 查询 Resource 详情

`GET /api/v1/resources/{resource_id}`

## 7. Run API

## 7.1 创建 Run

`POST /api/v1/runs`

请求：

```json
{
  "flow_id": "flow_01",
  "flow_version": 2,
  "input": {
    "user_message": "I want a refund"
  }
}
```

响应：

```json
{
  "success": true,
  "data": {
    "id": "run_01",
    "flow_id": "flow_01",
    "flow_version": 2,
    "status": "queued",
    "input": {
      "user_message": "I want a refund"
    },
    "created_at": "2026-04-16T10:00:00Z"
  }
}
```

## 7.2 查询 Run 列表

`GET /api/v1/runs`

支持按以下字段过滤：

- `flow_id`
- `status`

## 7.3 查询 Run 详情

`GET /api/v1/runs/{run_id}`

响应示例：

```json
{
  "success": true,
  "data": {
    "id": "run_01",
    "flow_id": "flow_01",
    "flow_version": 2,
    "status": "completed",
    "input": {
      "user_message": "I want a refund"
    },
    "output": {
      "final_text": "Refund request routed to billing"
    },
    "started_at": "2026-04-16T10:00:03Z",
    "finished_at": "2026-04-16T10:00:08Z",
    "steps": [
      {
        "id": "step_01",
        "node_id": "node_agent_1",
        "node_type": "agent",
        "status": "completed",
        "started_at": "2026-04-16T10:00:03Z",
        "finished_at": "2026-04-16T10:00:05Z",
        "input": {
          "user_message": "I want a refund"
        },
        "output": {
          "label": "billing_refund"
        },
        "error": null
      }
    ]
  }
}
```

## 8. 节点定义协议

FlowVersion 的 `definition.nodes` 中，节点协议建议最小统一为：

```json
{
  "id": "node_agent_1",
  "type": "agent",
  "position": {
    "x": 360,
    "y": 180
  },
  "data": {}
}
```

### 8.1 start 节点

```json
{
  "id": "node_start",
  "type": "start",
  "data": {}
}
```

### 8.2 agent 节点

```json
{
  "id": "node_agent_1",
  "type": "agent",
  "data": {
    "label": "Triage Agent",
    "agent_binding": {
      "agent_id": "agent_01"
    },
    "input_mapping": {},
    "output_mapping": {}
  }
}
```

### 8.3 condition 节点

```json
{
  "id": "node_condition_1",
  "type": "condition",
  "data": {
    "label": "Check category",
    "condition": {
      "field": "category",
      "operator": "equals",
      "value": "refund"
    }
  }
}
```

### 8.4 end 节点

```json
{
  "id": "node_end",
  "type": "end",
  "data": {}
}
```

## 9. 状态枚举建议

### 9.1 Flow 状态

- `draft`
- `published`
- `archived`

### 9.2 Run 状态

- `queued`
- `running`
- `completed`
- `failed`
- `cancelled`

### 9.3 Step 状态

- `pending`
- `running`
- `completed`
- `failed`
- `skipped`

## 10. 错误码建议

第一版先统一以下错误码：

- `FLOW_NOT_FOUND`
- `FLOW_VERSION_NOT_FOUND`
- `AGENT_NOT_FOUND`
- `RESOURCE_NOT_FOUND`
- `SKILL_NOT_FOUND`
- `RUN_NOT_FOUND`
- `INVALID_FLOW_DEFINITION`
- `INVALID_NODE_CONFIG`
- `RUN_EXECUTION_FAILED`

## 11. 第一版协议边界

为了保证实现速度，第一版协议刻意不做：

- websocket 实时事件协议
- 流式 token 输出协议
- 批量操作协议
- 复杂分页排序规范

先把最小 CRUD + Run 闭环做好，后续再加增强协议。
