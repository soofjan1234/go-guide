---
title: LangGraph 状态保存与人工介入
weight: 80
---

# LangGraph 状态保存与人工介入

上一篇用 State、Node、Edge 组织了工作流。本篇继续解决一个问题：**草稿已经生成，但审核人还没有处理，流程如何保存进度，等审核完成后继续？**

用一个回复审核流程贯穿全文：生成草稿，暂停等待人工审核；批准后结束，修改后重新提交审核。示例用固定文本模拟生成，不调用模型，也不实际发送邮件。

## 1. Checkpointer：保存执行检查点

State 表示当前业务数据，例如原始问题、回复草稿和审核结果。Checkpointer 则负责保存工作流的检查点，让后续执行能够找到此前的数据和执行位置。

检查点不只是把 State 转成 JSON 保存下来，还包含下一步任务等执行信息。因此恢复流程时，不需要自己根据一个 `status` 字段推测该运行哪个节点。

| 内容 | 在审核流程中的例子 |
| --- | --- |
| 状态数据 | 原始问题、已生成的草稿、草稿版本 |
| 待执行任务 | 接下来需要继续审核节点 |
| 中断信息 | 正在等待审核，以及展示给审核人的内容 |
| 检查点元数据 | 检查点标识、执行步骤等信息 |

### 1.1 在编译时接入

使用 Python 3.11 及以上版本，安装依赖：

```bash
pip install langgraph
```

下面的 Python 代码块按顺序放入同一个文件执行。

```python
from typing import Literal, NotRequired, TypedDict
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

# 整个示例共用同一个保存器实例，让多次调用能读取已有检查点。
checkpointer = InMemorySaver()
```

构图完成后，通过 `builder.compile(checkpointer=checkpointer)` 接入保存器。不要在每次请求时重新创建 `InMemorySaver()`，否则新实例里没有之前的数据。

### 1.2 内存保存与数据库保存

| 保存方式 | 适用场景 | 进程退出后 |
| --- | --- | --- |
| `InMemorySaver` | 学习、测试、单进程演示 | 检查点丢失 |
| PostgreSQL 等数据库保存器 | 长时间审核、服务重启后继续处理 | 已持久化的检查点仍可读取 |

接入数据库时，主要替换编译时传入的保存器，并完成数据库连接和检查点表初始化；本文不展开数据库部署。

数据库保存的是状态与执行信息，不会把 Python 调用栈和所有局部变量原封不动保存下来。跨进程恢复还需要加载兼容的图定义，并连接同一个检查点存储。

## 2. thread_id：找到同一段流程

有了保存器，还需要告诉它“当前操作对应哪段流程”。这个标识就是 `thread_id`：

```python
config = {"configurable": {"thread_id": "reply-review-001"}}
```

它放在执行配置中，不必再写入 State。示例可以把一封待处理邮件的审核流程对应到一个稳定 ID。

- **使用相同 ID**：访问同一线程下已保存的状态与检查点。
- **使用不同 ID**：进入另一条独立线程，不会自动继承前一条线程的草稿。
- **恢复待审核流程**：使用原来的 ID，同时传入 `Command(resume=...)`。

注意：相同 ID 只负责关联状态，**不代表传入任何数据都会自动完成审核恢复**。首次输入业务数据与恢复中断，是两种不同操作。

`thread_id` 也不等于用户 ID：一个用户可以有多个审核任务。它只是索引，不是权限凭据；实际服务需要校验用户是否有权审核对应任务，并避免同一任务被并发重复提交。

## 3. interrupt：暂停并等待审核意见

`interrupt(payload)` 把需要展示的内容交给调用方，并暂停当前执行。本例使用普通 `invoke()` 接口，暂停信息出现在返回值的 `__interrupt__` 中；调用会返回，不会一直占着一个函数调用等待人回复。

恢复时再次调用图，传入 `Command(resume=审核意见)`。这个审核意见会成为节点内 `interrupt()` 的返回值。

先定义审核状态和节点：

```python
class ReviewState(TypedDict):
    """保存问题、草稿及人工审核结果。"""

    question: str
    draft: NotRequired[str]
    version: NotRequired[int]
    approved: NotRequired[bool]
    status: NotRequired[str]


def draft_node(state: ReviewState) -> dict:
    """生成固定演示草稿，并初始化第一版审核状态。"""
    return {
        "draft": f"关于“{state['question']}”：请先提供设备型号与故障截图。",
        "version": 1,
        "approved": False,
        "status": "pending_review",
    }


def review_node(state: ReviewState) -> dict:
    """暂停等待审核；批准当前版本，或保存编辑后的草稿以便再审。"""
    # 1. 把已保存的草稿交给外部审核界面，等待恢复输入。
    decision = interrupt({
        "question": state["question"],
        "draft": state["draft"],
        "version": state["version"],
        "actions": ["approve", "edit"],
    })

    # 2. 校验审核输入及其对应的草稿版本。
    if not isinstance(decision, dict):
        raise ValueError("审核意见必须是字典")
    if decision.get("version") != state["version"]:
        raise ValueError("草稿版本不一致，请重新读取待审核内容")
    action = decision.get("action")
    if action == "approve":
        return {"approved": True, "status": "approved"}
    if action == "edit":
        edited = decision.get("draft")
        if not isinstance(edited, str) or not edited.strip():
            raise ValueError("修改后的草稿不能为空")
        return {
            "draft": edited.strip(),
            "version": state["version"] + 1,
            "approved": False,
            "status": "pending_review",
        }
    raise ValueError("仅支持 approve 或 edit")


def route_review(state: ReviewState) -> Literal["done", "review"]:
    """批准后进入完成节点，修改后重新进入审核节点。"""
    return "done" if state["approved"] else "review"


def done_node(state: ReviewState) -> dict:
    """标记审核流程完成，示例不执行外部发送。"""
    return {"status": "completed"}
```

这里的两个方向分别是：

- `interrupt({...})` 的参数：**程序交给审核人的待审内容**。
- `Command(resume={...})` 的参数：**审核人交回程序的审核意见**。

审核意见不会自动变成 State 字段，节点需要读取它、校验它，再返回状态更新。例子中的 `approved` 就是审核节点明确写回的结果。

中断载荷和恢复输入使用字典、字符串、数字等可以 JSON 序列化的数据，不要传数据库连接或模型客户端。

## 4. 完整审核示例与恢复机制

### 4.1 连接审核流程

```text
START → draft → review → 批准 → done → END
                  ↑        
                  └── 修改草稿后再审
```

```python
builder = StateGraph(ReviewState)
builder.add_node("draft", draft_node)
builder.add_node("review", review_node)
builder.add_node("done", done_node)
builder.add_edge(START, "draft")
builder.add_edge("draft", "review")
builder.add_conditional_edges("review", route_review)
builder.add_edge("done", END)
graph = builder.compile(checkpointer=checkpointer)
```

编辑后的草稿先通过节点返回值写入 State，再进入下一轮 `review`。因此下次暂停时展示的是新版本，旧版本的批准不能直接套到新草稿上。

### 4.2 首次运行：生成草稿后暂停

```python
first = graph.invoke({"question": "NAS 无法连接怎么办？"}, config=config)
pending = first["__interrupt__"][0].value
print(pending["version"], pending["draft"])
# 1 关于“NAS 无法连接怎么办？”：请先提供设备型号与故障截图。

snapshot = graph.get_state(config)
print(snapshot.values["status"])
print(snapshot.next)
# pending_review
# ('review',)
```

此时 `draft` 节点已经完成，草稿已经保存在 State 中；`review` 正在等待输入，`done` 尚未执行。

`get_state()` 只读取当前检查点，不会推动图继续运行。`snapshot.values` 是状态数据，`snapshot.next` 是待执行节点；不要把“仍有待执行节点”误认为程序正在后台自动运行。

### 4.3 提交修改：保存新版并再次暂停

```python
edited_text = "请提供 NAS 型号、客户端版本，以及无法连接时的错误提示。"
second = graph.invoke(
    Command(resume={
        "action": "edit",
        "version": pending["version"],
        "draft": edited_text,
    }),
    config=config,
)
pending_again = second["__interrupt__"][0].value
print(pending_again["version"], pending_again["draft"])
# 2 请提供 NAS 型号、客户端版本，以及无法连接时的错误提示。
```

这次调用先恢复第一次审核，保存编辑内容，再沿循环边进入下一次审核并暂停。**一次恢复调用可能再次遇到中断，不一定直接执行到 END。** 调用方要检查是否还有 `__interrupt__`。

### 4.4 批准新版：执行到结束

```python
final = graph.invoke(
    Command(resume={"action": "approve", "version": pending_again["version"]}),
    config=config,
)
print(final["status"], final["approved"], final["version"])
# completed True 2
assert not final.get("__interrupt__")
assert graph.get_state(config).next == ()
```

如果第一版就能批准，直接在首次暂停后提交 `action="approve"` 和第一版的版本号即可，不必先编辑。

| 调用 | 输入 | 结果 |
| --- | --- | --- |
| 第一次 | 问题字典 | 生成第一版草稿，暂停 |
| 第二次 | `Command(resume=编辑意见)` | 保存第二版草稿，再次暂停 |
| 第三次 | `Command(resume=批准意见)` | 标记批准，流程完成 |

### 4.5 恢复时，审核节点从哪里开始？

恢复并不是保留 Python 调用栈后从暂停的那一行直接跳着往下运行。**包含 `interrupt()` 的节点会从头重新执行**；再次走到对应的 `interrupt()` 时，框架把恢复输入作为它的返回值，然后继续后面的代码。

在本例中：

1. `draft_node` 已完成，普通审核恢复不需要重新生成草稿。
2. `review_node` 从头进入，重新构造待审内容。
3. 原来的 `interrupt()` 取得提交的审核意见，继续执行校验和状态更新。
4. 如果编辑了草稿，条件边再次进入 `review_node`，形成一次新的待审核中断。

因此中断前的代码必须允许重复执行。不要把“发送邮件”放在审核节点的 `interrupt()` 前面：第一次运行就会发送，恢复时还可能再发一次。更合理的安排是把外部动作放在批准后的独立节点中，并用业务唯一标识实现幂等，避免失败重试造成重复发送。

此外，不要用一个宽泛的 `try/except Exception` 包住 `interrupt()` 并吞掉异常，因为暂停依赖框架内部的特殊控制信号。一个节点存在多个中断时，也不要随意改变它们的执行顺序，恢复值需要与相应的中断位置匹配。

本例用异常明确拒绝格式错误或版本不符的审核意见；实际接口应在提交恢复前先完成这些校验，并把错误展示给用户。版本检查本身不能代替并发控制。

最终可以记成一句话：**Checkpointer 保存进度，thread_id 找到流程，interrupt 提出等待请求，Command(resume=...) 带回外部输入。**
