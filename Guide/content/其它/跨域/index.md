---
title: 跨域
weight: 5
date: 2026-06-06
draft: false
---
## 什么是跨域 +1
当你在浏览器里打开网页 A，网页 A 尝试去访问接口 B，如果网页 A 和接口 B 的“源”不一样，浏览器为了安全，就会在底层把这个请求给死死拦住，并抛出一个CORS报错

### 如何判断跨域
**同源策略（Same-Origin Policy）**：是指两个 URL 的 **协议（Protocol）、域名（Host）、端口（Port）** 必须完全一模一样。只要这三者中有任意一个不同，那就是跨域

### 跨域报错时，后端的接口到底有没有收到请求？
请求发出去了，后端也收到了，甚至也把数据返回了，但是浏览器把返回的数据给扣下了

## 如何解决跨域 +1
1. 后端配置CORS（跨源资源共享）
	1. 允许哪一个前端域名访问（生产环境千万别写 *，要写具体的域名）
	2. 允许哪些方法、哪些参数
	3. 允许cookie
2. Nginx反向代理
3. 开发环境时，前端可以配置Proxy，让node服务器去要数据，避免浏览器同源策略

### Nginx配置
```
server {
    listen       9999;       # 大堂经理守住 9999 端口
    server_name  localhost;

    # 1. 凡是直接访问根目录的，都转交给前端服务
    location / {
        proxy_pass http://localhost:3000; 
    }

    # 2. 凡是路径里带着 /api 的，都转交给 Go 后端服务
    location /api/ {
        proxy_pass http://localhost:8080; 
    }
}
``` 