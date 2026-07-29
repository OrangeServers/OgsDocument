"""Server-owned, read-only diagnostic profiles.

The model and browser choose a profile and structured parameters.  They never
provide shell text: every command below is shipped by OrangeServer and every
parameter is validated before interpolation.
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple


class DiagnosticProfileError(ValueError):
    pass


_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}$")
_LOG_LINES = (50, 100, 200)


@dataclass(frozen=True)
class Probe:
    id: str
    title: str
    kind: str
    command_template: str
    timeout_seconds: int = 15
    max_output_chars: int = 32_768

    def command(self, parameters: Mapping[str, Any]) -> str:
        values = {
            key: shlex.quote(str(value))
            for key, value in parameters.items()
        }
        return self.command_template.format(**values)


@dataclass(frozen=True)
class DiagnosticProfile:
    id: str
    name: str
    description: str
    category: str
    target_type: str
    probes: Tuple[Probe, ...]
    parameters: Tuple[Dict[str, Any], ...] = ()

    def public_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "target_type": self.target_type,
            "parameters": [dict(item) for item in self.parameters],
            "probe_count": len(self.probes),
        }

    def validate_parameters(
        self, raw: Mapping[str, Any] | None
    ) -> Dict[str, Any]:
        raw = dict(raw or {})
        allowed = {item["name"] for item in self.parameters}
        unknown = set(raw) - allowed
        if unknown:
            raise DiagnosticProfileError(
                "unknown diagnostic parameters: " + ", ".join(sorted(unknown))
            )
        result: Dict[str, Any] = {}
        for spec in self.parameters:
            name = spec["name"]
            value = raw.get(name, spec.get("default"))
            if value in (None, ""):
                if spec.get("required"):
                    raise DiagnosticProfileError(f"{name} is required")
                continue
            if spec["type"] == "integer":
                if isinstance(value, bool):
                    raise DiagnosticProfileError(f"{name} must be an integer")
                try:
                    value = int(value)
                except (TypeError, ValueError) as exc:
                    raise DiagnosticProfileError(
                        f"{name} must be an integer"
                    ) from exc
                if "enum" in spec and value not in spec["enum"]:
                    raise DiagnosticProfileError(f"{name} is not allowed")
                if value < spec.get("minimum", value):
                    raise DiagnosticProfileError(f"{name} is too small")
                if value > spec.get("maximum", value):
                    raise DiagnosticProfileError(f"{name} is too large")
            elif spec["type"] == "string":
                value = str(value)
                if not _SAFE_NAME.fullmatch(value):
                    raise DiagnosticProfileError(
                        f"{name} contains unsafe characters"
                    )
            result[name] = value
        return result


def _probe(
    probe_id: str,
    title: str,
    kind: str,
    command: str,
    *,
    timeout: int = 15,
    output: int = 32_768,
) -> Probe:
    return Probe(probe_id, title, kind, command, timeout, output)


PROFILES: Dict[str, DiagnosticProfile] = {
    "system_baseline": DiagnosticProfile(
        "system_baseline", "系统基线", "内核、时间、启动时长与主机身份",
        "system", "linux",
        (
            _probe("uname", "内核信息", "system", "uname -a"),
            _probe("uptime", "负载与启动时长", "load", "uptime"),
            _probe(
                "identity", "主机身份", "system",
                "hostname; date -u '+%Y-%m-%dT%H:%M:%SZ'",
            ),
        ),
    ),
    "cpu_load": DiagnosticProfile(
        "cpu_load", "CPU 与负载", "负载、CPU 数和高占用进程",
        "performance", "linux",
        (
            _probe("uptime", "系统负载", "load", "uptime"),
            _probe(
                "cpu_count", "CPU 数量", "cpu",
                "getconf _NPROCESSORS_ONLN",
            ),
            _probe(
                "top_cpu", "CPU 高占用进程", "process",
                "ps -eo pid,ppid,user,stat,pcpu,pmem,comm "
                "--sort=-pcpu | head -n 21",
            ),
        ),
    ),
    "memory_pressure": DiagnosticProfile(
        "memory_pressure", "内存压力", "内存、Swap 与虚拟内存活动",
        "performance", "linux",
        (
            _probe("memory", "内存使用", "memory", "free -m"),
            _probe("vmstat", "内存压力", "memory", "vmstat 1 2"),
        ),
    ),
    "disk_usage": DiagnosticProfile(
        "disk_usage", "磁盘与 inode", "文件系统容量和 inode 水位",
        "storage", "linux",
        (
            _probe("disk", "磁盘使用", "disk", "df -PT"),
            _probe("inode", "inode 使用", "inode", "df -Pi"),
        ),
    ),
    "process_snapshot": DiagnosticProfile(
        "process_snapshot", "进程快照", "CPU/内存高占用进程",
        "process", "linux",
        (
            _probe(
                "top_processes", "高占用进程", "process",
                "ps -eo pid,ppid,user,stat,pcpu,pmem,etime,comm "
                "--sort=-pcpu | head -n 31",
            ),
        ),
    ),
    "port_status": DiagnosticProfile(
        "port_status", "监听端口", "验证指定 TCP/UDP 端口是否处于监听状态",
        "network", "linux",
        (
            _probe(
                "listening_ports", "监听端口", "port",
                "ss -lntup && printf '\\nEXPECTED_PORT={port}\\n'",
            ),
        ),
        parameters=({
            "name": "port",
            "type": "integer",
            "minimum": 1,
            "maximum": 65535,
            "required": True,
        },),
    ),
    "service_status": DiagnosticProfile(
        "service_status", "服务状态", "失败服务或指定 systemd 服务",
        "service", "linux",
        (
            _probe(
                "failed_services", "失败服务", "service",
                "systemctl --failed --no-pager --plain",
            ),
        ),
    ),
    "system_logs": DiagnosticProfile(
        "system_logs", "系统日志", "最近 warning 及以上级别日志",
        "logs", "linux",
        (
            _probe(
                "warning_logs_current", "最近 5 分钟系统告警", "logs",
                "journalctl -p warning --since '-5 minutes' "
                "-n {log_lines} --no-pager",
                output=65_536,
            ),
            _probe(
                "warning_logs_baseline", "此前 5 分钟系统告警", "logs",
                "journalctl -p warning --since '-10 minutes' "
                "--until '-5 minutes' -n {log_lines} --no-pager",
                output=65_536,
            ),
        ),
        parameters=({
            "name": "log_lines",
            "type": "integer",
            "enum": list(_LOG_LINES),
            "default": 100,
            "required": False,
        },),
    ),
    "docker_health": DiagnosticProfile(
        "docker_health", "Docker 健康状态",
        "容器状态、资源、重启次数和最近日志摘要",
        "container", "docker",
        (
            _probe(
                "docker_ps", "容器状态", "docker",
                "docker ps -a --no-trunc --format "
                "'{{{{.ID}}}}\\t{{{{.Names}}}}\\t{{{{.Status}}}}\\t{{{{.Image}}}}'",
            ),
            _probe(
                "docker_stats", "容器资源", "docker",
                "docker stats --no-stream --format "
                "'{{{{.Name}}}}\\t{{{{.CPUPerc}}}}\\t{{{{.MemPerc}}}}\\t"
                "{{{{.MemUsage}}}}'",
            ),
            _probe(
                "docker_restarts", "容器健康与重启", "docker",
                "ids=$(docker ps -aq); "
                "if [ -z \"$ids\" ]; then printf 'NO_CONTAINERS\\n'; "
                "else docker inspect --format "
                "'{{{{.Name}}}}\\t{{{{.RestartCount}}}}\\t"
                "{{{{if .State.Health}}}}{{{{.State.Health.Status}}}}"
                "{{{{else}}}}none{{{{end}}}}\\t{{{{.State.Status}}}}' "
                "$ids; fi",
            ),
            _probe(
                "docker_logs", "容器最近日志", "logs",
                "ids=$(docker ps -q); "
                "if [ -z \"$ids\" ]; then printf 'NO_RUNNING_CONTAINERS\\n'; "
                "else for id in $ids; do "
                "name=$(docker inspect --format '{{{{.Name}}}}' \"$id\"); "
                "printf '\\n=== %s ===\\n' \"$name\"; "
                "docker logs --tail 50 \"$id\" 2>&1; done; fi",
                output=65_536,
            ),
        ),
    ),
    "docker_logs": DiagnosticProfile(
        "docker_logs", "Docker 容器日志",
        "指定容器的最近日志片段；容器名经过严格校验",
        "logs", "docker",
        (
            _probe(
                "docker_logs", "容器最近日志", "logs",
                "docker logs --tail {log_lines} -- {container_name}",
                output=65_536,
            ),
        ),
        parameters=(
            {
                "name": "container_name",
                "type": "string",
                "required": True,
            },
            {
                "name": "log_lines",
                "type": "integer",
                "enum": list(_LOG_LINES),
                "default": 100,
                "required": False,
            },
        ),
    ),
}


def list_profiles() -> list[Dict[str, Any]]:
    return [profile.public_dict() for profile in PROFILES.values()]


def get_profile(profile_id: str) -> DiagnosticProfile:
    try:
        return PROFILES[str(profile_id)]
    except KeyError as exc:
        raise DiagnosticProfileError("unknown diagnostic profile") from exc
