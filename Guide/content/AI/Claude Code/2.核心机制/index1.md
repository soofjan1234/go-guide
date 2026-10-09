---
title: 核心引擎
weight: 20
---

QueryEngine 是 Claude Code 的会话级任务编排器。它不只调用一次模型，还负责管理消息、协调工具执行，并处理权限、预算、中断等运行约束。

# QueryEngine 与会话

源码注释将其描述为 `One QueryEngine per conversation.`。需要区分三个层次：

| 概念 | 含义 |
| --- | --- |
| Conversation | 持续的会话，持有 QueryEngine 和必要的会话状态 |
| Agent Run | 一次用户输入触发的任务执行 |
| Model Request | Agent Run 中的一次模型 API 请求 |

一次 Agent Run 可能包含多次 Model Request；同一个 Conversation 也可以先后执行多次 Agent Run。会话级对象并不意味着所有状态都永久保留，部分状态会在每轮提交任务时重置。

## 核心状态

| 字段 | 作用 |
| --- | --- |
| `mutableMessages` | 维护会话消息历史 |
| `abortController` | 控制执行中断 |
| `permissionDenials` | 记录权限拒绝 |
| `totalUsage` | 统计模型使用量 |
| `readFileState` | 维护文件读取状态缓存 |
| `discoveredSkillNames` | 记录发现的 Skill 名称 |
| `loadedNestedMemoryPaths` | 记录已加载的嵌套 Memory 路径 |


# submitMessage：一次任务的入口

`submitMessage()` 接收用户输入，准备本次任务的运行环境，并通过异步生成器持续向上层输出消息。文章节选：

```typescript
async *submitMessage(
  prompt: string | ContentBlockParam[],
  options?: { uuid?: string; isMeta?: boolean },
): AsyncGenerator<SDKMessage, void, unknown> {
  const {
    cwd,
    commands,
    tools,
    mcpClients,
    verbose = false,
    thinkingConfig,
    maxTurns,
    maxBudgetUsd,
  } = this.config

  this.discoveredSkillNames.clear()
  setCwd(cwd)
  const persistSession = !isSessionPersistenceDisabled()
}
```

以上是用于说明入口职责的源码节选，并非 `submitMessage()` 的完整实现。

## 为什么使用异步生成器？

`async *` 表示异步生成器，调用者可使用 `for await...of` 逐步接收消息，无需等整项任务完成后一次性返回：

```typescript
for await (const message of engine.submitMessage(prompt)) {
  console.log(message)
}
```

它适合逐步输出模型消息、工具执行相关事件和最终结果。**流式输出是上层消费方式，不等于每条消息都会触发一次新的模型请求。**

## 本轮任务的配置

| 配置 | 用途 |
| --- | --- |
| `cwd` | 当前工作目录 |
| `commands` | 可用命令 |
| `tools` | 可用工具集合 |
| `mcpClients` | MCP 客户端连接 |
| `thinkingConfig` | 模型思考配置 |
| `maxTurns` | 执行轮次限制 |
| `maxBudgetUsd` | 预算限制 |

这些配置决定任务在哪里运行、能使用哪些能力、受到哪些约束。示例中的 `discoveredSkillNames.clear()` 也说明部分状态会在提交新任务时重置。

# Agent Loop：模型与工具的闭环

核心流程如下：

```text
用户输入
   ↓
QueryEngine 组织上下文并调用模型
   ↓
模型输出内容或提出 tool_use
   ↓
如果需要工具：权限检查 → 执行工具
   ↓
将 tool_result 交回模型
   ↓
模型根据新结果继续决策
   ├─ 再次调用工具 → 循环
   └─ 给出最终回答 → 结束本轮任务
```

**模型负责提出工具调用，Harness 负责权限判断、实际执行、错误处理和结果回填。** 模型本身不会直接读取文件或运行命令。

例如用户请求“检查 `main.ts` 的潜在问题”，模型可能先请求 Read，看到文件内容后再请求 Grep 查找相关调用，最后综合工具结果回答。一次用户输入因此可以产生多次模型调用。

# 完整运行示例

用户输入“检查 `main.ts` 是否存在问题”，简化执行过程：

```text
Conversation：QueryEngine 已创建
   ↓
Agent Run：submitMessage("检查 main.ts 是否存在问题")
   ↓
Model Request 1：返回 Read(main.ts) 的 tool_use
   ↓
Harness 检查权限并执行 Read
   ↓
tool_result：文件内容
   ↓
Model Request 2：返回 Grep(...) 的 tool_use
   ↓
Harness 执行 Grep 并回填结果
   ↓
Model Request 3：给出分析结果，不再请求工具
   ↓
本次 Agent Run 结束，保留必要的会话状态
```
