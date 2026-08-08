# -*- coding: utf-8 -*-
"""M1/S1: 结构化动作 schema、服务端探针与审批 digest。

锁定的安全契约：
- 自动的只读工作只接受服务端自有探针 ID + 校验过的结构化参数；
  模型或调用方不能把任意 Shell 标记为只读。
- 动作快照在审批前不可变地落库；凭据只以 ID 引用存在，永不进入
  快照、digest、Event 或响应。
- digest 绑定动作版本、目标、凭据引用、工具(kind/probe)、规范化
  参数、工作目录、超时与 Step ID；任一字段变化都会使审批失效。
"""
import hashlib
import hmac
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict


# 动作 schema 版本。digest 与快照都绑定该版本；升级动作结构时必须
# 递增，避免旧审批被复用到新语义。
ACTION_VERSION = 1

# 参数值里出现任何 Shell 元字符即拒绝。探针参数只允许纯标量，
# 管道/重定向/命令替换在参数层就被堵死。
_PARAM_FORBIDDEN_RE = re.compile(r"[|&;<>()`$\\\"'\n\r\t]")

# 服务端自有探针：命令模板完全由服务端持有，参数白名单校验。
# 每个探针都是只读探测；新增探针必须过安全评审。
_PROBES: Dict[str, Dict[str, Any]] = {
    'system.load': {
        'title': '系统负载',
        'command': 'uptime',
        'params': {},
    },
    'system.memory': {
        'title': '内存使用',
        'command': 'free -m',
        'params': {},
    },
    'system.disk_usage': {
        'title': '磁盘使用',
        'command': 'df -h',
        'params': {},
    },
    'service.status': {
        'title': '服务状态',
        'command': 'systemctl status {unit} --no-pager',
        'params': {
            'unit': re.compile(r'^[A-Za-z0-9@:._-]{1,128}$'),
        },
    },
}


class ActionValidationError(Exception):
    """探针/参数/动作构造不合法。"""


@dataclass(frozen=True)
class StructuredAction:
    """参与 digest 的不可变动作快照。

    target_id / system_user_id 只是引用；凭据内容永不进入本对象。
    """

    kind: str
    target_id: int
    system_user_id: int
    parameters: Dict[str, Any] = field(default_factory=dict)
    working_directory: str = ''
    timeout_seconds: int = 60
    step_id: str = ''

    def to_canonical_dict(self) -> Dict[str, Any]:
        return {
            'action_version': ACTION_VERSION,
            'kind': self.kind,
            'target_id': int(self.target_id),
            'system_user_id': int(self.system_user_id),
            'parameters': _normalize_params(self.parameters),
            'working_directory': str(self.working_directory or ''),
            'timeout_seconds': int(self.timeout_seconds),
            'step_id': str(self.step_id),
        }


def list_probe_ids():
    """服务端自有探针 ID 列表（只读，供 API 展示与测试）。"""
    return sorted(_PROBES)


def probe_spec(probe_id: str) -> Dict[str, Any]:
    spec = _PROBES.get(str(probe_id or ''))
    if spec is None:
        raise ActionValidationError('unknown probe: %r' % (probe_id,))
    return spec


def _normalize_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """规范化参数：字符串化 + 排序，保证 digest 输入稳定。"""
    normalized = {}
    for key in sorted(params or {}):
        value = params[key]
        normalized[str(key)] = str(value)
    return normalized


def validate_probe(probe_id: str, params: Dict[str, Any]) -> Dict[str, str]:
    """校验探针 ID 与结构化参数，返回规范化参数。

    - 未知探针直接拒绝；
    - 参数集合必须与探针声明完全一致（不允许多余参数，防止注入
      伪装成合法探针的额外字段）；
    - 每个参数值必须匹配探针的白名单正则，且不含任何 Shell 元字符。
    """
    spec = probe_spec(probe_id)
    declared = spec['params']
    params = params or {}
    unknown = set(params) - set(declared)
    if unknown:
        raise ActionValidationError(
            'unexpected parameters: %s' % ', '.join(sorted(unknown))
        )
    missing = set(declared) - set(params)
    if missing:
        raise ActionValidationError(
            'missing parameters: %s' % ', '.join(sorted(missing))
        )
    normalized = {}
    for key, pattern in declared.items():
        value = str(params[key])
        if _PARAM_FORBIDDEN_RE.search(value):
            raise ActionValidationError(
                'parameter %r contains shell metacharacters' % (key,)
            )
        if not pattern.match(value):
            raise ActionValidationError(
                'parameter %r does not match the probe whitelist' % (key,)
            )
        normalized[key] = value
    return normalized


def build_probe_command(probe_id: str, params: Dict[str, Any]) -> str:
    """由服务端模板构造最终命令。

    模板与参数都来自服务端白名单；构造结果再做一次元字符自检，
    双重防御模板维护失误。
    """
    spec = probe_spec(probe_id)
    normalized = validate_probe(probe_id, params)
    command = spec['command'].format(**normalized) if normalized else spec['command']
    if _PARAM_FORBIDDEN_RE.search(command):
        raise ActionValidationError('constructed command failed safety guard')
    return command


def redacted_summary(action: StructuredAction) -> str:
    """生成不含凭据的动作摘要（供快照与列表展示）。"""
    params = _normalize_params(action.parameters)
    param_text = ' '.join('%s=%s' % (k, v) for k, v in params.items())
    summary = '%s %s' % (action.kind, param_text)
    # 控制字符清洗，防止 ANSI/换行注入 UI 与日志。
    return re.sub(r'[\x00-\x1f\x7f]', '', summary).strip()[:255]


def _digest_key(secret_key: str) -> bytes:
    base = str(secret_key or '').encode('utf-8')
    return hashlib.sha256(b'ogs.ai.autonomy.digest.v1:' + base).digest()


def build_action_digest(action: StructuredAction, secret_key: str) -> str:
    """对规范化动作做 HMAC-SHA256 签名。"""
    payload = json.dumps(
        action.to_canonical_dict(), sort_keys=True,
        separators=(',', ':'), ensure_ascii=True,
    ).encode('utf-8')
    return hmac.new(_digest_key(secret_key), payload, hashlib.sha256).hexdigest()


def verify_action_digest(
    action: StructuredAction, digest: str, secret_key: str,
) -> bool:
    if not digest:
        return False
    expected = build_action_digest(action, secret_key)
    return hmac.compare_digest(expected, str(digest))


def action_from_dict(data: Dict[str, Any]) -> StructuredAction:
    """从落库快照重建动作（审批复核用）。缺字段即视为篡改。"""
    try:
        return StructuredAction(
            kind=str(data['kind']),
            target_id=int(data['target_id']),
            system_user_id=int(data['system_user_id']),
            parameters=dict(data.get('parameters') or {}),
            working_directory=str(data.get('working_directory') or ''),
            timeout_seconds=int(data.get('timeout_seconds') or 60),
            step_id=str(data.get('step_id') or ''),
        )
    except (KeyError, TypeError, ValueError):
        raise ActionValidationError('malformed action snapshot') from None
