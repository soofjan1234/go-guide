---
title: AI
weight: 2
date: 2026-05-27
draft: false
---

## 不符合预期怎么办 +4

1. 指出错误的地方，描述清楚要改什么
2. 启用plan模式，知道AI会怎么改
3. 规则沉淀，有哪些易犯的错误

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

## 用了哪些skill？ +1

superpowers的插件：
1. brainstorm：头脑风暴、需求澄清、方案取舍
2. test-driven-development：测试驱动开发
3. requesting-code-review/receiving-code-review
4. systematic-debugging: 系统化测试，先找根因再修，不直接猜
5. writing-plans/executing-plans
6. verification-before-completion:完成前必须跑验证命令

## 如何确定skill被使用 +1

1. 看 AI 的输出结构是否符合 skill 的流程，比如 brainstorm 会先拆问题、列方案、比较优缺点。
2. 看它有没有产出对应阶段的结果，比如 tdd 会先写测试或测试用例，再根据失败测试实现功能。
3. 看它是否按 skill 的检查清单执行，比如 code review 会优先指出风险、Bug、缺测试和边界问题。
4. 看工具或对话记录里是否出现 skill 名称、触发说明、执行步骤等痕迹。
