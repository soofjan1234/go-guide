---
title: Tool 工具系统
weight: 40
---

Claude Code 能够读取文件、修改代码、执行命令，并不是因为大模型直接拥有操作系统权限，而是因为 **Harness 提供了一套受控的工具执行系统**。模型负责判断调用什么工具、传入哪些参数；Harness 负责工具注册、参数校验、权限控制、执行和结果回传。

# Tool 系统的整体流程

假设用户要求：“读取 `src/config.ts`，把超时时间改为 30 秒，再运行测试。”一次任务可能经历以下过程：

```text
用户提出任务
    ↓
Harness 组装模型请求（System Prompt、Messages、可用 Tools）
    ↓
模型选择 FileRead，生成文件路径参数
    ↓
Harness 校验参数、检查权限、执行读取
    ↓
读取结果作为 Tool Result 返回模型
    ↓
模型分析内容，调用 FileEdit 修改 timeout
    ↓
Harness 执行编辑并返回结果
    ↓
模型调用 Bash 执行测试，依据结果决定下一步
    ↓
模型回复用户
```

这不是一次模型调用完成所有动作，而是 **模型决策 → 工具执行 → 结果反馈 → 再次决策** 的循环。模型发出工具调用不代表执行成功；只有收到实际结果后，才能确认文件是否修改、测试是否通过。

# Tool 抽象：所有工具遵守同一套契约

对模型而言，Tool 只需要三个信息：**函数名**（调用谁）、**参数定义**（传什么）、**功能描述**（什么时候用）。但 Harness 真正执行工具时，还需要找到对应的执行函数，并传入运行时上下文。

```typescript
interface Tool {
  name: string // 工具名
  description: string // 功能描述
  inputSchema: object // 参数定义
  execute(input: unknown, context: ToolUseContext): Promise<unknown> // 实际执行
}
```

这就是统一 Tool 协议的含义：FileRead、Bash、WebSearch 内部实现不同，但都提供相同的调用入口。Harness 可以统一调用 `tool.execute(input, context)`，并处理参数校验、权限、取消和错误反馈，而不必为每个工具重新设计执行流程。

# Input Schema：约定工具接受什么参数

假设模型要读取 `/workspace/src/config.ts`。FileRead 不能只接受一段任意文本，否则执行层无法稳定判断哪个字段是路径。

可以使用 JSON Schema 描述参数：

```json
{
  "type": "object",
  "properties": {
    "file_path": { "type": "string" }
  },
  "required": ["file_path"]
}
```

模型据此生成调用参数：

```json
{
  "file_path": "/workspace/src/config.ts"
}
```

Harness 可以验证 `file_path` 是否存在、类型是否正确。但 **Schema 校验不等于权限检查**：即使参数结构正确，文件也可能不存在，或者目标路径不允许读取。

还要区分 Schema 与上一节提示词工程中的 Tool Prompt：**Schema 说明“参数长什么样”，Tool Prompt 说明“什么时候用、怎么用”。** 

# ToolUseContext：工具运行时需要哪些信息

工具执行通常不是孤立的函数调用。假设 Bash 正在运行一个耗时测试，此时用户按下中断键，Harness 就需要让工具感知取消信号；如果工具需要读取当前会话状态，也必须有受控的访问方式。

 `ToolUseContext` 包含类似以下结构：

```typescript
type ToolUseContext = {
  options: {
    tools: Tools // 当前可用的工具
    commands: Command[] // 当前可用的命令
    mcpClients: MCPServerConnection[] // 已接入的 MCP 服务连接
  }
  abortController: AbortController // 向执行过程传递取消信号
  messages: Message[] // 相关会话消息
  getAppState(): AppState // 读取运行状态
  setAppState(f: (prev: AppState) => AppState): void // 更新运行状态
}
```

这是为突出核心字段而节选的结构，并非全部定义。

例如 Bash 执行测试时收到取消信号，可以尝试终止进程；但传递信号不意味着任何底层操作都一定能立即停止。**ToolUseContext 的意义是统一提供运行时资源，而不是让每个工具自己维护完整会话。**

# tools.ts：注册表决定系统有哪些工具

`Tool.ts` 解决“一个工具应当符合什么契约”，`tools.ts` 则解决“系统目前注册了哪些工具”。

简化后的注册逻辑如下：

```typescript
function getAllBaseTools() {
  return [
    FileReadTool,
    FileEditTool,
    FileWriteTool,
    BashTool,
    WebSearchTool,
  ]
}
```

工具可以按用途理解：

| 类型 | 典型工具 | 能力 |
| --- | --- | --- |
| 文件操作 | FileRead、FileEdit、FileWrite | 读取、修改、写入文件 |
| 搜索与执行 | Glob、Grep、Bash | 查找文件、检索内容、执行命令 |
| 会话控制 | AskUserQuestion、TodoWrite、Plan 工具 | 向用户确认、管理任务状态 |
| 外部集成 | MCP、LSP 工具 | 访问外部服务、语言服务 |
| 协作调度 | Agent、Task、SendMessage | 子任务与 Agent 间协作 |

注册表并不是模型每轮一定能看到的最终工具列表。**工具存在于代码中、已注册、对当前模型可见、最终允许执行，是不同的状态。**

# 动态筛选：为什么有些工具不会提供给模型

假设系统实现了 LSPTool，但当前环境没有启用 LSP 功能，就没有必要把它提供给模型。注册阶段可以通过条件决定是否加入：

```typescript
...(isEnvTruthy(process.env.ENABLE_LSP_TOOL) ? [LSPTool] : [])
```

另一个例子是权限规则。假设当前会话禁止 Bash，Harness 可以在模型请求构造前过滤它：

```typescript
function filterToolsByDenyRules(tools, permissionContext) {
  return tools.filter(
    tool => !getDenyRuleForTool(permissionContext, tool)
  )
}
```

这是源码中权限过滤思路的简化展示。整个过程可以理解为：

```text
注册的工具：FileRead、FileEdit、Bash、WebSearch、LSP
    ↓ 环境筛选：未启用 LSP
候选工具：FileRead、FileEdit、Bash、WebSearch
    ↓ 权限筛选：禁止 Bash
暴露给模型：FileRead、FileEdit、WebSearch
```

模型无法直接调用本轮未提供的工具。不过，**暴露前过滤只是安全机制的一层**：即使 FileEdit 已经暴露，修改具体文件时仍可能需要路径检查、权限判断或用户确认。工具描述中的“请勿修改敏感文件”属于模型指令，不能取代 Harness 的硬性约束。

# 一次 Tool Call 的执行链路

再看“将 `config.ts` 中的 timeout 改成 30”这个例子，可以把一次 FileEdit 调用拆成更细的阶段：

1. **模型生成调用**：选择 FileEdit，给出文件路径和修改内容。
2. **Harness 识别工具**：根据工具名称找到对应实现。
3. **参数校验**：验证输入符合工具 Schema。
4. **权限检查**：确认当前操作、目标路径是否被允许，必要时请求授权。
5. **执行工具**：调用实现逻辑，并传入 ToolUseContext。
6. **返回结果**：把成功信息或错误写回工具结果消息。
7. **模型继续决策**：成功则可能运行测试；失败则分析错误、调整操作或询问用户。

这是一条概念执行链，具体版本的内部函数和检查顺序可能不同。关键在于：**LLM 不直接执行 FileEdit，而是提出结构化调用；Harness 才是真正执行和控制副作用的一方。**

# Tool 系统与 Prompt、Agent Loop 的关系

把已经学过的提示词工程和核心引擎放在一起：

```text
Prompt 系统
  └─ 告诉模型角色、任务规则、工具使用方法
        ↓
Agent Loop
  └─ 让模型持续决策：回答还是调用工具
        ↓
Tool 系统
  ├─ 注册与筛选工具
  ├─ 提供 Schema 和描述
  ├─ 校验、授权与执行
  └─ 将结果返回消息流
        ↓
Agent Loop 根据结果继续
```

三者职责不能混淆：**Prompt 负责指导，Agent Loop 负责循环决策，Tool 系统负责受控执行。** 这也是 Tool 系统比简单地在 Prompt 中写“你可以操作文件”更可靠的原因。

# 总结

理解 Claude Code 的工具系统，重点是掌握四个边界：`Tool.ts` 定义统一契约，`tools.ts` 管理注册集合，动态筛选决定哪些工具提供给模型，执行层负责参数、权限与结果反馈。模型负责决定“做什么”，Harness 负责控制“能否做、如何做、做完结果是什么”。

进一步研究可以围绕具体的 FileRead、FileEdit、Bash 工具实现展开，观察它们如何接入这套统一协议。
