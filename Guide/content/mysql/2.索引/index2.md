---
title: 索引2
weight: 21
date: 2026-05-25
draft: false
---

## 什么情况会设计索引 +1 

![索引.设计原则](pic/索引.设计原则.png)

- 查询明显变慢，且 EXPLAIN 显示代价高
- WHERE / JOIN 条件稳定、重复出现
- 需要排序、分组，且数据量大
- 有唯一性 / 完整性要求
- 读多写少，或读的性能是瓶颈

## 索引查看 +3

### 预计查看

![索引.EXPLAIN](pic/索引.EXPLAIN.png)

1. type：
    - system / const：极优，通过主键或唯一索引一次定位。
    - eq_ref / ref：较好，常见于普通索引等值查询。
    - range：中等，适用于范围查询。
    - index：全索引扫描，说明虽然扫描的是索引树，但仍然遍历了大量叶子节点
    - All：全表扫描，数据量一大就是危险信号。
2. key：表示实际使用到的索引
3. possible_keys：MySQL 预测可能会用到的索引
4. key_len：联合索引到底命中了多少列
5. extra
    - **`Using index`**：命中了覆盖索引，不需要回表。
    - **`Using index condition`**：触发了 ICP（索引下推），在索引遍历阶段就做了一部分过滤。
    - **`Using filesort / Using temporary`**：说明排序、分组、去重没有很好地利用索引，往往需要进一步优化。
6. rows：预估扫描行数 

### 实际扫描

EXPLAIN ANALYZE（MySQL 8.0.+）
-> Filter: (users.age > 18)  (cost=10.5 rows=25) (actual time=0.081..0.155 rows=30 loops=1)

> 除了 `EXPLAIN`，还有慢查询日志查看，有个开关log_queries_not_using_indexes = ON可以看

### Index Hint（索引提示）

- FORCE INDEX（强制使用索引）
- USE INDEX（建议使用）
- IGNORE INDEX（忽略索引）

## 索引失效 +2

1. 索引列参与运算
    - WHERE age + 1 = 18 或 WHERE YEAR(birthday) = 2020
    - B+树无法对“计算后的结果”进行二分查找，因为树里没有存“计算后的值”。
    - 如果做优化，计算成本、边界都要考虑，更麻烦
2. 格式转换
    - 当字符串和数字进行比较时，MySQL 会自动把字符串转为数字再比较
    - 所以字段 phone 是 VARCHAR 类型，但查询时写成 WHERE phone = 13800000000
    - 但是字段 age 是 INT 类型，但查询时写成 WHERE age = "12"，是可以使用索引的
3. like '%xxx'
    - WHERE name LIKE '%ob'，可能有很多情况，所以不能用索引
4. a or b，有一列不是索引
5. 组合索引没用对
6. 优化器认为全表更快

### 其它

1. or

WHERE A = 1 OR B = 2, 如果 `A`、`B` 都有索引，MySQL 5.0+ 的 **Index Merge（索引合并）** 机制将会生效。引擎会分别并发扫描 A 索引和 B 索引，提取出匹配的主键 ID 集合，并在内存中进行**求并集（Union 去重）**操作，最终拿着并集后的 ID 统一进行回表。

2. null

在 InnoDB 引擎中，B+树索引（二级索引）是记录了 NULL 值的。在 B+树中，所有 NULL 值都会被放在叶子节点的最左边（最小端）。既然索引里有，那么理论上绝对可以走索引。可能走，可能不走的原因还是在优化器的估算

## 为什么用了索引还是慢 +1

![索引慢](pic/索引慢.png)

1. 区分度低，重复的太多
2. 回表次数太多
3. 范围查询导致联合索引后缀利用不足
4. 排序、分页没按索引
4. 返回结果集过大
5. 统计信息不准
