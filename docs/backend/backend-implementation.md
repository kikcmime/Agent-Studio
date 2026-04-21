# Agent Studio Backend 实现文档

## 1. 后端目标

后端第一版要提供的不是“大而全 AI 平台”，而是一个足够稳定的编排内核。

核心目标只有 4 个：

- 能让用户创建 Agent
- 能让用户编排 Flow
- 能跑流程
- 能留轨迹

技术栈按当前目标收敛为：

- Python
- FastAPI
- PostgreSQL
- Agno

运行约定补充：

- 后端开发默认在项目内 `.venv` 虚拟环境执行
- 不直接依赖系统 Python 作为项目运行环境
- 所有安装、启动、测试命令默认先激活 `.venv`

## 2. 名词约定

项目内统一采用以下理解：

- `Flow`：前端和项目内的产品命名
- `Workflow`：后端编排语义命名

在 v1 中这两个词语义等价。
代码、接口、数据库先沿用 `flow` 命名，避免和现有前端骨架冲突。

## 3. 后端职责

后端负责：

- Agent / Flow / Resource 的配置管理
- Flow Version 快照管理
- Run 创建与状态推进
- 节点执行编排
- 运行日志、输入输出、错误落库
- 为前端提供稳定 API

后端暂时不负责复杂运营能力，例如组织权限、计费、市场化插件分发。

## 4. 产品方向已经固定

当前项目不是做“系统内置固定 Agent 再让用户挑选”，主路线已经固定为：

- 用户在前端创建 Agent
- Agent 持久化到数据库
- 用户在前端把多个 Agent 编排成 Flow
- Orchestrator 在运行时读取 Flow 和 Agent 定义并执行

所以后端实现必须围绕“用户自定义 Agent”展开，而不是围绕硬编码模板展开。

系统模板可以保留，但只作为“创建时的快捷模板”，不是主数据来源。

## 5. 领域模型

第一版后端领域模型建议固定为以下对象：

- `flows`
- `flow_versions`
- `agents`
- `skills`
- `resources`
- `runs`
- `run_steps`
- `run_events`

其中 `resources` 是统一资源表，用来承载：

- mcp_server
- knowledge_base
- external_tool

## 6. 核心关系

### 6.1 Flow 与 FlowVersion

Flow 是逻辑对象。
FlowVersion 是可执行快照。

第一版即使不做正式发布，也建议保存版本快照，避免画布数据被直接覆盖后无法追查。

### 6.2 Agent 与 Resource

Agent 不直接拥有复杂能力实现，只维护绑定关系：

- 绑定模型配置
- 绑定 Skill
- 绑定 Resource

### 6.3 Run 与 RunStep

一次 Run 需要拆成三层：

- `runs`：整体执行实例
- `run_steps`：节点级执行记录
- `run_events`：流式事件和调试事件

这样前端的时间线、日志页和运行回放才有稳定来源。

## 7. Flow 执行模型

第一版执行模型建议支持：

1. 根据 `flow_version` 读取节点和边
2. 从 Start 节点开始
3. 顺序执行后继节点
4. 遇到 Condition 时根据规则选择下一条边
5. 到 End 节点结束

第一版必须支持：

- 串行
- 简单条件分支
- Agent 节点
- Run 落库

第一版可以先不支持：

- 并行 fan-out
- join 汇聚
- 人工审批节点
- 定时触发器

但表结构和 contracts 要预留扩展空间。

## 8. Agent 执行模型

一个 Agent 节点执行时，后端做以下事情：

1. 读取 Agent 配置
2. 解析 input mapping
3. 组装 prompt 上下文
4. 注入 Skill / MCP / 知识库能力引用
5. 调用 Agno Agent 执行
6. 将输出转成标准节点结果
7. 校验结构化输出
8. 落库到 run_steps

模型配置约定固定为：

- Agent 只保存 `provider`、`model` 和推理参数
- `base_url` 不存在 Agent 表里，统一走后端系统配置
- `api_key` 不存在 Agent 表里，统一走环境变量或后续密钥表

v1 先支持两类 provider：

- `openai`
- `openai-compatible`

对应环境变量建议固定为：

- `OPENAI_BASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_DEFAULT_MODEL`
- `OPENAI_COMPATIBLE_BASE_URL`
- `OPENAI_COMPATIBLE_API_KEY`
- `OPENAI_COMPATIBLE_DEFAULT_MODEL`

这样做的好处是：

- 前端不用处理密钥
- Agent 配置可以安全复用
- 切换模型服务时不需要批量改数据库

关键点不在于把所有能力都做复杂，而在于输出统一：

```py
class NodeExecutionResult:
    status: str
    output_text: str | None
    output_json: dict | None
    usage: dict | None
    error: str | None
```

## 9. v1 API 范围

第一版 API 建议按资源拆分：

- `/api/v1/agents`
- `/api/v1/flows`
- `/api/v1/runs`

必须有的动作：

- 创建 Agent
- 查询 Agent
- 更新 Agent
- 创建 Flow
- 查询 Flow
- 获取最新 FlowVersion
- 运行 Flow
- 查询 Run 详情

## 10. 当前代码实现建议

当前骨架已经存在：

- `app/main.py`
- `app/schemas/contracts.py`
- `db/schema.sql`

建议下一阶段直接按下面的方式展开：

```txt
Agent-Studio/
  app/
    main.py
    api/
      agent_routes.py
      flow_routes.py
      run_routes.py
    services/
      agent_service.py
      flow_service.py
      run_service.py
    repositories/
      agent_repository.py
      flow_repository.py
      run_repository.py
    runners/
      flow_runner.py
      agent_runner.py
    schemas/
      contracts.py
```

## 11. 当前最小代码目标

当前就可以同时写后端代码，优先级如下：

1. 先把 Agent CRUD 接口做真
2. 再把 Flow CRUD 接口做真
3. 再把 Run 触发和 Run 查询打通
4. 最后再把 Agent 执行器接到 Agno

这意味着：

- 现在可以同时写文档和代码
- 不需要等所有方案冻结后再开工
- 先做“可配置 + 可触发 + 可查询”的闭环最重要

## 12. 当前阶段边界

当前阶段先不要做：

- 动态生成永久 Agent
- 递归子 Flow
- 复杂 RBAC
- 并行调度器
- 多模型策略引擎

当前阶段只做：

- 用户创建 Agent
- 用户编排 Flow
- 顺序执行
- 条件分支
- 运行落库

## 13. 本地执行约定

本项目后端命令统一按下面顺序执行：

```bash
cd /Users/wtf/Desktop/agent-studio/Agent-Studio
source .venv/bin/activate
```

常用命令示例：

```bash
pip install -e .
uvicorn app.main:app --reload --port 7000
python -m py_compile app/main.py app/schemas/contracts.py
```

## 14. 第一阶段开发顺序

后端建议按以下顺序推进：

1. 先补 `agents / flows / runs` 三组最小路由
2. 再补 repository 层，先用内存实现，后接 PostgreSQL
3. 然后补 flow runner，把串行执行和 condition 分支跑通
4. 最后再接 Agno、MCP、知识库解析

不要一开始就把大模型、MCP、知识库都接满。
先把“编排骨架”跑通，后面接能力只是填充执行器。
