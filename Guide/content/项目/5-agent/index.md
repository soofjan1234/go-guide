---
title: go-agent
weight: 50
date: 2026-06-12
draft: false
---

# 描述

1. 使用 Go 实现多智能体框架，抽象 Simple、ReAct、Reflection、Plan-and-Solve 四类 Agent，打通模型调用、工具执行、结果回传和迭代推理链路。
2. 支持 Skill 扩展机制，通过元数据扫描、模型按需加载和正文缓存降低上下文开销；支持子 Agent 任务委派、工具权限隔离及任务摘要回传。
3. 实现上下文工程与会话恢复机制，基于 Token 预算进行历史压缩、相关内容筛选和工具输出截断，并持久化对话、配置、工具 Schema 哈希及文件缓存，恢复时执行一致性校验。

# 1. 多智能体架构

## 为什么要设计 Simple、ReAct、Reflection、Plan-and-Solve 四种 Agent？它们分别适合什么场景？

因为任务复杂度不一样，没必要所有问题都走最重的流程：
1. Simple 适合直接问答
2. ReAct 
   - 擅长应对动态不确定性，需要根据工具返回的实时数据来决定下一步干什么，
   - 适合边思考边调用工具
3. Plan-and-Solve 
   - 宏观把控全局，避免 ReAct 在长步骤中“走一步看一步”导致跑偏、死循环或迷失方向
   - 适合步骤多、依赖关系明显的复杂任务
4. Reflection 
   - 追求极高准确率和逻辑严密性，容错率极低，愿意用“多轮 Token 消耗”换取“高质量”
   - 适合对质量要求高、需要自我检查的任务。

## 从用户输入开始，一次 ReAct Agent 请求在项目中的完整执行顺序是什么？

1. 先把系统提示词、历史消息和用户输入组装起来，再把可用工具的 Schema 一起发给模型。
2. 模型如果要调用工具，Agent 就执行工具、回填结果，再发起下一轮模型调用
3. 模型直接回答或调用 Finish 后，本次请求结束并保存消息和统计信息。

## Plan-and-Solve Agent 如何拆分规划阶段和执行阶段？

1. Planner 的输出是可被程序消费的结构化计划 []string，因此需要专门的 generate_plan 约束。
2. Executor 要逐步执行，并维护“完整计划 + 已完成步骤结果”的执行上下文，还可能调用业务工具

## Reflection Agent 的“执行—反思—改进”流程

ReflectionAgent 没有像 Plan-and-Solve 那样拆出独立的 Planner、Executor 类型。

它把三个“角色”直接写成了同一个 Agent 的三个方法：
- executeTask：相当于 doer，先产出初稿。
- reflectOnResult：相当于 reflector，审查初稿。
- refineResult：相当于 reviser/editor，基于反馈重写。

它们共用同一个 a.LLM 和同一个 a.SystemPrompt，只是每次换不同提示词。

## 模型一次返回多个 Tool Call 时，项目如何并行执行并保持结果顺序正确？

ReAct Agent 为每个调用启动 goroutine，用 `WaitGroup` 等待完成，并提前按调用数量创建结果切片。每个 goroutine 只写入自己的下标，所以即使完成时间不同，最终回填顺序仍与模型返回顺序一致。

## 并行调用工具有什么要点

1. 需要区分可并行和有依赖
2. 工具职责尽量细分独立
3. 异步并发执行
4. 局部失败处理+超时控制

# 2. Skill

## 元数据扫描

1. NewSkillLoader 初始化后调用 scanSkills，遍历 skills 目录下的一级子目录；
2. 只接受包含 SKILL.md 且 frontmatter 同时具备 name 和 description 的目录。
3. 它把名称、描述、文件路径和目录路径放进 MetadataCache

## 模型按需加载
创建 SkillTool 时，会通过 GetDescriptions() 将所有技能的“名称 + 描述”加入该工具的说明。因此模型能知道“有哪些能力”，但不会一开始拿到所有 Skill 正文。只有模型实际调用 Skill(skill=xxx)，Run 才加载对应 Skill。

## 正文加载与缓存
GetSkill 先按 Skill 名查询 SkillsCache；未命中才读取对应 SKILL.md，解析 frontmatter 后取正文，构造 Skill 并写入缓存。

# 3. 子 Agent 委派与容错

## 为什么需要子 Agent，而不是让主 Agent 持有全部工具并完成所有工作？

子 Agent 可以把复杂任务拆开，并使用独立上下文处理某个小目标，减少主 Agent 的上下文压力。它还可以只拿到任务需要的工具，权限边界更清楚，失败影响也更容易控制。

## 子 Agent 的只读、全权限和自定义工具过滤策略是如何实现的？

   `ToolFilter` 统一提供过滤和权限判断。只读策略只放行 Read、LS、Glob、Grep 等工具；全权限策略默认只禁用终端执行类工具；自定义策略支持白名单或黑名单。运行前不允许的工具会被临时禁用，结束后再恢复。

## 如果子 Agent 超时，主 Agent 如何感知并处理？

LLM 客户端默认 60 秒，可由 LLM_TIMEOUT 配置；子Agent会返回响应码和信息

# 4. 上下文工程

目标是控制 Agent 后续发给模型的上下文长度。压缩后，旧消息变成摘要，影响模型还能“看到”什么

## 压缩

`TokenCounter` 优先用 tiktoken 按模型获取编码，失败时退回 `cl100k_base`，再失败则按约四个字符一个 Token 估算，并缓存结果

```
ContextWindow = 128000
历史压缩阈值 = 80%
```

压缩要点：
1. 不可变约束
2. 已完成事项
3. 工具结论 / 证据
4. 待办与决策

## ContextBuilder 如何从候选内容中筛选与当前用户问题相关的信息？

ContextBuilder 的作用是：在发给模型前，把零散且可能很长的信息，筛成一段有限预算内、与当前问题相关的上下文

1. 收集候选内容  
- system instructions：单独一个 packet；
- History：只取最后 10 条消息，合并成一个 packet；
- additionalPackets：例如 related_memory、retrieval、tool_result、task_state。

2. 计算相关性
把当前用户问题按空白切词、转小写，计算：
relevance = 问题中出现在候选内容里的不同词数 / 问题词数
例如问题是 how to implement task tool，候选内容包含 task、tool，相关性就是 2 / 5 = 0.4。

3. 加入新鲜度
新鲜度为 exp(-内容距现在的秒数 / 3600)，大约每小时指数衰减。最终排序分数：
score = 0.7 × relevance + 0.3 × recency

4. 过滤与装箱  
- system instructions 不参与低相关过滤，优先放入；
- 其他 packet 必须 relevance >= 0.3；
- 剩余项按总分降序，能整体装进剩余 token 预算才保留；
- 一个 packet 过大就被整块跳过，不会截取一部分再装。

5. 输出结构
被选中的内容按元数据类型组织成：
```
[Role & Policies]
[Task]
[State]
[Evidence]
[Context]
[Output]
```

## 工具输出为什么同时设置最大行数和最大字节数？截取头部与尾部分别适合什么场景？

前默认值是 2000 行、51200 字节；只要任一超限，就会标记为截断，并把完整输出保存到 tool-output 目录，预览文本放入上下文。

选择截取方向通常看“关键结论在哪里”：
- head（当前默认）：保留开头。适合目录列表、搜索结果、结构化输出的表头/请求参数，或第一处错误就足够定位的问题。
- tail：保留结尾。适合构建日志、测试日志、服务日志；退出码、最终失败原因和最近堆栈通常在末尾。
- head_tail：前后各留一半，中间插入“中间省略”。适合既要看命令/环境/输入，也要看最终结论的场景。

# 5. 会话恢复

目标是让 Agent 重启后能恢复运行状态。它把当前的历史（可能已经压缩过）、配置快照、工具 Schema 指纹、读取缓存、运行 metadata 写入 JSON。

## 会话持久化保存了哪些状态？为什么除消息历史外还要保存配置、工具 Schema 哈希和读取缓存？

会话文件保存 ID、时间、Agent 配置、消息历史、工具 Schema 哈希、读取缓存和元数据。
   
因为这里的“会话恢复”定位是继续工作，不是“严格复现上一次运行”。

## 加载会话时如何检查当前配置与历史配置是否一致？

当前比较 LLM Provider、模型和最大步数，并比较工具 Schema 哈希