---
title: 运维
weight: 4
date: 2026-06-06
draft: false
---

## Docker 多阶段构建是什么 +1

多阶段构建是在一个 Dockerfile 里写多个 `FROM`，前面的阶段负责编译、构建，最后一个阶段只保留运行需要的产物。

核心目的：
1. 减小最终镜像体积。
2. 避免把源码、编译工具、缓存文件打进运行镜像。
3. 降低镜像攻击面。

### Go 项目如何多阶段构建

```dockerfile
FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o server ./cmd/server

FROM alpine:3.19
WORKDIR /app
COPY --from=builder /app/server /app/server
EXPOSE 8080
ENTRYPOINT ["/app/server"]
```

第一阶段用 Go 镜像编译，第二阶段用更小的运行镜像启动程序。

## 前后端分离项目如何用 Docker 打包部署 +1

常见方式是前端单独构建成静态文件，后端单独构建成 API 服务，再用 Nginx 对外提供统一入口。

整体流程：
1. 前端项目通过 `npm run build` 生成 `dist`。
2. 前端静态文件放到 Nginx 镜像里。
3. 后端项目打包成独立服务镜像。
4. Nginx 负责访问静态资源，并把 `/api` 请求反向代理到后端服务。
5. 用 Docker Compose 或 K8s 把 Nginx、后端、数据库、Redis 等服务编排起来。

### 前端 Dockerfile 示例

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:1.25-alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

第一阶段构建前端，第二阶段只保留静态文件和 Nginx。

### 后端 Dockerfile 示例

```dockerfile
FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o server ./cmd/server

FROM alpine:3.19
WORKDIR /app
COPY --from=builder /app/server /app/server
EXPOSE 8080
ENTRYPOINT ["/app/server"]
```

后端镜像只负责提供 API，不负责托管前端页面。

## Nginx 用来干嘛 +1

Nginx 是高性能 Web 服务器，常见作用：

1. 静态资源服务：托管 HTML、CSS、JS、图片等前端构建产物。
2. 反向代理：把客户端请求转发给后端服务，比如 `/api` 转发到 Go 服务。
3. 负载均衡：多个后端实例之间分摊流量。
4. TLS 终止：处理 HTTPS 证书，对内转发 HTTP。
5. 路由分发：根据域名、路径把请求转发到不同服务。
6. 限流、缓存、压缩：提升稳定性和访问性能。

### Nginx 反向代理示例

```nginx
server {
    listen 80;
    server_name example.com;

    location / {
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://backend:8080/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

`try_files` 常用于前端单页应用，刷新页面时仍返回 `index.html`，交给前端路由处理。

## K8s 是什么

Kubernetes 是容器编排平台，用来管理大量容器的部署、扩缩容、服务发现、滚动更新和故障恢复。

Docker 解决的是单个容器如何构建和运行，K8s 解决的是一组容器如何在多台机器上稳定运行。

### K8s 基本架构

K8s 集群分为控制平面和工作节点。

控制平面负责“做决策”：
1. API Server：集群统一入口，所有操作都通过它。
2. etcd：保存集群状态和配置。
3. Scheduler：决定 Pod 应该调度到哪台机器。
4. Controller Manager：持续对比期望状态和实际状态，并推动系统收敛。

工作节点负责“跑业务”：
1. kubelet：节点上的代理，负责管理本机 Pod。
2. kube-proxy：负责 Service 的网络转发。
3. Container Runtime：真正运行容器，比如 containerd。

### K8s 常见资源对象

1. Pod：最小调度单位，一个 Pod 里可以有一个或多个容器。
2. Deployment：管理无状态应用，支持副本数、滚动更新、回滚。
3. Service：给一组 Pod 提供稳定访问入口。
4. Ingress：管理外部 HTTP/HTTPS 流量入口。
5. ConfigMap：保存普通配置。
6. Secret：保存密码、Token 等敏感配置。
7. PersistentVolume：提供持久化存储。


