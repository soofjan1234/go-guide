---
title: AI
weight: 2
date: 2026-05-27
draft: false
---

## AI生成结果不符合预期怎么办 +4

1. 指出错误的地方，描述清楚要改什么
2. 启用plan模式，知道AI会怎么改
3. 规则沉淀，有哪些易犯的错误

## Codex、Cursor区别 +2

1. Cursor是AI的IDE，有Tab补全功能、@符号引用精确上下文注入，同时可以自行确认、否定更改
2. CC是命令行的AI Agent，一个在终端里运行的智能体，自主执行任务
3. Codex也是独立的强力 Agent

功能实现、批量修改、长任务自动化，用 Codex 会更顺手；局部补全、边看边改、随时调整，IDE 体验通常更好

## 用了哪些skill？ +2

superpowers的插件：
1. brainstorm：头脑风暴、需求澄清、方案取舍
2. test-driven-development：测试驱动开发
3. requesting-code-review/receiving-code-review
4. systematic-debugging: 系统化测试，先找根因再修，不直接猜
5. writing-plans/executing-plans
6. verification-before-completion:完成前必须跑验证命令

## 如何确定skill被使用 +1

拿codex来说
1. 看工具或对话的开始有没有出现你想要的skill
2. 看它是否按 skill 的检查清单执行
3. 看它输出的结果是否符合 skill 的执行规范、预期结果

## 如何避免限流、省token +1

1. 出现bug时明确指定改哪里，错误是什么，文件有哪些。
2. 大的行动之前使用plan模式，看流程是否符合预期。
3. 上下文节省：用 @ 精确圈上下文，一个对话只做一件事或一个任务，限定输出范围。

## 讲讲Rules。你们如何维护？ +1

个人rules，放在Cursor Settings → Rules。比如用中文回复，用cmd执行命令，大改前先plan

团队rules，放在仓库 .cursor/rules/*.mdc，做版本管理。比如项目、GO、数据库规范、错误码表。

## 对 AI 的看法？优势和局限是什么？ +1

AI的优势：
1. 能够快速的搭建好一个项目
2. 快速的定位Bug，CodeReview

我的优势：
1. 理解需求，描述给AI
2. AI给的测试边界不全，需要自己考虑更多
3. AI给出技术方案，我来拍板做哪个

## 你怎么用 AI？日常占比？ +1

- CRUD 接口、单元测试、代码 Review 与 Debug，AI 快速生成
- 核心算法、架构设计、业务逻辑，由我主导设计，AI 协助实现细节。


