---
title: 提示词工程
weight: 30
---

Claude Code 不依赖一段固定不变的巨大 Prompt，而是将基础身份、环境信息、工具说明和特定任务指导分别组织，在需要时提供给模型。理解这套机制，关键是分清：**指令告诉模型什么、在什么场景生效、最终放在模型请求的哪个位置。**

# 提示词体系

| 类型 | 解决的问题 | 常见位置 |
| --- | --- | --- |
| System Prompt | 模型是谁、基本职责是什么 | 系统级指令 |
| Dynamic Sections | 当前项目、环境和设置是什么 | System Prompt 的组成部分 |
| 自定义 Prompt | 如何替换或补充默认规则 | 系统级指令 |
| Teammate Prompt | 多 Agent 成员如何协作 | 角色附加指令 |
| Tool Prompt | 某个工具何时、如何使用 | 工具描述 |
| 专项 Prompt | 当前特定任务应该怎么完成 | 任务指令或独立模型调用 |

这些名称描述的是**职责分类**，不是六种彼此独立的模型消息类型。

# System Prompt：确定 Agent 身份

基础提示词可由 `constants/prompts.ts` 中的 `getSimpleIntroSection()` 等逻辑生成。它让模型知道自己是面向软件工程任务的交互式 Agent，可以结合可用工具完成任务，并遵守基础行为约束。

例如，用户要求“检查项目依赖”，模型不只是回答应该执行哪些命令，还可以根据可用工具选择读取项目配置、执行检查并反馈结果。**Prompt 只指导行为，实际工具能力和权限由 Harness 控制。**

# Dynamic Sections：动态组装 System Prompt

基础身份通常不足以完成任务。假设用户在 `/workspace/project` 启动 Claude Code，项目提供 `CLAUDE.md`，并设置中文输出，那么模型还需要知道项目规范、工作目录和语言偏好。运行时可以将这些信息分别构造为 Section：

```text
[基础身份] 你是一个编程 Agent。
[Memory] 当前项目使用 TypeScript；遵循 CLAUDE.md 的项目规范。
[Environment] 当前工作目录：/workspace/project。
[Language] 使用中文回答。
[Output Style] 回答简洁。
```

以上是为了理解装配方式而简化的内容，不是完整的实际 Prompt。**Dynamic Sections 是构造 System Prompt 的零件，不是一种新的模型消息。**

实现中使用 `systemPromptSection()` 组织不同来源的内容：

```typescript
const dynamicSections = [
  systemPromptSection('session_guidance', () =>
    getSessionSpecificGuidanceSection(enabledTools, skillToolCommands),
  ),
  systemPromptSection('memory', () => loadMemoryPrompt()),
  systemPromptSection('env_info_simple', () =>
    computeSimpleEnvInfo(model, additionalWorkingDirectories),
  ),
  systemPromptSection('language', () =>
    getLanguageSection(settings.language),
  ),
  systemPromptSection('output_style', () =>
    getOutputStyleSection(outputStyleConfig),
  ),
]
```

这是核心结构的节选。各 Section 的职责如下：

| Section | 提供的信息 |
| --- | --- |
| `session_guidance` | 当前会话工具、Skills 等指导 |
| `memory` | 记忆及项目规则 |
| `env_info_simple` | 工作目录等环境信息 |
| `language` | 语言偏好 |
| `output_style` | 输出风格 |
| `mcp_instructions` | MCP 相关指令 |

这样切换项目、语言或工具集合时，可以调整对应部分，而不必重写整个 System Prompt。

## 动态装配与缓存

“动态”并不意味着每轮都重新计算全部 Section。例如 MCP 服务器可能在轮次之间连接或断开，相关指令就需要考虑更新。实现中存在 `DANGEROUS_uncachedSystemPromptSection()` 等机制，但不能仅凭名称推断所有 Section 的缓存策略；具体更新时机取决于运行时实现。

# 自定义 Prompt：替换还是追加？

假设只想让 Claude Code 用中文回答，没有必要重新定义整个 Agent 身份，可以追加指令：

```bash
claude --append-system-prompt "请使用中文回答"
```

如果要完全自定义默认系统指令，可以替换：

```bash
claude --system-prompt "你是一个代码审查助手"
```

| 参数 | 效果 |
| --- | --- |
| `--append-system-prompt` | 保留默认 System Prompt，追加额外规则 |
| `--system-prompt` | 替换默认 System Prompt |

一般的语言、输出风格或局部约束适合追加。无论替换还是追加，都不能绕过工具权限或运行时校验。

# Tool Prompt：工具的使用说明书

工具不只有参数 Schema。假设用户说“读取 `main.ts`”，模型首先需要知道有一个 Read 工具，以及如何正确调用它。

Schema 描述工具接受什么参数：

```json
{
  "name": "Read",
  "parameters": { "file_path": "string" }
}
```

但 Schema 本身不足以解释工具的适用场景。Tool Prompt 会进一步指导：Read 用于读取本地文件，路径应为绝对路径，不能直接读取目录，并可能存在读取范围限制。模型结合工具描述选择 Read、生成参数，再由 Harness 检查并执行。

| 工具 | 典型使用指导 |
| --- | --- |
| Read | 读取文件，使用绝对路径 |
| Grep | 搜索文件内容 |
| Glob | 查找文件路径 |
| Bash | 执行构建、测试等命令；有专用工具时优先考虑专用工具 |

例如要搜索项目中的 `TODO`，模型可以调用 Grep，而不是默认通过 Bash 执行 `grep -R`。

**Schema 回答“参数是什么”，Tool Prompt 回答“什么时候、怎样用”。** 工具说明通常通过工具定义提供，不必直接拼进 System Prompt。Prompt 是软约束，参数验证和权限检查才是运行时硬约束。

# Teammate Prompt：为协作角色补充规则

假设两个 Agent 协作：Agent A 负责开发，Agent B 负责代码审查。B 除了知道自己是编程 Agent，还需要知道如何将审查结论发送给 A：

```text
你是团队中的代码审查 Agent。
完成审查后，通过 SendMessage 向其他成员传递结论。
不能假设普通文本输出会自动送达 Agent A。
```

**Teammate Prompt 规定如何协作；SendMessage 工具和运行时负责真正投递消息。**

# 专项 Prompt：只为特定任务提供指导

例如用户执行 `/init`，目的是生成项目说明。此时系统需要指导模型重点分析哪些信息，而不是只依赖通用身份指令：

```text
分析当前项目，重点关注：
1. 项目结构和关键模块。
2. 构建、测试命令。
3. 编码规范与架构约定。
根据分析结果生成项目说明。
```

这是简化的任务指导示意。只有执行 `/init` 时才需要此类指令，没有必要让所有普通会话始终携带。

其他专项任务包括：

| 子系统 | 任务指导的用途 |
| --- | --- |
| Memory | 筛选或生成记忆 |
| Tool Summary | 总结过长的工具输出 |
| Prompt Suggestion | 生成输入建议 |
| Sub Agent | 指导特定子任务的执行 |

专项 Prompt 可能作为主会话中的任务指令，也可能用于独立模型调用，例如工具结果总结。因此它不是固定的 System Prompt 类型。

# Prompt 最终如何进入模型请求？

把前面的概念放在一起，主 Agent 的模型请求可以这样理解：

```text
主 Agent 模型请求
├─ System Prompt
│  ├─ 基础身份
│  ├─ Dynamic Sections（Memory、环境、语言等）
│  └─ 适用时附加 Teammate 等角色指令
├─ Tools
│  ├─ 工具 Schema
│  └─ Tool Prompt（描述和使用规则）
└─ Messages
   ├─ 用户输入
   ├─ 历史消息
   └─ 工具执行结果

专项任务：按需提供任务 Prompt，也可能发起独立模型调用。
```


