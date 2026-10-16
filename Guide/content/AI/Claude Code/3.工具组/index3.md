---
title: AskUserQuestionTool 用户交互
weight: 130
---

Agent 并不总能仅凭现有信息完成任务。当关键需求存在多种合理选择，而且不同选择会明显改变实现时，**AskUserQuestionTool 允许 Agent 把决策交还给用户，再根据回答继续执行**。这属于 Human-in-the-loop（人在回路中）的常见形式。

# 为什么不能总让 Agent 自己决定

假设用户要求：“为 NAS 服务增加缓存。”模型可以提出 Redis、进程内缓存等方案，但如果部署环境、数据一致性要求都不明确，贸然选型可能造成返工。

Agent 可以询问：

```text
你希望缓存部署在哪里？

A. 进程内缓存：实现简单，不依赖外部服务
B. Redis：适合多实例共享缓存
C. 先做单机版本，未来再扩展
```

用户选择后，Agent 才继续设计或实现。这里的重点不是让模型多问问题，而是**只在关键决策无法可靠推断时询问**。

# 工具调用如何进入 Agent Loop

```text
用户提出需求
  ↓
LLM 发现关键约束缺失
  ↓
调用 AskUserQuestionTool（问题、选项等结构化参数）
  ↓
Harness 向用户展示问题
  ↓
等待用户回答
  ↓
回答作为 Tool Result 返回
  ↓
LLM 根据新约束继续执行
```

这与普通 Tool 不同：FileReadTool 等待文件系统返回内容，AskUserQuestionTool 则需要等待用户提供新的信息。

# 为什么使用结构化问题

如果模型只是输出一句“你想怎么做？”，Harness 很难统一展示、记录和恢复这次交互。结构化工具调用可以明确问题、选项和说明，便于前端呈现，也便于把用户的选择作为结果传回模型。

概念上可以写成：

```typescript
type Question = {
  question: string
  options: Array<{ label: string; description?: string }>
}
```

这只是说明数据结构的简化示例，不是源码中的完整参数 Schema。真实实现还需要处理用户取消、跳过或补充自定义回答等情况。

# 什么时候该问，什么时候不该问

**适合询问**：架构方案存在实质差异、关键业务约束缺失、执行后果难以逆转，或者用户偏好直接决定结果。

**不必询问**：已有项目规范明确答案、可以从代码或文档可靠查到，或者只是变量命名、局部实现细节等低影响选择。

例如用户明确说“使用现有 Redis 缓存”，就不应再询问选 Redis 还是内存缓存；如果用户只要求“修复编译错误”，也不应为了每个微小修改都打断用户。

# 用户交互不等于权限审批

这是一个重要区别：

| 机制 | 目的 |
| --- | --- |
| AskUserQuestionTool | 澄清需求、让用户选择方案 |
| 权限审批 | 判断某次操作是否允许执行 |

用户选择了“使用 Redis”，不代表自动授权安装未知软件、修改生产配置或部署服务。**需求决策与操作授权属于不同层次**，Harness 应分别处理。

# 与 Agent Loop 的关系

AskUserQuestionTool 使 Agent Loop 不只是“模型与工具”的闭环，也可以在必要时引入用户决策。好的 Agent 不应把所有问题都推给用户，而应先利用现有上下文作出合理判断，只在真正影响目标或风险的分歧点暂停询问。

参考：[ct12 AskUserQuestionTool](https://www.xuanyuancode.com/learn-claude-code/tutorials/ct12)。
