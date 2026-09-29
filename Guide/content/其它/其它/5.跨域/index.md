---
title: 跨域
weight: 50
date: 2026-06-06
draft: false
---
## 什么是跨域 +1
网页 A 的脚本访问不同源的接口 B 时，浏览器按同源策略与 CORS 响应头判断脚本能否读取结果。请求是否发到后端，取决于它是否需要预检及预检是否成功。

### 如何判断跨域
**同源策略（Same-Origin Policy）**：是指两个 URL 的 **协议（Protocol）、域名（Host）、端口（Port）** 必须完全一模一样。只要这三者中有任意一个不同，那就是跨域

同源策略主要限制脚本读取跨源响应；普通 HTML 表单仍可跨源提交，因此服务端还需考虑 CSRF 防护。

### 跨域报错时，后端的接口到底有没有收到请求？
对满足条件的简单请求，浏览器会发出实际请求，后端可能已处理，但若响应缺少允许该来源的 CORS 头，脚本无法读取结果。带 `Content-Type: application/json`、`Authorization` 或其他非简单请求头时，浏览器通常先发 `OPTIONS` 预检；预检失败，实际业务请求不会发送。判断时先查网络面板里的 `OPTIONS` 和实际请求。

## 如何解决跨域 +1
1. 后端配置CORS（跨源资源共享）
	1. 不带凭证的公开接口可以用 `Access-Control-Allow-Origin: *`。若允许 Cookie 等凭证（`Access-Control-Allow-Credentials: true`），则 Origin 必须是明确来源，不能用 `*`。
	2. 预检响应要按需声明 `Access-Control-Allow-Methods` 和 `Access-Control-Allow-Headers`；浏览器请求所带的方法与非简单请求头必须被允许。
	3. 需要跨站 Cookie 时，还要检查 Cookie 的 SameSite、Secure 属性及前端 `credentials` 选项。
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

上例 `proxy_pass` 没有 URI，`/api/users` 会以 `/api/users` 发送给后端。如果写成 `proxy_pass http://localhost:8080/;`，匹配的 `/api/` 前缀会被替换成 `/`，后端收到 `/users`。反向代理让浏览器只访问同源地址，不等于后端自动具备 CORS 配置。
