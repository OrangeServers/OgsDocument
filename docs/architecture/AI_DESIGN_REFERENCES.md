# AI 运维设计参考

OrangeServer 的 AI 运维能力优先复用现有资产、凭据、SSH、审批和审计体系。
下列成熟项目用于校验设计方向，不是运行时依赖，也不会被直接嵌入服务。

## 参考项目

### HolmesGPT

[HolmesGPT](https://github.com/HolmesGPT/holmesgpt) 将诊断数据源组织为受控
toolset，并支持 Runbook 驱动的调查流程。OrangeServer 借鉴其“工具分层、按需取证、
先调查后处置”的思路，但首版只实现现有 SSH 通道上的内部 Adapter，不引入 sidecar
或公开插件系统。

### K8sGPT

[K8sGPT](https://github.com/k8sgpt-ai/k8sgpt) 通过 Analyzer 先生成确定性问题描述，
再把结构化结果交给模型解释。OrangeServer 同样把阈值判断、状态分类和证据引用放在
服务端 Analyzer 中，避免让模型直接从无限原始日志中猜测。

### OpenTelemetry

[OpenTelemetry Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/)
提供跨日志、事件、指标和资源的一致命名方式。当前诊断事件采用 OrangeServer 自身的
稳定契约；未来接入 Prometheus、Loki 或其他 Adapter 时，优先映射到兼容的资源与事件
字段，而不是为每个数据源发明新的语义。

## 明确不照搬的部分

- 不把模型直接暴露给任意 Shell、Docker exec 或集群管理凭据。
- 不用危险命令黑名单替代参数白名单和服务端固定探针。
- 不因引入 AI 绕过 OrangeServer 现有的资产权限、凭据授权、审批和审计。
- 不把 1M 上下文当作日志仓库；长证据仍使用持久化、检索和分层摘要。

具体安全边界见[架构与信任边界](TRUST_BOUNDARIES.md)，诊断状态和证据契约见
[AI REST 与 SSE API](../ai/API.md)。
