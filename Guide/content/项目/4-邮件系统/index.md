---
title: 邮件系统
weight: 40
date: 2026-06-12
draft: false
---

## 项目背景

把历史客服回复和FAQ沉淀为知识库，用户发邮件后利用RAG技术找到相似的并生成草稿，最后人工审核发布。

# 技术选型

## Python

项目主要在模型调用、业务迭代，吞吐并不高，Python 的 AI 生态和实验效率更适合当前 MVP

## FastAPI

1. FastAPI 基于 ASGI，适合异步 HTTP 接口：邮件系统有大量外部IO，比如调用模型网关、查询PostgreSQL
2. FastAPI 是直接把 Pydantic 作为“底层基石”来构建的，可以统一处理参数校验

**其它**

1. Flask 更轻，但项目需要类型校验、OpenAPI、异步接口和较多业务契约。如果用 Flask，这些能力通常需要额外组合多个扩展；FastAPI 在这些方面提供了相对统一的默认方案
2. Django 的后台管理、ORM很成熟，对于当前项目可能稍重

## PostgreSQL 与 pgvector

PostgreSQL 同时承载：

- 邮件、审核、候选案例和审计等业务数据；
- LangGraph checkpoint、interrupt 和恢复所需的运行状态；
- 使用 `tsvector` 和 GIN 的关键词检索；
- 使用 pgvector 的向量语义检索。

选择 pgvector 的原因：业务数据本就需要 PostgreSQL，将向量存入同一数据库可以减少独立向量数据库、跨库同步和一致性处理

## snowflake

对比了 Qwen3 0.6B、Nomic v1.5、Snowflake Arctic M v1.5 和 BGE-M3 

测试模拟了常见的 NAS 客服问题，检查模型能否找到对应的产品说明和客服回复示例。

Snowflake 在扩展测试集上的两类检索 Recall@3 均达到 100%，查询延迟 P95 约 58 毫秒，速度和内存占用也是本轮表现最好的

## LangGraph

1. 本项目选择 LangGraph，主要因为需要展示非线性的高级 RAG 工作流：查询改写、证据评估、生成校验、有上限的循环重试、多分支路由和人工兜底。
2. LangGraph 可以通过 Conditional Edges 和 Cycles 显式表达这些路径，并通过 Checkpoint 和 Interrupt 保存、暂停及恢复工作流。  
3. 它替代的是自研 Agent 流程状态机，不替代邮件、审核、知识库等业务表，也不替代权限校验、审计记录和副作用幂等机制。
