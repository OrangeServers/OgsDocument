# -*- coding: utf-8 -*-
"""M1/S1: 服务端动作策略、预算与敏感路径规则。

策略完全由服务端持有：
- probe（服务端自有探针）是唯一可自动执行的只读动作；
- file_read 永不自动：敏感路径直接拒绝，其余等待精确审批；
- shell 永不自动：read_only 模式直接拒绝，其余等待精确审批；
  含管道/重定向/解释器/下载执行等特征时按高危处理。
- lab_autonomous 仅由管理员维护的 t_host.ai_environment='lab'
  授予；名为 lab 的普通资产组不带来任何自治能力。
"""
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Tuple

from app.ai.autonomy.actions import StructuredAction
from app.ai.autonomy.state import AiEnvironment, RunMode


class ApprovalDecision(str, Enum):
    AUTO = 'auto'
    APPROVAL_REQUIRED = 'approval_required'
    DENIED = 'denied'


class PolicyViolation(Exception):
    """动作命中永久拒绝规则。"""


# ---------------------------------------------------------------------------
# 预算：服务端硬上限不可被调用方抬高
# ---------------------------------------------------------------------------

# 默认值与硬上限来自 docs/ai/ROADMAP.md 的执行预算章节。
BUDGET_LIMITS: Dict[str, Tuple[int, int]] = {
    # field: (default, hard_max)
    'duration_seconds': (3600, 3600),
    'max_loops': (20, 20),
    'max_actions': (30, 30),
    'command_timeout_seconds': (60, 600),
    'step_output_bytes': (65536, 65536),
    'run_artifact_bytes': (2097152, 2097152),
}


@dataclass(frozen=True)
class Budget:
    duration_seconds: int = BUDGET_LIMITS['duration_seconds'][0]
    max_loops: int = BUDGET_LIMITS['max_loops'][0]
    max_actions: int = BUDGET_LIMITS['max_actions'][0]
    command_timeout_seconds: int = BUDGET_LIMITS['command_timeout_seconds'][0]
    step_output_bytes: int = BUDGET_LIMITS['step_output_bytes'][0]
    run_artifact_bytes: int = BUDGET_LIMITS['run_artifact_bytes'][0]

    def to_dict(self) -> Dict[str, int]:
        return {
            'duration_seconds': self.duration_seconds,
            'max_loops': self.max_loops,
            'max_actions': self.max_actions,
            'command_timeout_seconds': self.command_timeout_seconds,
            'step_output_bytes': self.step_output_bytes,
            'run_artifact_bytes': self.run_artifact_bytes,
        }


def parse_budget(payload: Any) -> Budget:
    """从创建请求解析预算；缺省用默认值，越界拒绝而不是静默钳制。"""
    if payload is None:
        return Budget()
    if not isinstance(payload, dict):
        raise PolicyViolation('budget must be an object')
    values = {}
    for name, (default, hard_max) in BUDGET_LIMITS.items():
        if name not in payload:
            values[name] = default
            continue
        raw = payload[name]
        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise PolicyViolation('budget.%s must be an integer' % name) from None
        if value < 1 or value > hard_max:
            raise PolicyViolation(
                'budget.%s must be within 1..%d' % (name, hard_max)
            )
        values[name] = value
    unknown = set(payload) - set(BUDGET_LIMITS)
    if unknown:
        raise PolicyViolation(
            'unknown budget fields: %s' % ', '.join(sorted(unknown))
        )
    return Budget(**values)


# ---------------------------------------------------------------------------
# 敏感路径：服务端策略拒绝，提示词不是安全控制
# ---------------------------------------------------------------------------

_SENSITIVE_PATH_PATTERNS = (
    re.compile(r'^/etc/(shadow|gshadow|sudoers|sudoers\.d(/.*)?)$'),
    re.compile(r'^/etc/(ssl|pki|ca-certificates)/.*\.key$'),
    re.compile(r'^/root/\.ssh(/.*)?$'),
    re.compile(r'^/home/[^/]+/\.ssh(/.*)?$'),
    re.compile(r'.*\.pem$'),
    re.compile(r'.*id_(rsa|dsa|ecdsa|ed25519)(\.pub)?$'),
    re.compile(r'.*(^|/)\.env(\..+)?$'),
    re.compile(r'^/proc/[^/]+/(mem|environ)$'),
    re.compile(r'.*(secret|credential|password|token).*\.(key|pem|json|ya?ml|ini|conf)$'),
)


def is_sensitive_path(path: str) -> bool:
    """通用文件读取的敏感路径判定（命中即永久拒绝）。"""
    normalized = str(path or '').strip()
    if not normalized:
        return True
    return any(p.match(normalized) for p in _SENSITIVE_PATH_PATTERNS)


# ---------------------------------------------------------------------------
# Shell 命令风险特征：黑名单只提供风险信号，命中即不可自动
# ---------------------------------------------------------------------------

_SHELL_RISK_PATTERNS = (
    (re.compile(r'[|;`]'), 'pipeline or command chaining'),
    (re.compile(r'&&|\|\|'), 'command chaining'),
    (re.compile(r'[<>]'), 'redirection'),
    (re.compile(r'\$\('), 'command substitution'),
    (re.compile(r'(^|\s)(bash|sh|zsh|python[23]?|perl|ruby|node)\s+-c\b'), 'inline interpreter'),
    (re.compile(r'(^|\s)(wget|curl)\b.*\|\s*(bash|sh)\b'), 'download and execute'),
    (re.compile(r'(^|\s)(wget|curl)\b'), 'download command'),
    (re.compile(r'\n|\r'), 'embedded newline'),
)


def classify_shell_command(command: str) -> Tuple[ApprovalDecision, str]:
    """对任意 Shell 文本做风险分级。

    shell 动作永远不可能自动执行；这里进一步把伪装写入、管道、
    重定向、解释器和下载命令标记为永久拒绝，其余要求精确审批。
    """
    text = str(command or '')
    if not text.strip():
        return ApprovalDecision.DENIED, 'empty command'
    for pattern, reason in _SHELL_RISK_PATTERNS:
        if pattern.search(text):
            return ApprovalDecision.DENIED, reason
    return ApprovalDecision.APPROVAL_REQUIRED, 'arbitrary shell requires exact approval'


# ---------------------------------------------------------------------------
# 动作分类：模式 × kind × 环境 → 决策
# ---------------------------------------------------------------------------

def validate_mode_for_environment(mode: str, environment: str) -> None:
    """lab_autonomous 只授予管理员标记为 lab 的资产。"""
    RunMode(mode)
    AiEnvironment(environment)
    if mode == RunMode.LAB_AUTONOMOUS.value and environment != AiEnvironment.LAB.value:
        raise PolicyViolation(
            'lab_autonomous mode requires ai_environment=lab on the target host'
        )


def classify_action(
    mode: str,
    action: StructuredAction,
    environment: str,
) -> Tuple[ApprovalDecision, str]:
    """服务端策略：返回 (决策, 原因)。

    - probe 是服务端自有只读探针，任何模式下都可自动（参数在
      actions.validate_probe 已白名单校验）；
    - file_read 敏感路径拒绝，其余任何模式都要求审批；
    - shell 在 read_only 拒绝，其余要求审批，永不自动。
    """
    RunMode(mode)
    AiEnvironment(environment)
    kind = str(action.kind)
    if kind == 'probe':
        return ApprovalDecision.AUTO, 'server-owned read-only probe'
    if kind == 'file_read':
        path = str(action.parameters.get('path') or '')
        if is_sensitive_path(path):
            return ApprovalDecision.DENIED, 'sensitive path is denied by server policy'
        return ApprovalDecision.APPROVAL_REQUIRED, 'general file reads are never automatic'
    if kind == 'shell':
        if mode == RunMode.READ_ONLY.value:
            return ApprovalDecision.DENIED, 'shell actions are denied in read_only mode'
        return ApprovalDecision.APPROVAL_REQUIRED, 'arbitrary shell requires exact approval'
    return ApprovalDecision.DENIED, 'unknown action kind'
