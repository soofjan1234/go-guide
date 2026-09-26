---
title: Gorm
weight: 160
date: 2026-05-25
draft: false
---

# 框架对比

1. Gorm：
    - 开箱即用，开发效率高、社区最大。
    - 依赖反射、复杂查询缺类型检查，排障要懂内部机制。
    - 适合 CRUD 多、迭代快的业务。
2. Ent：
    - 编译期类型安全、无运行时反射；表关系用 Node/Edge 建模，复杂连表更顺。
    - 学习成本高、生成代码量大。
    - 适合社交/权限等图关系、强类型中大型项目。
3. sqlx：
    - `database/sql` 薄封装，原生 SQL + Struct 映射，无黑盒。
    - 没有 ORM，CRUD/Join/分页全手写。
    - 适合要控 SQL、抠性能的团队。
    - sqlx 在当前生态中已属于维护模式，在新项目中逐渐被替代
4. sqlc：
    - 先写 `.sql`，CLI 校验并生成类型安全 Go 方法，性能接近 sqlx、安全接近 Ent。
    - 动态条件拼接弱。
    - 适合 SQL 相对固定、要效率和类型安全的项目。
5. Bun (uptrace/bun)：
    - Go-PG 的继承者，专注于高性能、SQL 友好的轻量级 ORM。
    - 性能极佳，动态 SQL 构建器（Query Builder）设计优雅，对复杂 SQL 和复杂查询映射支持极好，同时避免了 GORM 过于繁重的黑盒机制。

快速开发/CRUD 密集用 Gorm；关系复杂/追求强类型用 Ent；追求高性能与 SQL 完全掌控用 sqlc；平衡效率与 SQL 透明度（替代 sqlx/Gorm）用 Bun。


## 1. 为什么零值更新会被跳过？

`Updates` 接收结构体时，默认只把**非零值字段**放进更新语句。`0`、`false`、`""` 都是零值，所以这段代码不会把 `age` 改成 `0`，也不会把 `active` 改成 `false`：

```go
db.Model(&User{}).Where("id = ?", 1).
	Updates(User{Age: 0, Active: false})
```

需要明确更新零值时，有两种常用写法：

```go
// map 中列出的字段都会参与更新，包括零值。
db.Model(&User{}).Where("id = ?", 1).
	Updates(map[string]any{"age": 0, "active": false})

// 使用结构体时，Select 明确指定要更新的字段。
db.Model(&User{}).Where("id = ?", 1).
	Select("Age", "Active").Updates(User{Age: 0, Active: false})
```

不要为了绕过零值规则就一律改用 `Save`：`Save` 有全字段更新和在更新未影响行时回退到创建的语义，可能不符合“只更新指定记录”的意图。

还要区分 `Where(&User{Age: 0})`：结构体条件默认也会忽略零值，这是**查询条件**的另一条规则。

## 2. `Preload` 与 N+1 是什么关系？

N+1 指先查出 N 个用户，再对每个用户单独查询订单：一次用户查询加 N 次订单查询。

```go
var users []User
db.Find(&users)
for _, user := range users {
	var orders []Order
	db.Where("user_id = ?", user.ID).Find(&orders) // 循环中每个用户查一次。
}
```

对 `Orders` 使用 `Preload`，GORM 会先查询用户，再用一条包含这些用户 ID 的关联查询批量加载订单。对这个简单的一层关联，通常是两次查询，而不是 N+1 次：

```go
var users []User
db.Preload("Orders").Find(&users)
// 类似：SELECT * FROM users ...
//       SELECT * FROM orders WHERE user_id IN (1, 2, 3, ...) ...
```

因此标题应理解为“**用 Preload 避免常见的 N+1**”，不要写成“Preload 会产生 N+1”。

`Preload` 仍有成本：会读取关联数据，关联层级、返回行数和 SQL 条件都要看实际生成的查询。

## 3. 取消的时候会修改数据吗？

**有可能。**`WithContext(ctx)` 把取消或超时信号传给数据库操作，`cancel()` 本身不是“撤销已写入数据”的命令。

最终结果取决于取消与 SQL 执行、事务提交的先后顺序：

| 取消发生时 | 数据可能怎样 |
| --- | --- |
| SQL 尚未执行 | 操作通常返回取消或超时错误，写入没有发生。 |
| SQL 正在执行，事务尚未提交 | 支持取消的驱动会尝试中止操作；用该 `ctx` 开启的事务若在提交前被取消，`database/sql` 会回滚事务。 |
| 事务已经提交 | 写入已经生效，之后取消 `ctx` 不会自动撤销它。 |

因此，不能看到“请求取消”就断定数据库没有变化。驱动若不支持取消，正在执行的 SQL 还可能等到完成才返回。

GORM 默认会把**单次写操作**放在事务里，但两次独立的 `Create`、`Update` 并不会自动组成同一个业务事务。
