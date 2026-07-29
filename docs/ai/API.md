# AI REST 与 SSE 契约

本文描述当前已经实现的 Provider、会话、只读诊断、聊天和动作接口。

## 通用约定

- 所有接口都要求有效 OrangeServer 会话。
- 普通用户和管理员接口均经过 CSRF 校验；管理员配置接口额外要求 `admin` 角色。
- JSON 请求使用 `Content-Type: application/json`。
- JSON 成功响应沿用平台统一信封，业务数据同时可能出现在具名字段和 `data` 中。
- 错误使用统一 `code`、`msg` 和相应 HTTP 状态。
- SSE 接口使用 POST，因此浏览器通过 `fetch` 读取流，而不是 `EventSource`。

示例成功信封：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {}
}
```

## Provider

| 方法 | 路径 | 角色 | 说明 |
|---|---|---|---|
| GET | `/ai/providers` | user/admin | 可见 Provider、可用状态和默认项 |
| GET | `/ai/stats` | user/admin/audit | 仪表盘统计：近 N 天（`?days=`，默认 7，上限 30）AI 发起的批量执行按天台次（成功/失败），数据源为 `t_command_log` 中 `log_type='AI 批量命令'` 的逐台审计行，无新增表结构 |
| GET | `/ai/admin/providers` | admin | Provider 配置列表，不含明文密钥 |
| PUT | `/ai/admin/providers/{code}` | admin | 保存 Provider |
| POST | `/ai/admin/providers/{code}/test` | admin | 验证 Tool Calling |
| POST | `/ai/admin/providers/{code}/models` | admin | 用已保存密钥发现模型 |
| POST | `/ai/admin/providers/{code}/clear-key` | admin | 清除密钥并禁用 Provider |

保存 Provider 的主要字段：

```json
{
  "base_url": "https://provider.example/v1",
  "model": "model-id",
  "api_key": "only-sent-when-changing",
  "context_window_tokens": 262144,
  "extra_body": {},
  "enabled": true,
  "is_default": true
}
```

`context_window_tokens` 只接受 `262144` 或 `1048576`。响应使用
`api_key_configured` 表示密钥状态，永远不回传 `api_key`。

## 会话和结果集

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/ai/conversations` | 当前用户最近会话 |
| POST | `/ai/conversations` | 创建会话 |
| GET | `/ai/conversations/{id}` | 会话、消息、工具事件和动作状态 |
| DELETE | `/ai/conversations/{id}` | 删除当前用户会话 |
| GET | `/ai/results/{id}` | 当前用户的权威结果集分页 |

创建会话：

```json
{
  "provider_code": "siliconflow",
  "context_mode": "standard_256k"
}
```

`provider_code` 可省略并使用默认可用 Provider。`context_mode` 可用值：

- `standard_256k`
- `deep_diagnostic_1m`

会话详情支持 `?action_summary=1`，只返回最近动作摘要，供运行中轮询使用。结果集
支持 `page` 和 `page_size`，其中 `page_size` 范围为 1–100。

资源 ID、会话和动作都按当前用户隔离。不能把其他用户或其他会话的 ID 作为能力
凭证。

## 受控诊断 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/ai/diagnostic-profiles` | 服务端固定只读档案及参数 schema |
| POST | `/ai/diagnostics` | 启动诊断并返回 Run |
| GET | `/ai/diagnostics/{run_id}` | 当前用户的权威 Run 快照 |
| POST | `/ai/diagnostics/{run_id}/cancel` | 请求取消未结束 Run |
| GET | `/ai/diagnostics/{run_id}/evidence` | 当前用户的解密、脱敏证据 |
| GET | `/ai/diagnostics/{run_id}/report` | 确定性规则报告 |

直接启动示例：

```json
{
  "profile_id": "disk_usage",
  "result_set_id": "server-generated-result-set",
  "conversation_id": "optional-conversation-id",
  "system_user_id": 12,
  "parameters": {}
}
```

也可以传 `target_ids`，但服务端仍会重新验证全部资产和系统用户权限。单次最多
10 台；`target_ids` 和 `result_set_id` 至少提供一个。使用结果集并同时提供
`conversation_id` 时，两者必须属于同一会话。

`POST /ai/diagnostics` 是普通 JSON 请求，当前调用会等待采集和规则分析完成后返回
Run。通过聊天 `run_diagnostic` 工具启动时，进度会作为聊天 SSE 事件实时发送。

Run 的权威状态为 `queued`、`running`、`completed`、`partial`、`failed` 或
`cancelled`；类型中还为中断和过期恢复保留 `interrupted`、`expired`。证据接口
只允许 Run 所有者访问，内容带 `untrusted: true`。报告 Finding 的
`evidence_ids` 只能引用同一 Run 的证据。

详情见 [受控只读诊断](DIAGNOSTICS.md)。

## 聊天 SSE

```http
POST /ai/chat
Content-Type: application/json
Accept: text/event-stream
```

```json
{
  "conversation_id": "server-generated-id",
  "message": "查询我能访问的在线资产"
}
```

每个 SSE 帧同时提供标准 `event` 字段和 JSON `data.type`：

```text
event: assistant.delta
data: {"type":"assistant.delta","run_id":"...","content":"..."}

```

| 事件 | 关键字段 | 含义 |
|---|---|---|
| `run.started` | `run_id`, `conversation_id` | 一次 Agent 运行开始 |
| `assistant.delta` | `run_id`, `content` | 模型文本增量 |
| `tool.started` | `id`, `tool`, `arguments` | 工具开始 |
| `tool.completed` | `id`, `tool`, `result`/`error` | 同一工具完成 |
| `approval.required` | `action_id`, `expires_at` | 需要用户确认 |
| `diagnostic_started` | `event_seq`, `run_id`, `profile_id` | 只读诊断开始 |
| `diagnostic_progress` | `event_seq`, `run_id`, `asset` | 逐资产探针进度 |
| `diagnostic_evidence` | `event_seq`, `run_id`, `evidence_id` | 新证据已保存 |
| `diagnostic_completed` | `event_seq`, `run_id`, `report` | 完成或部分完成 |
| `diagnostic_failed` | `event_seq`, `run_id`, `message` | 失败或取消 |
| `run.completed` | `waiting_for_approval` | 本轮正常结束 |
| `run.failed` | `message` | 本轮失败 |

`tool.started` 和对应的 `tool.completed` 使用相同 `id`。客户端应更新同一条时间线
记录，而不是追加两条卡片。`assistant.delta` 是展示增量；刷新后的权威内容来自
会话详情和诊断 Run 快照。诊断事件带递增 `event_seq`，Run 的
`latest_event_seq` 可用于客户端判断快照新旧；当前没有公开事件重放接口。

同一会话一次只允许一个运行锁；单轮最多执行有限个工具步骤，同一轮最多创建一个
待审批批量动作。

## 动作审批

| 方法 | 路径 | 响应 |
|---|---|---|
| POST | `/ai/actions/{id}/approve` | SSE |
| POST | `/ai/actions/{id}/cancel` | JSON |

审批 SSE：

| 事件 | 关键字段 | 含义 |
|---|---|---|
| `action.progress` | `action_id`, `alias`, `status`, `output`, `error` | 单资产进度 |
| `action.completed` | `summary`, `outcome`, `results`, `status` | 最终聚合结果 |
| `run.completed` | `action_id` | 审批流完成 |
| `run.failed` | `action_id`, `message` | 校验或执行失败 |

`action.completed.results` 只返回资产别名，不返回主机 ID/IP。单项输出限制为 8,192
字符，错误限制为 2,048 字符；截断项带 `truncated: true`。

审批不是对模型建议的盲信。服务端会原子认领动作并重新验证所有权、有效期、
`result_set_id`、资产权限、系统用户权限、目标数量和危险命令规则。

## 保留和并发

- AI 会话和结果集默认 TTL：7 天。
- 每用户最多会话：20。
- 待审批动作默认 TTL：10 分钟。
- 会话展示事件最多保留最近 200 条。
- 诊断原始证据默认写入 7 天到期时间，过期后证据接口不再返回；结构化报告、
  Run 快照和事件默认在 90 天后级联删除。管理员可通过环境变量调整两类保留期。
- 会话删除时如果仍有待审批动作会返回冲突。

## OpenAPI

OrangeServer 提供 `/openapi.json`、`/openapi.yaml` 和 `/apidocs`。AI 路由因需要
REST 动词、URL 参数和 POST SSE 而单独注册，当前生成文档可能未完整覆盖所有 AI
事件字段。集成前应同时核对本文、当前版本的 `app/api/ai_api.py` 和运行中响应；
发现不一致请提交文档修复。
