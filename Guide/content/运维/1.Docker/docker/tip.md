# Docker Excalidraw 画图计划

参考主文档：`[[5-docker]]`

> 原则：**一张图只回答一个问题**。主框讲链路，细节放旁注；每张图控制在 6-8 个主元素内，方便面试时 30 秒讲清。

## 已完成

1. Docker 和虚拟机区别：`Docker和虚拟机.md`
2. 镜像、容器、仓库：`镜像容器仓库.md`
3. Docker 网络：`Docker网络.md`
4. 数据卷：`Docker数据卷.md`

## 本组图

| 图 | 建议文件名 | 类型 | 回答什么问题 |
| --- | --- | --- | --- |
| 1 | `镜像容器仓库.md` | 横向流程图 | Dockerfile、镜像、容器、仓库是什么关系 |
| 2 | `Docker网络.md` | 关系/分层图 | bridge、端口映射、自定义网络怎么工作 |
| 3 | `Docker数据卷.md` | 对比/关系图 | 容器可写层、Volume、Bind Mount 有什么区别 |

---

## 图 1：`镜像容器仓库.md`

**画布**：横向流程图，从左到右讲“构建、分发、运行”。

**配色**

- 输入/说明书：浅黄
- 镜像：浅蓝
- 仓库：浅紫
- 容器：浅绿
- 临时可写层/易丢数据：浅红或灰色旁注

**主流程**

1. **Dockerfile**
   - 框内写：`Dockerfile`
   - 小字：镜像构建说明书

2. **build**
   - 箭头标注：`docker build`

3. **Image**
   - 框内写：`Image`
   - 小字：只读模板 = 应用 + 依赖
   - 旁注：多层只读 Layer，可复用缓存

4. **Registry**
   - 框内写：`Registry`
   - 小字：Docker Hub / Harbor
   - 箭头：`push` / `pull`

5. **run**
   - 箭头标注：`docker run`

6. **Container**
   - 框内写：`Container`
   - 小字：镜像运行后的实例
   - 顶部加一层小框：`Writable Layer`

7. **删除容器旁注**
   - 虚线框：容器删除后，默认可写层也删除
   - 箭头指向数据卷图：长期数据交给 Volume / Bind Mount

**标题**：`Docker：Dockerfile -> Image -> Registry -> Container`

**刻意不画**：Namespace、网络、数据卷细节；这些放到后续图里。

---

## 图 2：`Docker网络.md`

**画布**：中间画宿主机，里面放 `docker0 bridge` 和两个容器；右侧画外部访问；下方放网络模式对比小表。

**配色**

- 宿主机区域：浅灰边框
- docker0 / 自定义 bridge：浅蓝
- 容器：浅绿
- 外部网络/用户：浅紫
- NAT / 端口映射：浅橙

**主结构**

1. **Host**
   - 大框标题：`Host`
   - 内部放 `docker0 bridge`

2. **Container A / Container B**
   - 每个容器内写：
     - 独立 NET Namespace
     - 独立 IP / 端口空间

3. **bridge 模式**
   - 容器箭头连到 `docker0`
   - `docker0` 再连到外部网络
   - 箭头标注：`NAT 出去`

4. **端口映射**
   - 右侧画用户访问：`User -> Host:8080`
   - 再转到容器：`Container:80`
   - 标注命令：`-p 8080:80`

5. **自定义网络**
   - 另画一个小区域：`app-net`
   - 两个容器：`app`、`mysql`
   - 箭头标注：`app -> mysql:3306`
   - 旁注：自定义 bridge 支持容器名 DNS

6. **host / none / overlay 小表**
   - `host`：共享宿主机网络，少 NAT，隔离弱
   - `none`：无网络，极端隔离
   - `overlay`：跨主机网络，Swarm / K8s 类场景

**标题**：`Docker 网络：Namespace + Bridge + NAT`

**面试旁注**

- 默认 bridge 适合单机容器互通
- 端口映射暴露的是宿主机端口
- `host` 模式没有独立端口空间，容易端口冲突

---

## 图 3：`Docker数据卷.md`

**画布**：左侧画容器文件系统分层，右侧对比 Volume 和 Bind Mount。

**配色**

- 镜像只读层：浅蓝
- 容器可写层：浅红
- Volume：浅青
- Bind Mount：浅黄
- 宿主机目录：浅紫

**主结构**

1. **Image Layers**
   - 多层堆叠：`Layer 1`、`Layer 2`、`Layer 3`
   - 标注：只读、可复用

2. **Container Writable Layer**
   - 放在最上方
   - 标注：容器运行时写入
   - 旁注：容器删除后默认随容器消失

3. **Volume**
   - 从容器目录连到 `Docker Managed Volume`
   - 命令小字：`-v mysql-data:/var/lib/mysql`
   - 旁注：适合数据库、上传文件、生产持久化

4. **Bind Mount**
   - 从容器目录连到宿主机路径
   - 命令小字：`-v /host/html:/usr/share/nginx/html`
   - 旁注：适合本地开发、配置文件、日志目录

5. **对比表**

| 维度 | Volume | Bind Mount |
| --- | --- | --- |
| 管理方式 | Docker 管理 | 用户指定宿主机路径 |
| 可移植性 | 更好 | 依赖宿主机目录 |
| 典型场景 | 生产数据 | 开发调试、配置挂载 |
| 风险 | 注意 volume 生命周期 | 容易误改宿主机文件 |

**标题**：`Docker 数据持久化：Writable Layer vs Volume`

**面试旁注**

- 镜像层是只读的，容器写入发生在可写层
- 不要把数据库数据只放在容器可写层
- Volume 更适合生产，Bind Mount 更适合开发和配置注入

---

## 画之前检查清单

- [ ] 每张图只讲一条主线，不把所有 Docker 知识塞进同一张图
- [ ] 主框不超过 8 个，命令和细节用小字旁注
- [ ] 图 1 能讲清：Dockerfile、Image、Registry、Container 的关系
- [ ] 图 2 能讲清：bridge、NAT、端口映射、自定义网络 DNS
- [ ] 图 3 能讲清：可写层为什么不适合持久化，以及 Volume / Bind Mount 区别
- [ ] 所有图都能回链到 `[[5-docker]]`

## 已回写

1. Docker 和虚拟机区别：`Docker和虚拟机.md`
2. 镜像、容器、仓库：`镜像容器仓库.md`
3. Docker 网络：`Docker网络.md`
4. 数据卷：`Docker数据卷.md`

生成脚本：`../scripts/generate_docker_excalidraw.py`
