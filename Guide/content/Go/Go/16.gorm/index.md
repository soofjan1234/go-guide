---
title: Gorm
weight: 160
date: 2026-05-25
draft: false
---

## 框架对比

1. **Gorm**：
    - 全功能 ORM。链式 API、AutoMigrate、Preload、Hook、软删除开箱即用，社区最大。
    - 依赖反射、复杂查询缺类型检查，SQL 生成走 Callback，排障要懂内部机制。
    - 适合 CRUD 多、迭代快的业务。
2. **Ent**：
    - Schema 生成查询代码，编译期类型安全、无运行时反射；表关系用 Node/Edge 建模，复杂连表更顺。
    - 学习成本高、生成代码量大。
    - 适合社交/权限等图关系、强类型中大型项目。
3. **sqlx**：
    - `database/sql` 薄封装，原生 SQL + Struct 映射，无黑盒。
    - 没有 ORM，CRUD/Join/分页全手写。
    - 适合要控 SQL、抠性能的团队。
4. **sqlc**：
    - 先写 `.sql`，CLI 校验并生成类型安全 Go 方法，性能接近 sqlx、安全接近 Ent。
    - 动态条件拼接弱。
    - 适合 SQL 相对固定、要效率和类型安全的项目。

选型：找工作/常规 Web 用 Gorm；关系复杂且要编译期安全用 Ent；要完全掌控 SQL 用 sqlx；SQL 固定且要生成代码用 sqlc。

