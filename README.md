# Agent-Studio

Agent Studio 后端仓库。

这个仓库承载 Agent Studio 的编排内核，目标是支持：

- Flow 工作流定义与版本管理
- Agent 配置与能力绑定
- MCP / Skill / 知识库资源接入
- Flow 运行与 Run 轨迹记录

第一版不是做成完整平台，而是先把“配置、执行、观测”三件事打通。

## 当前定位

这个后端项目主要负责：

- 保存 Flow、FlowVersion、Agent、Resource、Run
- 根据 FlowVersion 执行节点
- 记录每个节点的输入、输出、状态和错误
- 给前端提供稳定 API

当前第一版执行模型先收敛到：

- Start
- Agent
- Condition
- End

## 技术栈

- Python
- FastAPI
- PostgreSQL
- Agno

## 开发约定

后端默认在项目内虚拟环境执行。

- 虚拟环境目录：`.venv/`
- Python 版本：`>=3.11`
- 不直接使用系统 Python 跑项目命令

## 初始化

```bash
cd /Users/wtf/Desktop/agent-studio/Agent-Studio
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
cp .env.example .env
```

## 模型配置

Agent 只保存：

- `provider`
- `model`
- 推理参数，例如 `temperature`

以下敏感或系统级配置不落 Agent 表：

- `base_url`
- `api_key`

当前支持的环境变量如下：

```bash
DEFAULT_LLM_PROVIDER=openai-compatible
LLM_TIMEOUT_SECONDS=120

OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=
OPENAI_DEFAULT_MODEL=gpt-4.1-mini

OPENAI_COMPATIBLE_BASE_URL=https://kspmas.ksyun.com/v1
OPENAI_COMPATIBLE_API_KEY=
OPENAI_COMPATIBLE_DEFAULT_MODEL=deepseek-v3.1-ksyun
```

## 本地运行

```bash
cd /Users/wtf/Desktop/agent-studio/Agent-Studio
source .venv/bin/activate
uvicorn app.main:app --reload
```

如果后面需要按可编辑模式安装，也可以使用：

```bash
pip install -e .
```

## 当前结构

```txt
Agent-Studio/
  app/
    main.py
    schemas/
      contracts.py
  db/
    schema.sql
  docs/
    backend/
  requirements.txt
  .env.example
```

## 当前已有内容

- `app/main.py`
  FastAPI 入口和 API 路由注册

- `app/runners/flow_runner.py`
  最小编排执行器，支持 Start/Agent/Condition/End

- `app/runners/agent_runner.py`
  Agent 节点执行器，已接入 OpenAI-compatible LLM 调用

- `app/schemas/contracts.py`
  Flow、Agent、Run 等协议模型

- `db/schema.sql`
  第一版数据库表结构草案

- `docs/backend/backend-implementation.md`
  后端分层、执行模型和开发顺序

- `docs/backend/api-contract-v1.md`
  第一版 API 协议

- `docs/backend/database-schema-v1.md`
  第一版 PostgreSQL 表设计

## 文档

- `docs/backend/backend-implementation.md`
- `docs/backend/api-contract-v1.md`
- `docs/backend/database-schema-v1.md`
