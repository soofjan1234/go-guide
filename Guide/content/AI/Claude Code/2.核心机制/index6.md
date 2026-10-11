---
title: File 文件读写与编辑链路
weight: 70
---

Claude Code 不只是给出修改建议，还能读取代码、修改文件并验证结果。关键不是模型直接操作磁盘，而是 **LLM 决定使用什么工具，Harness 负责执行、检查权限并把结果返回给模型**。

# 文件操作的完整链路

假设用户要求：“将 `config.go` 中的超时时间改为 30 秒，并运行测试。”Agent 的工作过程可以简化为：

```text
用户提出修改需求
  ↓
LLM 选择 FileReadTool(file_path)
  ↓
Harness 校验参数、路径和权限 → 读取文件
  ↓
Tool Result 返回原始代码
  ↓
LLM 选择 FileEditTool(目标位置、原内容、新内容)
  ↓
Harness 检查编辑条件与权限 → 写入磁盘
  ↓
展示 Diff / 返回编辑结果
  ↓
LLM 使用 Bash 运行测试，依据结果继续处理
```

这里有两个容易混淆的概念：**工具调用只是模型提出的执行请求，不代表操作已经成功**；文件是否真的修改，需要看 Harness 的执行结果，必要时还要重新读取文件、检查 Diff 或运行测试。

# FileReadTool：为什么读文件也要专门设计

文件读取不是简单封装一个 `fs.readFile()`。源码中通过 `buildTool()` 注册 FileReadTool，并声明其工具名称、描述、路径解析、只读性质和并发安全性质。可以用简化代码理解：

```typescript
const FileReadTool = buildTool({
  name: FILE_READ_TOOL_NAME,
  strict: true,
  isReadOnly() { return true },
  isConcurrencySafe() { return true },
  getPath({ file_path }) { return file_path || getCwd() },
})
```

**`isReadOnly()`** 表示这个工具按设计不应修改文件；**`isConcurrencySafe()`** 表示实现允许安全地并发执行此类读取。二者不同：只读不自动意味着任意操作都能并发执行，仍需由工具实现给出声明。

例如，读取一个 20MB 的日志文件时，系统还需要考虑内容大小、行范围、输出截断以及 Token 预算；读取图片、PDF 或 Notebook 时，也需要区别于普通 UTF-8 文本的处理方式。路径可能是相对路径，还需要结合工作目录解析，并接受权限规则约束。

因此，FileReadTool 的职责不仅是取得字节，还要将文件内容以**模型能够消费、系统能够管理**的方式返回。

# FileEditTool 与 FileWriteTool：为什么要分开

两者的核心差别是修改意图：

| 工具 | 典型用途 | 示例 |
| --- | --- | --- |
| FileEditTool | 定向修改已有文件 | 把 `timeout = 10` 改成 `timeout = 30` |
| FileWriteTool | 新建或整体写入文件 | 新建 `cache.go`，或整体替换文件内容 |

例如原文件包含：

```go
const timeout = 10
const retries = 3
```

用户只要求修改超时，使用定向编辑更符合意图：把 `timeout = 10` 替换为 `timeout = 30`，同时保留 `retries`。如果用整体写入，则需要提供整个文件的新内容，遗漏原有代码的风险更高。

不过，**Edit 不等于天然不会覆盖别人的修改**。稳妥的实现仍要校验原内容是否匹配、处理文件变化与冲突，并检查最终 Diff；具体防护取决于工具版本和实现。

# 为什么编辑需要权限与 Diff

读取和写入的风险不同。读取通常不会改变工作区，而写入可能破坏已有代码、覆盖未提交改动，甚至修改错误的文件。因此编辑链路需要考虑权限审批、路径边界和变更展示。

例如用户要求修改 `config.go`，模型却准备重写整个 `auth.go`。如果 Harness 能在执行前显示目标文件和 Diff，用户就更容易发现操作偏离预期。

```diff
- const timeout = 10
+ const timeout = 30
  const retries = 3
```

Diff 的价值不只是好看，而是把“模型声称做了什么”转换为“用户能够检查的具体变更”。但 Diff 也不能证明修改正确，仍需测试或其他验证。

# 与 Agent Loop 的关系

文件工具本身不会决定业务逻辑。LLM 根据任务选择读取什么、修改哪里；Harness 执行操作并返回 Tool Result；模型再根据结果决定是否继续搜索、编辑或测试。整个过程仍然是 **模型决策 → 工具执行 → 结果反馈 → 再次决策**。

因此，文件系统工具真正重要的地方，是把普通的文件操作升级为具有明确语义、权限边界、可观察结果和变更展示的工程能力。它使 Agent 不只是“生成代码文本”，而是能够参与真实项目的修改流程。
