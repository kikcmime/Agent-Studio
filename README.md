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
```

## 当前已有内容

- `app/main.py`
  最小 FastAPI 入口和 demo 接口

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

## 第一版要做的东西

这个仓库接下来优先做：

1. `flows / agents / runs` 三组最小 CRUD
2. FlowVersion 的保存与读取
3. 串行 Flow Runner
4. Condition 分支执行
5. Run 和 RunStep 轨迹记录

## 文档

- `docs/backend/backend-implementation.md`
- `docs/backend/api-contract-v1.md`
- `docs/backend/database-schema-v1.md`
