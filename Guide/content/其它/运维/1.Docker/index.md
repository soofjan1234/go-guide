---
title: Docker
weight: 10
date: 2026-05-25
draft: false
---

## Docker 为什么比虚拟机快？

![](docker/Docker和虚拟机.png)

Docker 不是虚拟机。容器共享宿主机内核，虚拟机则有完整 Guest OS 和独立内核。

| 维度   | Docker 容器     | 虚拟机           |
| ---- | ------------- | ------------- |
| 隔离层级 | 进程级隔离，共享宿主机内核 | 硬件级虚拟化，独立操作系统 |
| 启动速度 | 秒级甚至更快        | 通常更慢          |
| 资源开销 | 较小            | 较大            |
| 隔离强度 | 相对弱，依赖内核能力    | 更强            |
| 典型场景 | 应用交付、微服务部署、CI | 多系统运行、强隔离环境   |

## Docker Image 和 Container 有什么区别？

1. 状态：镜像是创建容器的模板；容器是镜像的实例，可以处于 created、running、exited 等状态。退出后仍可用 `docker ps -a` 查看。
2. 可读写性：镜像层只读且可共享；容器看到的是可读可写的合并文件系统，每个容器有自己的可写层。
3. 占用空间：多个容器可共享镜像层，运行中的写入、日志和挂载数据另占空间，不能只比较镜像与容器的大小。
4. 关系：一个镜像可以创建多个容器；删除容器时，其默认可写层也会消失，独立 Volume 不随之删除。

### Image 为什么是只读的？

为了安全、分层共享、极速启动和节省空间。

### Container 为什么可以写？

![](docker/OverlayFS.png)

OverlayFS 把多层只读镜像层（lowerdir）和容器的可写层（upperdir）合成一个视图。读取时先查 upperdir，再查 lowerdir；修改镜像中的文件时会先复制到 upperdir，删除则用 whiteout 遮住原文件，不会写穿镜像层。

![](docker/COW.png)

## Docker 为什么镜像这么小？

1. 不包含内核
2. 只保留了程序运行所必须的最小化运行时环境，去掉了图形界面、硬件驱动等

### alpine 为什么只有几 MB？

1. 使用 musl libc 而非 glibc，配合 BusyBox 缩小基础镜像；代价是依赖 glibc 的软件和部分 CGO 程序可能不兼容，不能由体积推断运行速度或安全性。
2. 用 BusyBox 代替标准 GNU 工具集。把几十个最常用的 Unix 工具全部打包合并到了一个极小的可执行文件中（只有 1MB 多）

> 在 Linux 世界中，libc（C 标准库）是所有程序的基石。程序只要运行在 Linux 上，最终都需要通过 libc 来调用 Linux 内核的功能

### scratch 是什么？

scratch 是一个虚拟的、完全空白的镜像。

- 它的体积是 0 字节。
- 它里面没有任何文件：没有文件夹、没有 sh/bash、没有 C 语言库，什么都没有。
- 你不能通过 docker pull scratch 拉取它，因为它只是 Docker 内部保留的一个关键字，代表“绝对的起点”

## 一个 Docker 容器启动以后，里面 PID 1 是谁？

谁是主进程，谁就是 PID 1。你在 Dockerfile 的 CMD 或 ENTRYPOINT 中指定的那个启动命令，运行起来后就是 PID 1。

### PID1 为什么特殊？

1. “收割”僵尸进程
2. 对信号（Signal）的特殊处理机制

> 在 Linux 中，如果我们给普通进程发送 SIGTERM（终止信号），程序默认会退出。但是，Linux 内核对 PID 1 进行了特殊保护：如果 PID 1 进程没有显式地为某个信号注册监听器（Handler），那么它会忽略这个信号。

### 为什么很多 Dockerfile 要用 `exec`？

用新的进程替换当前进程，但保留原来的 PID

Dockerfile 的 JSON exec 形式（如 `ENTRYPOINT ["./app"]`）直接启动应用；shell 形式（如 `CMD ./app`）会经过 `/bin/sh -c`。若用启动脚本，末尾写 `exec ./app` 可让应用接替脚本成为 PID 1，接收 `docker stop` 发给 PID 1 的 SIGTERM。

### 为什么需要 tini？

1. 信号转发：当 docker stop 发送 SIGTERM 给 tini（PID 1）时，tini 会非常敬业地立刻转发给你的应用（PID 2）。
2. 收割僵尸：子进程退出后需要父进程调用 `wait` 回收，否则僵尸会占用进程表中的 PID 项；tini 可以代 PID 1 回收被托管的子进程。这不是业务内存泄漏。

> docker run --init -d my-node-app

---

# 第二层：Dockerfile
## 为什么要 Multi-stage Build？

1. 极大地减少镜像体积
2. 提高安全性（减少攻击面）
3. 更快的传输和部署

Go 服务的最小示例：

```dockerfile
FROM golang:1.24 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /app ./cmd/server

FROM scratch
COPY --from=build /app /app
ENTRYPOINT ["/app"]
```

## 为什么 COPY go.mod 再 go mod download？

先复制依赖清单并下载依赖，使源码变化时尽量复用依赖层；源码最后再复制。

## ENTRYPOINT 和 CMD 有什么区别？

- ENTRYPOINT：容器启动时必定执行的命令（主程序）。	
- CMD：传递给 ENTRYPOINT 的默认参数，或默认命令。

仅设置 `CMD` 时，`docker run 镜像 新命令` 会替换整个默认命令；同时设置 `ENTRYPOINT` 和 `CMD` 时，运行参数通常替换 `CMD`，保留 `ENTRYPOINT`。

---

# 第三层：网络

Docker 默认网络是什么？ bridge

![](docker/Docker网络.png)

## host 网络和 bridge 网络区别？

1. 网络隔离：bridge安全隔离；host直接共享宿主机的网络命名空间
2. IP地址和端口：bridge容器有独立的内网 IP，需要通过 -p 进行端口映射；host 和宿主机共用同一个 IP

## 容器之间如何通信？

1. 通过容器的 IP 地址通信，容器重启后，IP 地址可能会发生变化
2. 使用自定义 Bridge 网络 + 容器名
    - 创建一个自定义网络：docker network create my-net
    - 启动容器 A 并加入该网络：docker run -d --name appA --network my-net nginx
    - 启动容器 B 并加入该网络：docker run -d --name appB --network my-net nginx
    - 此时，容器 A 可以直接通过 http://appB 访问容器 B，Docker 内部的 DNS 会自动把 appB 解析为它的实际 IP。

## docker-compose 为什么服务名可以直接访问？

docker-compose 帮你在后台创建了自定义网络，并利用了 Docker 原生的内置 DNS 服务，实现了通过服务名自动解析 IP 的功能

---

# 第四层：Volume、资源限制

## Bind Mount 和 Volume 区别？

1. 管理：Volume是由Docker统一管理；Bind Mount直接映射宿主机的绝对路径
2. 影响：空的 Volume 首次挂到镜像中已有内容的目录时，Docker 默认会把该目录内容复制进去；已有数据的 Volume 不会反复复制。Bind Mount 不复制，只会遮住容器原目录中的内容。
3. 使用场景：数据库持久化用Volume；热更新用Bind Mount
4. 命令：Volume无需指定地址；Bind Mount显式指定 type=bind，并指定地址

```
docker run --mount source=my-vol,target=/app nginx
docker run --mount type=bind,source=/data/mysql,target=/var/lib/mysql nginx
```

## 为什么 OOM Killer 会杀容器？

容器达到 `--memory` 等 cgroup 内存上限时，即使宿主机还有空闲内存，也可能发生容器内 OOM，内核会选择进程终止。未设置容器上限时，整机内存耗尽也可能触发宿主机级 OOM；排查时先区分这两类。

---

# 第五层：实际部署

## docker-compose.yml 主要写哪些内容？

```yaml
# 1. 核心大板块一：服务定义 (Services) —— 你的容器们
services:
  
  # 服务 A：你的 Go 业务应用
  web-app:
    image: myregistry.com/go-app:v1.2.0    # 1. 镜像地址
    container_name: go-web-service          # 2. 容器名称
    restart: always                         # 3. 重启策略（崩溃后自动重启）
    ports:
      - "8080:8080"                         # 4. 端口映射 (宿主机:容器)
    environment:                            # 5. 环境变量
      - DB_HOST=db-service                  # 直接使用下方定义的服务名作为数据库连接地址
      - DB_USER=root
      - DB_PASSWORD=my_secure_pwd
    volumes:
      - ./config:/app/config                # 6. Bind Mount (挂载配置文件)
      - app-logs:/app/logs                  #    Volume (持久化日志)
    depends_on:                             # 7. 启动顺序依赖（先启动 db，再启动 web）
      - db-service
    networks:                               # 8. 加入自定义网络
      - my-app-net

  # 服务 B：数据库
  db-service:
    image: mysql:8.0
    container_name: mysql-db
    restart: always
    environment:
      MYSQL_ROOT_PASSWORD: my_secure_pwd
      MYSQL_DATABASE: app_db
    volumes:
      - db-data:/var/lib/mysql              # Volume (数据库数据持久化)
    networks:
      - my-app-net

# 2. 核心大板块二：命名卷定义 (Volumes) —— 独立于容器的数据存储
volumes:
  db-data:                                  # 声明一个名为 db-data 的持久化卷
  app-logs:                                 # 声明一个日志卷

# 3. 核心大板块三：自定义网络 (Networks) —— 容器通信的桥梁
networks:
  my-app-net:                               # 声明一个自定义桥接网络
    driver: bridge

```
## Docker Compose常见属性

1. depends_on + healthcheck：保证“容器 A 启动好并能对外提供服务了，容器 B 再启动”

```yaml
 depends_on:
      postgres-db:
        condition: service_healthy

healthcheck:
    test: ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"]
    interval: 10s       # 检查间隔：每 10 秒听诊一次
    timeout: 5s         # 超时时间：如果 5 秒内没响应，算作一次失败
    retries: 3          # 容错次数：连续失败 3 次，正式判定为 "unhealthy"
    start_period: 30s   # 缓冲期/启动期：容器启动后的前 30 秒内，失败不计入次数
```

2. restart：崩溃重启策略

- no：默认，容器退出时不进行任何自动重启。
- on-failure：只有当容器的退出状态码（Exit Code）不为 0（表示由于错误而崩溃/异常退出）时，Docker 才会重启它。可以选择最大重试次数
- always：总是重启
- unless-stopped: 
  - 与 always 非常相似，唯一的区别在于如何对待手动停止的容器。
  - 如果容器被你手动执行了 docker stop，或者在 Docker 守护进程关闭前已经是停止状态，那么当 Docker 守护进程/宿主机重启后，它不会被自动启动。
  - 只有在关机前处于运行状态的容器，才会在重启后恢复运行

3. logging：日志滚动限制

```yaml
logging:
      driver: "json-file"
      options:
        max-size: "10m" # 单个日志文件最大 10MB
        max-file: "3"   # 最多保留 3 个归档，多余的自动删除
```

## 线上升级镜像怎么做？

1. 修改配置文件，比如v1.3.0
2. 对示例中的 `image:` 服务执行 `docker compose pull web-app` 拉取新 tag。
3. 执行 `docker compose up -d --no-deps web-app` 重建服务。单实例 Compose 更新会有中断，不等同于 Kubernetes 多副本滚动更新；只有使用本地 `build:` 构建时才加 `--build`。

# 第六层：底层

Docker 容器并不是真正的“虚拟机”，它本质上只是宿主机上的一个普通进程。之所以能起到虚拟机的效果，全靠 Linux 内核的两个机制：Namespace（命名空间）和Cgroups（Control Groups，控制组）

## Docker 如何隔离

让容器内的进程产生错觉，以为自己独占了整台电脑：
1. PID Namespace：让容器拥有自己独立的进程树
2. NET Namespace：给容器分配独立的网卡、IP 地址和路由表。
3. Mount Namespace：让容器拥有独立的文件系统挂载点。

## Docker 如何限制 CPU？

1. 限制CPU数量
2. 绑定对应CPU核心
3. 限制CPU权重

内存可以用 `--memory` 设 cgroup 上限；CPU 配额和内存上限是运行时约束，不等同于 Kubernetes 调度时使用的 request。

## Containerd（容器运行时）

负责**容器生命周期管理（拉取镜像、启动容器、停止容器）**的核心底层代码

现在的 Kubernetes 就是跳过 Docker 直接与 containerd 交互来运行容器的
