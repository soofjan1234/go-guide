---
title: 通信协议
weight: 80
---

# 通信协议（Communication Protocol）

通信协议（Communication Protocol）是指 Agent 与用户、工具、其他 Agent 或外部系统之间交换信息时遵循的规则和格式。

在简单聊天场景中，通信可以只是自然语言。但在 Agent 系统中，模型经常需要调用工具、接收结构化结果、与多个模块协作，甚至参与多 Agent 任务分工。因此，通信协议决定了信息如何被表达、传递、解析和执行。

## 1. 为什么需要 MCP？（解决什么痛点）

在 MCP 之前，AI 接入生态面临着**典型的“$N \times M$ 碎片化难题”**：

- 如果你有 $N$ 个 AI 客户端（如 Cursor、Claude Desktop、VS Code AI 扩展、自定义 Agent）；
- 同时有 $M$ 个外部工具/数据源（如 Git、Jira、Slack、PostgreSQL）；
- 开发者需要为每一个客户端与工具组合，重复编写 $N \times M$ 次对接逻辑。
    

```
【以前：私有对接，混乱不堪】
Cursor   ----(私有代码)----> GitHub / Postgres
Claude   ----(插件格式)----> GitHub / Postgres
Custom   ----(自定义API)----> GitHub / Postgres

【现在：MCP 统一标准，天然解耦】
Cursor   \                                   / GitHub Server
Claude   ---->  [ MCP 标准协议通信 ]  ---->  - Postgres Server
Custom   /                                   \ Slack Server
```

有了 MCP 之后：

1. 工具提供商（如 Postgres 或 GitHub）只需要编写**一次** MCP Server。
2. 任何支持 MCP 协议的 AI 客户端，都可以**直接插入使用**这个 Server，无需二次改造。
    

## 2. MCP 的核心架构（Client - Host - Server）

MCP 的架构灵感深度借鉴了编程语言界极其成功的 **LSP（Language Server Protocol，语言服务协议）**。

其体系由三个核心角色构成：

1. **MCP Host（宿主环境）：** 发起连接的 AI 应用程序（例如 Cursor 编辑器、Claude Desktop 客户端或你的自定义 Agent 框架）。
    
2. **MCP Client（协议客户端）：** 运行在 Host 内部，与 MCP Server 建立 1:1 稳定连接的通信代理。
    
3. **MCP Server（协议服务端）：** 一个独立的轻量级进程（或服务），专门用来**暴露特定的数据资源、工具能力或 Prompt 模板**。
    

### 底层通信机制

- **协议标准：** 基于 **JSON-RPC 2.0** 消息格式。
- **传输层（Transport）：**
    
    - **stdio（标准输入输出）：** 用于本地进程间通信（例如 Claude Desktop 直接拉起一个本地运行的 Python/Node.js MCP 脚本）。
    - **SSE（Server-Sent Events）：** 用于跨网络/远程 HTTP 通信，支持异步推送。
        

## 3. MCP 暴露给 AI 的三大核心能力

一个 MCP Server 可以向 AI 模型提供以下三种能力：

### ① Resources（资源 - Read Only）

类似 HTTP 的 `GET` 请求。向模型提供**只读的上下文数据**（如文件内容、数据库 Schema、API 接口文档、日志流等）。

- _例子：_ `file:///path/to/project/main.go` 或 `postgres://database/schema`
    

### ② Tools（工具 - Executable）

类似于 LLM 的 **Function Calling（函数调用）**。允许模型触发执行某些业务动作，并返回执行结果。

- _例子：_ 执行 `git_commit`、发起 `send_slack_message`、运行 `execute_sql_query`。
    

### ③ Prompts（预设提示词/模板）

允许 MCP Server 暴露一些精心调优过的**交互模板**，帮助用户快速触发特定复杂任务。

- _例子：_ 一个 Code Review 服务可以提供名为 `analyze-security-vulnerabilities` 的 Prompt 模板。
