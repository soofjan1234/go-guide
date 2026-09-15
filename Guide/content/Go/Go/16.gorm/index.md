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

