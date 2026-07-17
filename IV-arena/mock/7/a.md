下面是我对这道题的系统设计答案。

**结论先行**

我会选择：

- **WebSocket 用于在线状态实时同步**
- **Heartbeat 心跳用于在线状态续租**
- **定时任务 / 流式消费用于在线时长结算**
- **Redis 存储实时在线状态**
- **MySQL / PostgreSQL 存储在线会话与日报汇总**
- **OLAP / 分区表 / 预聚合支撑历史大规模查询**

不建议只用 Polling。Polling 简单，但实时性差、请求浪费大、离线判断滞后明显。WebSocket 更适合“当前在线员工列表”这类实时状态展示。不过在线时长统计不能完全依赖 WebSocket 的连接断开事件，因为浏览器崩溃、网络抖动、代理断连都可能导致事件不可靠，所以必须用 **心跳 + 超时兜底**。

---

## 1. WebSocket、Polling 还是其他方案？

### 推荐方案：WebSocket + Heartbeat + TTL

原因：

1. **当前在线员工列表需要实时性**
   管理后台希望看到当前在线员工，WebSocket 可以在员工上线、下线、状态变化时主动推送。

2. **员工在线状态是连接型场景**
   WebSocket 天然表示一个持续连接，适合表达“员工当前是否还活跃”。

3. **允许 5 分钟误差**
   可以设置 30 秒或 60 秒心跳，离线超时时间设置为 2 到 5 分钟，满足误差要求。

4. **异常关闭不能只依赖 close 事件**
   浏览器异常关闭、网络断开时，前端可能来不及发离线请求，所以服务端必须根据最后一次心跳时间判断离线。

### Polling 的问题

Polling 可以实现，但有几个缺点：

- 在线列表刷新不够实时
- 每个员工都定时请求，浪费服务端资源
- 大量员工同时轮询会造成周期性流量尖峰
- 离线判断依然要靠超时，不能真正解决异常关闭问题

### 可选退化方案

如果 WebSocket 不可用，可以降级为：

- 前端每 30 到 60 秒发送 heartbeat HTTP 请求
- 管理后台每 10 到 30 秒 polling 在线列表
- 后端仍用 TTL 判断在线状态

也就是说，核心不是 WebSocket 本身，而是 **租约式在线状态模型**。

---

# 2. 整体系统方案

## 核心架构

可以分为几层：

```text
浏览器 / App
   |
   | WebSocket 连接 + 心跳上报
   v
网关 / WebSocket Gateway
   |
   | 连接管理、身份认证、心跳接收
   v
在线状态服务 Online Service
   |
   | 实时状态写 Redis
   | 会话事件写 MQ
   v
Redis
   |
   | 当前在线员工、设备、标签页、最后心跳时间
   v
消息队列 Kafka / Pulsar / RabbitMQ
   |
   | login / heartbeat / logout / timeout events
   v
统计服务 Statistics Service
   |
   | 生成 session、切分自然日、计算在线时长
   v
OLTP 数据库 MySQL / PostgreSQL
   |
   | session 明细、daily summary
   v
OLAP / ClickHouse / Elasticsearch 可选
   |
   | 大规模历史查询、部门职位聚合
```

核心职责：

- **WebSocket Gateway**
  负责连接建立、断开、心跳接收，不承担复杂统计逻辑。

- **Online Service**
  维护实时在线状态，判断员工是否在线，处理多设备、多标签页合并。

- **Statistics Service**
  将在线事件转成可统计的会话段，并生成每日汇总。

- **Query Service**
  查询当前在线列表、历史在线时长、部门职位筛选结果。

---

# 3. 在线状态同步机制

## 3.1 连接维度

不要只用 `employee_id` 表示在线状态，应该至少区分：

```text
employee_id
device_id
browser_session_id
tab_id
connection_id
```

原因是一个员工可能：

- 同时打开多个标签页
- 同时使用多个浏览器
- 同时在电脑和手机登录
- 刷新页面导致旧连接未及时关闭、新连接已经建立

推荐模型：

```text
employee online = 至少存在一个有效 active connection
device online = 该设备下至少存在一个有效 tab / connection
tab online = 最近心跳未超时
```

也就是说，员工在线状态是从连接状态聚合出来的，而不是由某一个连接直接决定。

## 3.2 心跳机制

前端：

- 页面打开后建立 WebSocket
- 每 30 秒发送一次 heartbeat
- heartbeat 携带：
  - employee_id
  - device_id
  - browser_session_id
  - tab_id
  - current_page
  - active / idle 状态
  - timestamp

服务端：

- 收到 heartbeat 后刷新 Redis TTL
- 更新最后心跳时间
- 如果是首次心跳，则创建在线会话
- 如果超过阈值未收到心跳，则认为离线

建议参数：

```text
heartbeat_interval = 30s
offline_timeout = 120s ~ 300s
allowed_error = 5min
```

由于题目允许 5 分钟误差，离线超时可以设置为 3 分钟左右，兼顾准确性和抗网络抖动。

---

# 4. 在线时长统计方式

## 4.1 不建议每次心跳都直接累加时长

直接每次 heartbeat 写数据库并累加在线时长，会有问题：

- 写放大严重
- 心跳重复、乱序会导致统计错误
- 多标签页会重复计时
- 数据库压力大

更好的方式是：

```text
在线事件流 -> session 明细 -> 每日汇总
```

## 4.2 Session 明细模型

每个员工的一段连续在线时间记为一个 online session：

```text
employee_id = 1001
start_time = 2026-07-16 09:00:00
end_time = 2026-07-16 11:30:00
duration_seconds = 9000
end_reason = normal_logout / timeout / connection_closed
```

如果员工跨天在线，需要切分成多天：

```text
2026-07-16 23:50:00 ~ 2026-07-17 00:10:00
```

应该拆成：

```text
2026-07-16 23:50:00 ~ 2026-07-17 00:00:00
2026-07-17 00:00:00 ~ 2026-07-17 00:10:00
```

这样日报统计更简单。

## 4.3 多连接去重

员工同时开多个标签页时，不能简单把所有连接时长相加。

应该统计员工级别的“并集在线时长”。

例子：

```text
Tab A: 09:00 - 10:00
Tab B: 09:30 - 10:30
```

不能算 2 小时，应该算：

```text
09:00 - 10:30 = 1.5 小时
```

实现方式：

- 实时层：Redis 维护 employee 下所有 active connection
- 统计层：把连接 session 合并成员工 session
- 或者在员工从 0 个连接变成 1 个连接时开启 employee_online_session
- 从 1 个连接变成 0 个连接时结束 employee_online_session

推荐后者，更简单：

```text
连接数 0 -> 1：员工上线，创建 employee session
连接数 1 -> 0：员工离线，关闭 employee session
连接数 1 -> 2：不新建员工 session
连接数 2 -> 1：不关闭员工 session
```

---

# 5. 核心数据表设计

## 5.1 employee 员工表

```sql
employee (
  id bigint primary key,
  name varchar(64),
  department_id bigint,
  position_id bigint,
  status tinyint,
  created_at datetime,
  updated_at datetime
)
```

索引：

```sql
idx_employee_department_position(department_id, position_id)
```

作用：

- 支持按部门、职位筛选
- 作为统计查询维表

---

## 5.2 employee_online_session 员工在线会话表

```sql
employee_online_session (
  id bigint primary key,
  employee_id bigint not null,
  start_time datetime not null,
  end_time datetime null,
  duration_seconds int null,
  start_reason varchar(32),
  end_reason varchar(32),
  last_heartbeat_at datetime,
  status tinyint,
  created_at datetime,
  updated_at datetime
)
```

索引：

```sql
idx_employee_time(employee_id, start_time, end_time)
idx_time_range(start_time, end_time)
idx_status_last_heartbeat(status, last_heartbeat_at)
```

作用：

- 保存原始在线区间
- 支持历史回溯
- 支持异常在线扫描
- `status + last_heartbeat_at` 用于超时关闭未结束 session

---

## 5.3 connection_session 连接会话表，可选

```sql
connection_session (
  id bigint primary key,
  employee_id bigint not null,
  device_id varchar(128),
  browser_session_id varchar(128),
  tab_id varchar(128),
  connection_id varchar(128),
  start_time datetime not null,
  end_time datetime null,
  last_heartbeat_at datetime,
  end_reason varchar(32),
  created_at datetime,
  updated_at datetime
)
```

索引：

```sql
idx_employee_connection(employee_id, connection_id)
idx_employee_device_time(employee_id, device_id, start_time)
idx_last_heartbeat(last_heartbeat_at)
```

作用：

- 排查多设备、多标签页问题
- 支持更细粒度审计
- 员工 session 出错时可以重算

如果业务只关心员工级在线时长，可以不长期保存所有 connection_session，或者只保留短期数据。

---

## 5.4 employee_daily_online_summary 日汇总表

```sql
employee_daily_online_summary (
  id bigint primary key,
  employee_id bigint not null,
  stat_date date not null,
  department_id bigint,
  position_id bigint,
  online_seconds int not null default 0,
  active_seconds int not null default 0,
  idle_seconds int not null default 0,
  session_count int not null default 0,
  abnormal_flag tinyint not null default 0,
  created_at datetime,
  updated_at datetime
)
```

唯一索引：

```sql
uk_employee_date(employee_id, stat_date)
```

查询索引：

```sql
idx_date_department_position(stat_date, department_id, position_id)
idx_employee_date(employee_id, stat_date)
```

作用：

- 查询员工每日在线时长
- 支持部门、职位、日期范围筛选
- 避免每次查询都扫 session 明细

---

## 5.5 online_event_log 事件表，可选

```sql
online_event_log (
  id bigint primary key,
  employee_id bigint not null,
  event_type varchar(32),
  connection_id varchar(128),
  device_id varchar(128),
  event_time datetime not null,
  payload json,
  created_at datetime
)
```

索引：

```sql
idx_employee_event_time(employee_id, event_time)
idx_event_time(event_time)
```

作用：

- 审计
- 异常排查
- 数据重放与修正

大规模场景下可以写 Kafka 后落 ClickHouse 或对象存储，不一定进 OLTP 主库。

---

# 6. 在线 / 离线状态判断

## 在线判断

员工在线条件：

```text
存在至少一个未过期 connection
```

Redis 结构可以这样设计：

```text
online:employee:{employee_id} -> set(connection_id)
online:connection:{connection_id} -> hash
```

connection hash 示例：

```text
employee_id
device_id
tab_id
last_heartbeat_at
status
ttl
```

每次 heartbeat：

- 刷新 `online:connection:{connection_id}` TTL
- 把 connection_id 加入 `online:employee:{employee_id}`
- 更新 employee 当前在线状态

## 离线判断

离线有三种来源：

1. **正常关闭**
   - 页面 unload / WebSocket close / 用户退出登录
   - 立即结束 connection

2. **连接断开**
   - WebSocket close 事件触发
   - 可先标记 suspect，不一定立即员工离线
   - 如果该员工还有其他连接，则员工仍在线

3. **心跳超时**
   - 定时任务扫描 last_heartbeat_at
   - 超过 offline_timeout，则关闭 connection
   - 如果员工 active connection 变为 0，则关闭 employee session

最终以服务端超时判断为准。

---

# 7. 准确性保障

## 7.1 多浏览器、多设备、多标签页

关键原则：

```text
连接级别记录，员工级别去重
```

处理方式：

- 每个标签页生成唯一 `tab_id`
- 每个浏览器会话生成 `browser_session_id`
- 每台设备生成或绑定 `device_id`
- 每条 WebSocket 连接生成 `connection_id`
- Redis 维护员工下所有有效连接
- 员工在线时长按连接区间并集计算

避免的问题：

- 多标签页重复累加
- 刷新页面导致旧连接未关闭
- 同时登录多个设备导致在线时长膨胀

---

## 7.2 异常断开、网络抖动、页面关闭

### 页面正常关闭

前端可以用：

- WebSocket close
- `navigator.sendBeacon`
- `visibilitychange`
- `pagehide`

尽量发送离线事件。

但不能依赖它，因为浏览器不保证一定发出。

### 网络抖动

不应一次心跳丢失就判离线。

可以采用：

```text
heartbeat_interval = 30s
offline_timeout = 3min
```

也就是连续多次心跳丢失才判离线。

### 异常关闭

如果浏览器崩溃或电脑断电：

- 不会收到 logout
- 服务端靠 `last_heartbeat_at + timeout` 结束 session
- end_reason 标记为 `timeout`

在线时长最大误差就是 timeout 阈值，控制在 5 分钟内。

---

## 7.3 挂机、空闲在线、异常常在线识别

这是一个重要 tradeoff：  
“在线”不一定等于“有效工作”。

所以建议区分：

```text
online_seconds：系统连接在线时间
active_seconds：用户活跃时间
idle_seconds：空闲时间
```

前端采集用户行为：

- 鼠标移动
- 键盘输入
- 页面点击
- 路由切换
- API 请求
- 订单处理操作
- 通知查看操作

如果连续一段时间无交互，比如 10 或 15 分钟，标记为 idle。

统计时：

```text
在线时长 = 连接存在的时间
活跃时长 = 有交互或业务操作的时间
空闲时长 = 在线但无操作的时间
```

异常常在线识别规则：

- 单次 session 超过 12 小时
- 连续多天 24 小时在线
- active_seconds / online_seconds 过低
- 只有心跳，没有任何业务操作
- 长时间后台标签页在线
- 心跳来源 IP、设备、UA 异常变化

这些不要直接删除，而是打标：

```text
abnormal_flag = 1
abnormal_reason = long_session / idle_too_long / heartbeat_only
```

管理端可以选择是否纳入工作量分析。

---

# 8. 查询设计

## 查询一段时间总在线时长

优先查 `employee_daily_online_summary`：

```sql
select
  employee_id,
  sum online_seconds as total_online_seconds,
  avg online_seconds as avg_daily_online_seconds
from employee_daily_online_summary
where stat_date between ? and ?
  and department_id = ?
  and position_id = ?
group by employee_id;
```

注意平均每日在线时长有两种口径：

1. **按自然日平均**
   ```text
   total_online_seconds / 查询范围天数
   ```

2. **按有在线记录的天数平均**
   ```text
   total_online_seconds / 有在线记录天数
   ```

产品上必须明确，否则指标会产生歧义。  
我建议默认用“查询范围自然日平均”，更适合管理统计。

---

# 9. 关键 tradeoff

## 9.1 实时性 vs 准确性

WebSocket close 可以实时，但不可靠。  
Heartbeat timeout 稍有延迟，但可靠。

所以采用：

```text
实时事件优先，超时机制兜底
```

## 9.2 在线时长 vs 有效工作时长

在线时长容易统计，但可能包含挂机。  
有效工作时长更有业务意义，但采集更复杂，也更敏感。

所以建议同时提供：

- 在线时长
- 活跃时长
- 空闲时长
- 异常标记

不要把它们混成一个指标。

## 9.3 明细数据 vs 汇总数据

明细数据准确、可重算，但查询慢。  
汇总数据查询快，但需要维护一致性。

所以采用：

```text
session 明细保留事实
daily summary 提供查询
event log 支持审计和重放
```

## 9.4 前端上报 vs 服务端判定

前端能提供更多上下文，但不可信、不稳定。  
服务端更可靠，但只能看到连接和心跳。

所以：

```text
前端负责上报意图和行为
服务端负责最终状态裁决
```

---

# 10. 还需要考虑的边界情况

1. **跨天在线**
   必须按自然日切分 session。

2. **员工部门或职位变更**
   历史统计应该按“当时所属部门/职位”还是“当前部门/职位”？
   建议日报表冗余当天的 department_id、position_id，保留历史口径。

3. **服务端时间与客户端时间不一致**
   统计以服务端接收时间为准，客户端时间只作参考。

4. **重复心跳、乱序事件**
   事件要幂等，使用 connection_id + sequence 或 event_id 去重。

5. **员工退出登录**
   主动 logout 应立即关闭所有当前连接。

6. **账号被禁用或权限变化**
   应强制断开连接，并结束在线 session。

7. **WebSocket 服务重启**
   Redis TTL 和客户端重连机制要兜底。
   服务重启后旧连接不能永久保持在线。

8. **Redis 故障**
   实时在线列表可能短暂不准确，但 session 事件应通过 MQ 或数据库保证最终一致。

9. **浏览器后台节流**
   后台标签页定时器可能变慢，所以心跳间隔和超时时间不能设置太激进。

10. **移动端切后台**
   App 或移动浏览器切后台后，心跳可能暂停，需要单独定义是否算在线。

11. **隐私与合规**
   采集活跃行为要明确边界，不应采集具体输入内容。

12. **重复登录策略**
   如果公司只允许单设备在线，则可以新登录踢旧连接；如果允许多设备，则需要并集统计。

---

# 11. 千万级数据下的低延迟查询与扩展性

## 11.1 写入侧扩展

- WebSocket Gateway 水平扩展
- 连接状态放 Redis Cluster
- 在线事件写 Kafka
- Statistics Service 消费事件异步结算
- 数据库按时间分区
- 热数据和冷数据分层存储

## 11.2 查询侧优化

核心策略：不要查原始 session 明细。

使用：

```text
daily summary 表
monthly summary 表
部门 / 职位维度预聚合
ClickHouse 等 OLAP 存储
```

对于常见查询：

- 最近 7 天
- 最近 30 天
- 按部门统计
- 按职位统计
- 员工排行榜

可以做预聚合或缓存。

## 11.3 分区与索引

`employee_online_session`：

- 按 `start_time` 月分区或日分区
- 索引 `employee_id, start_time`
- 历史老分区归档

`employee_daily_online_summary`：

- 按 `stat_date` 分区
- 索引 `stat_date, department_id, position_id`
- 唯一索引 `employee_id, stat_date`

## 11.4 OLAP 方案

当数据达到千万级、亿级后，历史分析建议进入 ClickHouse：

```text
Kafka -> ClickHouse online_event / online_session / daily_summary
```

ClickHouse 适合：

- 时间范围扫描
- group by employee / department / position
- 排行榜
- 多维筛选

OLTP 数据库只保留：

- 最近在线状态
- 最近 session
- 业务事务数据

## 11.5 缓存

可以缓存高频查询：

```text
online:list:department:{department_id}
summary:{date_range}:{department_id}:{position_id}
```

当前在线列表直接从 Redis 读，不查数据库。

## 11.6 数据修正机制

由于心跳、超时、重连可能导致统计延迟，建议：

- 实时统计提供近似结果
- T+1 定时任务重算昨日数据
- 异常 session 可人工或自动修正
- 保留 event log 支持回放

---

# 最终设计摘要

我会用 **WebSocket + 心跳 + Redis TTL** 做实时在线状态，用 **员工级 session** 统计去重后的在线时长，用 **daily summary** 支撑查询，用 **timeout 机制** 处理浏览器异常关闭和网络问题。

这个系统最关键的设计点是：

```text
不要相信单个连接事件；
不要把多标签页时长简单相加；
不要把在线时长等同于有效工作时长；
不要用明细表直接支撑大规模历史查询。
```

在允许 5 分钟误差的前提下，服务端用最后心跳时间兜底结束在线状态，是准确性、复杂度和性能之间比较合理的平衡。