---
title: Context 上下文系统
weight: 50
---

Claude Code 刚进入项目时，并没有读完全部代码，却能够了解当前 Git 分支、未提交修改和项目规范。这不是模型天然知道这些信息，而是 **Harness 在请求模型前收集并组织上下文（Context）**，让模型根据当前环境做出判断。

# 上下文系统：为模型准备项目背景

假设用户要求：“修改登录接口，增加 Token 缓存。”如果只把这句话发送给模型，模型不知道项目使用什么框架，也不知道哪些文件已有修改。Harness 可以补充以下信息：

```text
用户请求：
  修改登录接口，增加 Token 缓存

项目上下文：
  当前目录：/workspace/backend
  Git 分支：feature/auth
  Git 状态：auth.go 存在未提交修改
  最近提交：修复 JWT 过期验证

项目规范（CLAUDE.md）：
  - 项目使用 Go + Gin
  - 不允许修改数据库表结构
  - 修改后执行 go test ./...
```

这只是便于理解的示例，不代表 Claude Code 发送给模型的真实消息格式。

| 信息 | 来源 | 作用 |
| --- | --- | --- |
| 用户需求 | 用户输入 | 说明要完成什么任务 |
| Git 上下文 | Harness 收集 | 说明代码仓库当前状态 |
| 项目规范 | CLAUDE.md | 说明开发时应遵循的约定 |

**上下文系统负责提供决策依据，而不是直接执行修改。** 模型仍然需要根据任务读取相关代码、调用工具并检查执行结果。

# getSystemContext()：获取 Git 环境信息

`getSystemContext()` 用于收集与当前仓库相关的环境信息，例如当前分支、默认分支、工作区状态、最近提交和 Git 用户名。核心逻辑可以简化为：

```typescript
const [branch, mainBranch, status, log, userName] =
  await Promise.all([
    getBranch(),
    getDefaultBranch(),
    exec("git status --short"),
    exec("git log --oneline -n 5"),
    exec("git config user.name"),
  ])
```

**为什么需要 Git 信息？** 例如，用户要求修改 `auth.go`，但这个文件已经存在未提交的改动。Harness 将工作区状态提供给模型后，模型就有机会识别并保留这些改动，而不是误以为文件处于干净状态。最近提交也可以提供线索，例如上一笔提交刚修复 JWT 验证逻辑，可能与当前任务有关。

**为什么使用 `Promise.all()`？** 这些查询基本独立，不必等待上一项完成才能开始下一项，因此可以并发执行，减少上下文准备耗时。

需要注意：Git 信息只是收集时刻的快照，也不能代替阅读源码。Harness 提供线索，模型还需要按需进一步调查。

# getUserContext()：加载 CLAUDE.md 项目规范

`getUserContext()` 负责组织用户和项目提供的上下文，其中一个重要来源是 `CLAUDE.md`。可以把它理解为开发者提前写给 Claude Code 的项目说明，例如：

```markdown
# Project Instructions

## 技术栈
- Go
- Gin
- MySQL

## 开发规范
- 新增 API 必须编写测试
- 不允许直接修改数据库 Schema
- 修改已有代码前先阅读相关实现

## 验证
- go test ./...
```

这样，每次提出开发需求时，就不必重复说明相同的项目约定。文章中的加载逻辑可以简化为：

```typescript
const shouldDisableClaudeMd =
  isEnvTruthy(process.env.CLAUDE_CODE_DISABLE_CLAUDE_MDS) ||
  (isBareMode() && getAdditionalDirectoriesForClaudeMd().length === 0)

const claudeMd = shouldDisableClaudeMd
  ? null
  : getClaudeMds(filterInjectedMemoryFiles(await getMemoryFiles()))

setCachedClaudeMdContent(claudeMd || null)
```

这段代码体现三个知识点：

1. **条件加载**：特定运行模式或环境变量可以禁用 `CLAUDE.md` 加载，并非任何时候都无条件注入。
2. **过滤与组织**：先取得相关记忆文件，再筛选需要注入的内容，而不是直接加载所有文件。
3. **缓存结果**：整理后的内容可以缓存，供后续上下文构建使用。

`CLAUDE.md` 并不是模型训练时学到的知识，也不是每次由用户手动输入的消息，而是 **Harness 从文件中读取并注入提示词上下文的项目级指令**。它能够指导模型，但不等于操作系统级的强制约束。写入大量无关规则还会占用上下文、干扰当前任务，因此应保留真正有用的项目约定。
