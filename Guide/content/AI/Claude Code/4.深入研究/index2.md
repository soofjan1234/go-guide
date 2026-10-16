---
title: MCP 与 LSP 集成
weight: 220
---

Claude Code 的工具系统不必只依赖内置的 Read、Edit 和 Bash。**MCP 负责把外部能力接入 Agent，LSP 则帮助 Agent 更准确地理解代码符号与引用关系。** 二者用途不同，但都能提升 Agent 获取信息和完成任务的能力。

# MCP：把外部工具接入 Agent

假设用户要求：“查看项目的 GitHub Issue，并根据描述修复代码。”如果没有对应工具，模型只能依赖用户粘贴 Issue 内容；接入 MCP Server 后，Agent 可以通过服务器暴露的工具读取 Issue。

```text
用户请求
   ↓
Claude Code / Harness
   ↓ 发现可用工具、构造调用
MCP Client
   ↓ 协议通信
MCP Server（例如 GitHub 集成）
   ↓
外部服务
   ↓
工具结果返回 Agent Loop
```

MCP（Model Context Protocol）定义的是客户端与外部能力提供者之间的交互协议。外部服务器可以提供工具等能力，但 **MCP 不等于自动授权，也不等于让模型直接访问所有外部数据**。真正可用的能力还受连接配置、服务端权限和 Harness 策略约束。

# LSP：为什么代码导航不只靠 Grep

假设 Go 项目里有多个同名的 `GetUser` 函数。Grep 可以找出文本匹配，但它本身不知道某个调用对应哪个函数定义。

LSP（Language Server Protocol）提供更接近代码语义的操作，例如：

- 跳转到定义（Definition）
- 查找引用（References）
- 查看符号信息（Symbols）
- 获取诊断信息（Diagnostics）

例如：

```go
user, err := repo.GetUser(ctx, id)
```

如果语言服务器正确理解项目，Agent 就可以定位这里的 `GetUser` 对应的具体实现，而不必仅靠字符串搜索推断。

# MCP 和 LSP 不要混为一谈

| | MCP | LSP |
| --- | --- | --- |
| 主要目标 | 连接外部工具、资源和服务 | 提供编程语言语义能力 |
| 典型对象 | GitHub、数据库、业务服务 | Go、TypeScript 等语言服务器 |
| 典型操作 | 查询 Issue、调用外部 API | 跳转定义、查找引用 |
| 核心价值 | 扩展 Agent 能做什么 | 提高代码理解与导航准确性 |

LSP 可以作为某种工具能力接入 Agent，但它与 MCP 不是同一层协议，也不是必须通过 MCP 才能使用。

# 如何进入 Agent Loop

对模型而言，无论能力来自内置工具、MCP 还是 LSP，最终都需要以 Harness 能够管理的调用入口呈现。模型选择工具并传入参数，执行层完成实际通信，再把结果作为上下文返回模型。

**模型负责判断需要什么信息，协议和工具适配层负责获取信息。** 这也解释了为什么统一 Tool 抽象很重要：底层实现不同，Agent Loop 不需要为每一种外部系统重新设计推理流程。

# 什么时候值得深入

如果只是学习 Claude Code 原理，重点掌握 MCP 的客户端—服务器关系、工具发现与调用，以及 LSP 相比文本搜索的优势即可。具体 SDK、传输方式和语言服务器配置可以等到真正开发集成时再研究。
