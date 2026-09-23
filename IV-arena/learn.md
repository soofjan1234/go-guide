熟悉Agent框架及开发、Agent运行原理、Agent系统组件；

对大模型有系统性认知，理解Context Window、Token机制、RL等核心概念；

熟悉Claude Code、OpenClaw等典型Agent内部实现细节

熟悉幻觉，上下文献制，token成本，响应延迟以及基础测试与评测方法

第一阶段：底层基石（大模型核心机制与限制）
├── 1. Token 与 Context Window（BPE、N²复杂度、Attention 衰减、Lost in the Middle）
├── 2. 性能与成本（TTFT、TPOT、Prefill vs Decode、Prompt Caching 缓存优化）
├── 3. 采样与输出控制（Temperature/Logprobs、Function Calling 底层、Grammar 强约束/JSON Mode）
├── 4. 缺陷与安全（幻觉机理、指令漂移/遵循边界）
└── 5. 对齐与推理（RLHF/DPO、DeepSeek-R1 式 RL 强化思维链推理能力）

第二阶段：Agent 理论与核心系统组件在理解 LLM 特性的基础上，拆解 Agent 的内部构成。Agent 运行原理：深入理解 ReAct（Reason + Act）、Plan-and-Solve、Reflection（反思机制）等核心思考 loops。Agent 系统组件：Planning（规划）：任务拆解、子目标生成、Self-Correction（自我修正）。Memory（记忆）：短期记忆（Context 内）与长期记忆（Vector DB、KV Store、Graph Memory）。Tools / Action（工具扩展）：Function Calling、MCP（Model Context Protocol）协议接入与工具使用约束。Profile（角色与设定）：Prompt System Setting 对 Agent 行为模式的约束。

第三阶段：经典 Agent 源码与内部实现剖析通过拆解优秀的开源/商业 Agent，学习工业级架构设计。熟悉典型 Agent 内部实现细节：Claude Code：研究其命令行交互、代码库检索（Code Indexing）、上下文剪枝与压缩（Context Pruning/Compaction）、工具调用流程及工具流安全（Execution Hooks/Approvals）。OpenClaw：分析其自动化 Loop、状态持久化、环境交互与错误自动重试机制。

第四阶段：Agent 框架开发与评测落地将理论与拆解经验转化为实际工程落地能力。熟悉 Agent 框架及开发：掌握流行框架（如 LangGraph、AutoGen、CrewAI 或 Go/TypeScript 自研轻量级框架）的用法与底层架构。实践状态机管理（State Machine）、Multi-Agent 协作模式（如 Supervisor、Swarm 模式）。

基础测试与评测方法（Agent Evaluation）：评测指标：Task Completion Rate（任务完成率）、Tool Call Accuracy（工具调用准确率）、Step Efficiency（步骤效率）、Cost & Latency per Execution。评测方法：LLM-as-a-Judge、Trajectory-based Eval（执行轨迹评测）、Benchmark 数据集构建（如 SWE-bench 等场景测试）。