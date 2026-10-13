---
title: 登录
weight: 30
date: 2026-10-13
draft: false
---

## Cookie、Session、JWT 是什么关系？

Cookie 是浏览器保存和携带数据的机制；Session 是服务端维护会话的方式；JWT 是令牌格式。它们可以组合使用：Cookie 可以装 Session ID，也可以装 JWT。

登录认证回答“你是谁”，接口授权回答“你能做什么”。登录成功后，每次访问接口仍需要检查权限。

## Cookie 怎么工作？

服务端通过响应头 `Set-Cookie` 设置 Cookie，浏览器保存后，在满足条件的请求中通过 `Cookie` 请求头带回来。它也可用于偏好设置，不只用于登录。

```http
Set-Cookie: sid=random-session-id; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=1800
```
Cookie 本身是一种浏览器存储和传输机制，浏览器按域名、路径、安全和 SameSite 等规则携带它。登录场景一般在里面放会话 ID，并设置 HttpOnly、Secure 和适当的 SameSite。

## Session 登录流程

1. 用户提交账号密码，服务端验证。
2. 服务端生成不可预测的 Session ID，保存用户身份和会话有效期。
3. 将 Session ID 写入 Cookie，浏览器后续请求携带它。
4. 服务端查询 Session，确认未过期后识别用户，再检查接口权限。
5. 退出时删除或撤销服务端 Session，同时清除浏览器 Cookie。

会话可以放在内存、数据库或 Redis。多实例部署时常用 Redis 共享，并设置 TTL；Redis 故障时的登录行为也需明确。登录成功或权限提升后应更换 Session ID，防止会话固定攻击。

## JWT 是什么？怎么校验？

常见的签名 JWT 有三段：`Header.Payload.Signature`。Header 描述算法等信息，Payload 存放声明，签名用于检测篡改。

**编码不等于加密。**普通签名 JWT 的 Payload 可以读取，不要放密码或其他敏感信息；JWT 也有加密形式，但不能把常见签名令牌当作加密令牌。

### 过期、刷新与退出

Access Token 用于访问接口，通常有效期较短；Refresh Token 用于换取新的 Access Token，需更严格保护，未必是 JWT。

退出时清除客户端令牌并撤销刷新凭证；已签发的 Access Token 仍可能有效到过期。需要立即失效时，可增加撤销名单、用户令牌版本或在线校验，相应地引入服务端状态。刷新凭证轮换并检测旧凭证重用，可以降低被盗后持续换取令牌的风险。

## Session 与 JWT 怎么选？

| 维度 | 服务端 Session | 仅本地校验的 JWT |
| --- | --- | --- |
| 身份状态 | 服务端保存，客户端持有 ID | 声明放在令牌里 |
| 请求验证 | 查询会话存储 | 验签并校验声明 |
| 多实例 | 共享会话存储 | 分发可信密钥及校验规则 |
| 退出与撤销 | 撤销会话即可使后续校验失败 | 通常等过期，或补充撤销机制 |
| 权限变更 | 可查询当前权限；缓存仍需更新 | 令牌内权限可能过时 |

需要集中管理会话和立即撤销时，Session 比较直接；多个服务需要本地验证令牌时，可以考虑 JWT。两者都能支持多实例，JWT 也有验签、密钥管理和撤销成本，要按需求选择。

## 第三方授权与登录

OAuth 2.0 解决“允许应用访问哪些资源”，本身不是完整的身份认证协议。OIDC 在 OAuth 2.0 上补充身份认证，提供 ID Token；不支持 OIDC 的平台则需按其官方接口获取并验证用户身份。

### 授权码 + PKCE 流程

1. 应用生成随机 `state` 和 PKCE `code_verifier`，保存本次请求关联信息。
2. 浏览器跳转到第三方授权页，携带客户端标识、回调地址、scope、state 和由 verifier 计算出的 challenge。
3. 用户在第三方完成登录与授权，第三方回调应用，带回一次性授权码 code 和 state。
4. 应用核对 state，提交 code、原始 verifier 等信息向令牌端点换取令牌；机密客户端还需按平台要求认证自身。
5. OIDC 场景验证 ID Token 的签名、iss、aud、exp 等，以及请求中使用的 nonce；需要更多资料时调用用户信息接口。
6. 将第三方身份映射到本地账号，建立自己的 Session 或签发自己的登录令牌。

授权码不是 Access Token。Access Token 用于访问第三方 API，ID Token 用于向客户端表达认证结果，不能互相替代。

第三方登录通常走授权码加 PKCE。用户在第三方授权后，我们用授权码换令牌，验证第三方身份，再映射本地账号、建立自己的登录态。OAuth 负责授权，OIDC 进一步标准化了身份认证。