---
title: 相册2
weight: 21
date: 2026-06-12
draft: false
---

# 时间轴分页查询

## 出现的问题

当用户存了4-5万张照片后，开始稳定出现慢查询，通过 Explain query plan 分析发现，查询只命中了 deleted_at 索引，排序依赖 CASE 动态计算 filming_time 或 modified_at。

## 解决方案

新增了 sort_time 字段，在媒体写入或更新时提前计算排序时间；并建立 (user_id, sort_time DESC, id DESC) 索引。

另一方面，分类查询先获取某个标签下所有 SHA，再通过 WHERE sha IN (...) 查询媒体数据，随着数据量增长，不仅需要在后端拼接超长 SQL，而且由于 IN 参数数量动态变化，数据库无法复用执行计划。因此改为 JOIN 查询，并补充关联索引。
