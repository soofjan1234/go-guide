---
title: 架构总览
weight: 10
---

Claude Code 不只是调用大模型 API 的命令行工具，还需要组织模型、工具、上下文和运行状态，持续推进任务。

# 整体架构

| 层次 | 原笔记中的模块 | 主要职责 |
| --- | --- | --- |
| 启动层 | `main.tsx` | 加载配置、认证，确定运行模式并装配能力 |
| 核心引擎 | `QueryEngine.ts` | 管理消息，调用模型，调度工具，推进任务循环 |
| 工具系统 | `Tool.ts`、`tools.ts` | 定义工具协议，汇总、注册和筛选工具 |
| 命令系统 | `commands.ts` | 提供用户显式操作的命令入口 |
| 上下文与状态 | `context.ts`、`AppStateStore.ts` | 准备模型上下文，维护应用运行状态 |
| 扩展能力 | MCP、LSP、Plugins、Skills | 接入外部能力、代码分析和可复用的任务指导 |

# 各模块职责

## main.tsx：启动与能力装配

Claude Code 初始化的是：

- 配置、认证、模型和会话设置。
- Tools 和 Commands。
- MCP、LSP、Plugins 和 Skills。
- 交互式 REPL，或本次运行所需的其他模式。

启动层负责决定本次运行需要哪些能力，并把它们组织起来；具体工具逻辑由对应模块实现。

## QueryEngine：任务执行循环

普通 LLM 调用通常是：

```text
用户提问 → 调用模型 → 返回回答
```

Agent 需要在模型和工具之间循环：

```text
用户提问
   ↓
调用模型
   ↓
模型提出工具调用
   ↓
执行工具并获取结果
   ↓
将结果交回模型
   ↓
根据结果继续执行，直到本轮任务结束
```

例如让 Claude Code“找到 Go 项目里的慢 SQL，并尝试优化”，它可能依次搜索 SQL 代码、读取文件、分析查询、修改代码、运行测试，最后总结结果。

这些动作需要多轮模型调用。QueryEngine 负责持续推进任务，并维护运行状态：

| 状态字段 | 用途 |
| --- | --- |
| `mutableMessages` | 保存会话消息 |
| `abortController` | 控制任务中断 |
| `permissionDenials` | 记录权限拒绝 |
| `readFileState` | 保存文件读取缓存 |
| `totalUsage` | 统计 Token 用量 |

## Tool.ts 与 tools.ts：协议和注册

- **`Tool.ts`**：定义工具应遵循的统一协议。
- **`tools.ts`**：汇总、注册和筛选工具。

BashTool、FileReadTool、FileEditTool 等能力通过统一协议接入：模型提出工具调用，运行时负责执行并返回结果。

## Commands 与 Tools：用户入口和执行能力

| 对比项 | Commands | Tools |
| --- | --- | --- |
| 主要触发方 | 用户 | 模型 |
| 典型例子 | `/help`、`/compact` | Bash、Read、Edit |
| 主要职责 | 用户显式控制 Claude Code | Agent 操作外部环境、执行任务 |

Command 是用户控制程序的入口，Tool 是 Agent 执行任务的能力。某些命令也会进一步触发 Agent 执行，两者可以配合使用。

## Context 与 AppState：模型信息和程序状态

| 模块 | 关注的问题 | 例子 |
| --- | --- | --- |
| `context.ts` | 模型应该知道什么 | Git 状态、`CLAUDE.md` 等上下文 |
| `AppStateStore.ts` | 当前程序处于什么状态 | REPL、任务、通知、MCP 等应用状态 |

例如，Git 工作区有哪些未提交修改，属于提供给模型的上下文；界面有哪些任务和通知，属于应用状态。

# 启动流程

| 阶段 | 主要工作 |
| --- | --- |
| 1. 性能预热 | 提前发起配置读取、系统密钥存储预取等操作 |
| 2. 解析配置和环境 | 解析 CLI 参数、settings、权限策略、运行模式和会话信息 |
| 3. 装配能力 | 准备 Commands、Tools、Context、MCP、LSP、Plugins 和 Skills |
| 4. 进入运行模式 | 启动交互式 REPL、非交互执行，或处理远程、恢复会话等模式 |

## 性能预热：提前发起 I/O

- `profileCheckpoint('main_tsx_entry')`：记录启动性能检查点。
- `startMdmRawRead()`：提前读取 MDM 管理设置。
- `startKeychainPrefetch()`：提前预取系统安全存储中的数据。

性能检查点用于记录耗时，后两个操作用于提前发起读取，减少后续等待。

## 运行模式：交互式与非交互式

交互式启动：

```bash
claude
```

用户可以持续输入问题。

非交互式执行：

```bash
claude -p "解释这个项目的架构"
```

适合脚本或自动化场景。两种模式可以复用底层 Agent 引擎，但交互方式、输出处理和生命周期不同，因此启动层需要先确定本次会话的运行模式。

## REPL 与 QueryEngine 的分工

REPL 是 Read-Eval-Print Loop，即“读取输入 → 执行 → 输出结果 → 继续等待输入”的交互循环。

在 Claude Code 中：

- **REPL** 负责接收用户输入、展示执行结果。
- **QueryEngine** 负责驱动模型与工具执行。

一次 REPL 输入可以触发多轮模型和工具调用。

# 完整运行示例

启动 Claude Code 后，输入“检查当前 Go 项目有没有并发安全问题”，可以用下面的简化流程理解：

```text
启动 claude
   ↓
main.tsx
加载配置，初始化工具和上下文，启动 REPL
   ↓
REPL 接收用户请求
   ↓
QueryEngine 推进任务
   ├─ 模型分析任务
   ├─ 调用 Grep / Read / Bash 等工具
   ├─ 将工具结果交回模型
   └─ 根据结果继续循环，直到本轮任务结束
   ↓
REPL 展示最终结果
```
