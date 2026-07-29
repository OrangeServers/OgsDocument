# AI Provider 与上下文档位

OrangeServer 使用 OpenAI-compatible Chat Completions、流式输出和 Tool Calling。
预设包含 OpenAI、Anthropic、xAI、DeepSeek、MiniMax、Kimi、Qwen、GLM 和硅基流动。预设只提供
名称与默认 Base URL，管理员仍需确认模型 ID、能力和厂商条款。

> Anthropic 原生 API（Messages 格式）不兼容 OpenAI 协议，预设仅作占位，需将 Base URL
> 指向 OpenAI 兼容的中转代理（如 OpenRouter）才能使用；xAI（`https://api.x.ai/v1`）原生兼容。

## 数据库准备

已有实例启用本版本 AI 前，需要按
[统一升级流程](../operations/UPGRADE.md) 执行 rev48、rev49 和 rev50。不要从
本文复制零散迁移命令，以免漏掉前置版本。

## 配置步骤

1. 进入“系统设置 → AI 模型服务”。
2. 选择 Provider 模板并确认 Base URL。
3. 填写模型 ID 和 API Key。
4. 将模型上下文能力标记为 256K 或 1M。
5. 可先获取模型列表；模型列表最多返回 200 个已去重的模型 ID。
6. 运行 Tool Calling 测试。
7. 选择“仅保存”或“保存并启用”，需要时设为默认 Provider。

获取模型列表只使用已保存密钥，不要求 Provider 已启用或已经选定模型。发现失败
不会向浏览器返回 API Key，也不会把完整上游异常直接暴露给用户。

## API Key 行为

- 密钥使用 `OGS_FERNET_KEYS` 加密保存。
- 管理接口只返回 `api_key_configured: true|false`。
- 页面显示掩码状态，空白输入不会覆盖现有密钥。
- “清除密钥”会同时禁用该 Provider 并取消其默认状态。
- Fernet 密钥丢失后，已保存的 Provider 和 SSH 密钥无法解密，只能重新录入。

## 256K 标准档

`standard_256k` 是所有新会话的默认模式，对应 262,144 token 的管理窗口。它是
OrangeServer 的预算上限声明，不保证厂商一定接受相同长度；管理员必须按照模型
真实能力配置。

## 1M 深度诊断档

`deep_diagnostic_1m` 对应 1,048,576 token。它只在 Provider 的
`context_window_tokens` 明确设置为 1M 时可选：

- 系统不根据模型名称猜测能力；
- 256K Provider 创建 1M 会话会被服务端拒绝；
- 旧 Provider 和旧会话按 256K 兼容；
- 档位在会话创建后固定，切换档位需要新建会话。

“1M”不是要求系统主动填满一百万 token。后续证据化诊断仍应优先使用结构化数据、
按需证据和分层摘要，避免直接发送海量原始日志。

## 压缩策略

当前服务使用跨厂商保守估算，不依赖某一厂商 tokenizer：

- 消息与摘要估算达到窗口的 80% 时尝试压缩；
- 保留最近 4 个用户轮次；
- 摘要只保存目标、已确认条件、结论和失败原因；
- 权威状态、结果集范围和动作状态不由摘要替代；
- 存在待审批动作时不会压缩；
- 摘要失败或为空时保留原对话。

这是一种保护性预算，不是精确的计费 token 统计。实际厂商用量和输出限制仍以
Provider 响应为准。

## 私有 Provider

默认情况下，Base URL 解析到私网、环回或链路本地地址会被拒绝，以降低 SSRF
风险。只有在管理员确认目标是受控模型网关、网络访问策略已限制、证书和 DNS
可信时，才设置：

```dotenv
OGS_AI_ALLOW_PRIVATE_PROVIDER=1
```

该开关放宽目标地址限制，不会替代出口防火墙、DNS 防重绑定、TLS 验证和网关
访问控制。

## Provider 不可用的常见原因

| 原因码/现象 | 含义 |
|---|---|
| `disabled` | 配置已保存但未启用 |
| `key_missing` | 没有可解密的 API Key |
| `model_missing` | 未填写模型 ID |
| 1M 选项不可用 | Provider 能力仍声明为 256K |
| 模型列表为空 | 厂商 `/models` 无返回、兼容性不足或密钥无权限 |

继续排查见 [AI 常见问题](../troubleshooting/AI.md)。
