"""Deterministic analyzers and built-in diagnostic runbooks."""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Mapping
from uuid import uuid4


_SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}
_PERCENT = re.compile(r"(?<!\d)(\d{1,3})%")
_LOAD = re.compile(
    r"load average[s]?:\s*([0-9.]+)[,\s]+([0-9.]+)[,\s]+([0-9.]+)",
    re.IGNORECASE,
)


RUNBOOKS: Dict[str, Dict[str, Any]] = {
    "disk": {
        "id": "disk_pressure",
        "name": "磁盘水位处置",
        "steps": [
            "确认高水位文件系统及业务影响",
            "定位大目录、大文件和已删除但仍占用的文件",
            "生成清理或扩容审批计划",
            "执行后重新检查容量和 inode",
        ],
        "verification_profile_id": "disk_usage",
    },
    "inode": {
        "id": "inode_pressure",
        "name": "inode 水位处置",
        "steps": [
            "确认高水位文件系统",
            "定位小文件密集目录",
            "生成归档或清理审批计划",
            "执行后重新检查 inode",
        ],
        "verification_profile_id": "disk_usage",
    },
    "memory": {
        "id": "memory_pressure",
        "name": "内存压力处置",
        "steps": [
            "确认 available 内存与 Swap 活动",
            "定位高内存进程",
            "评估扩容、限额或服务重启方案",
            "执行后重新检查内存压力",
        ],
        "verification_profile_id": "memory_pressure",
    },
    "load": {
        "id": "high_load",
        "name": "高负载处置",
        "steps": [
            "比较负载与 CPU 数量",
            "定位高 CPU 或不可中断进程",
            "评估限流、扩容或服务处理方案",
            "执行后重新检查负载",
        ],
        "verification_profile_id": "cpu_load",
    },
    "service": {
        "id": "service_unavailable",
        "name": "服务不可用处置",
        "steps": [
            "确认失败服务及依赖",
            "读取服务状态和相关日志",
            "生成修复或重启审批计划",
            "执行后验证服务和监听端口",
        ],
        "verification_profile_id": "service_status",
    },
    "port": {
        "id": "port_anomaly",
        "name": "端口异常处置",
        "steps": [
            "确认预期监听地址和端口",
            "关联进程与服务状态",
            "生成服务或配置修复审批计划",
            "执行后验证监听状态",
        ],
        "verification_profile_id": "port_status",
    },
    "docker": {
        "id": "docker_container_anomaly",
        "name": "Docker 容器异常处置",
        "steps": [
            "确认异常容器、健康状态和重启次数",
            "检查资源水位与最近错误日志",
            "生成容器修复审批计划",
            "执行后验证容器健康和重启计数",
        ],
        "verification_profile_id": "docker_health",
    },
    "logs": {
        "id": "log_error_spike",
        "name": "日志错误突增处置",
        "steps": [
            "确认错误关键词和时间范围",
            "关联服务、资源与最近变更",
            "形成修复建议",
            "执行后复查同一时间窗口",
        ],
        "verification_profile_id": "system_logs",
    },
}


def _finding(
    evidence: Mapping[str, Any],
    *,
    title: str,
    severity: str,
    summary: str,
    recommendation: str,
) -> Dict[str, Any]:
    kind = str(evidence.get("kind") or "system")
    return {
        "id": uuid4().hex,
        "title": title,
        "severity": severity,
        "asset_alias": evidence.get("asset_alias"),
        "kind": kind,
        "summary": summary,
        "evidence_ids": [str(evidence["id"])],
        "recommendation": recommendation,
        "runbook": RUNBOOKS.get(kind),
    }


def _usage_finding(evidence: Mapping[str, Any]) -> Dict[str, Any] | None:
    values = [int(value) for value in _PERCENT.findall(
        str(evidence.get("content") or "")
    )]
    if not values:
        return None
    highest = max(values)
    if highest < 85:
        return None
    severity = "critical" if highest >= 95 else "warning"
    label = "inode" if evidence.get("kind") == "inode" else "磁盘"
    return _finding(
        evidence,
        title=f"{label}使用率过高",
        severity=severity,
        summary=f"检测到最高使用率 {highest}%",
        recommendation=f"按{label}水位 Runbook 定位占用并在审批后处置。",
    )


def _memory_finding(evidence: Mapping[str, Any]) -> Dict[str, Any] | None:
    for line in str(evidence.get("content") or "").splitlines():
        fields = line.split()
        if fields and fields[0].rstrip(":") == "Mem" and len(fields) >= 7:
            try:
                total, available = int(fields[1]), int(fields[6])
            except ValueError:
                return None
            if total <= 0:
                return None
            available_pct = round(available * 100 / total)
            if available_pct >= 20:
                return None
            return _finding(
                evidence,
                title="可用内存偏低",
                severity="critical" if available_pct < 10 else "warning",
                summary=f"available 内存约为总内存的 {available_pct}%",
                recommendation="关联高内存进程后评估限额、扩容或审批重启。",
            )
    return None


def _cpu_count(evidence: Mapping[str, Any]) -> int | None:
    try:
        count = int(str(evidence.get("content") or "").strip())
    except ValueError:
        return None
    return count if count > 0 else None


def _load_finding(
    evidence: Mapping[str, Any],
    cpu_evidence: Mapping[str, Any],
) -> Dict[str, Any] | None:
    cpu_count = _cpu_count(cpu_evidence)
    if cpu_count is None:
        return None
    match = _LOAD.search(str(evidence.get("content") or ""))
    if not match:
        return None
    one_minute = float(match.group(1))
    threshold = cpu_count
    if one_minute <= threshold:
        return None
    finding = _finding(
        evidence,
        title="系统负载超过 CPU 容量",
        severity="critical" if one_minute >= threshold * 2 else "warning",
        summary=f"1 分钟负载 {one_minute:g}，在线 CPU {threshold}",
        recommendation="关联 CPU 高占用和不可中断进程后再制定处置方案。",
    )
    finding["evidence_ids"].append(str(cpu_evidence["id"]))
    return finding


def _service_finding(evidence: Mapping[str, Any]) -> Dict[str, Any] | None:
    content = str(evidence.get("content") or "")
    failed = [
        line.strip()
        for line in content.splitlines()
        if ".service" in line and "loaded units listed" not in line.lower()
    ]
    if not failed:
        return None
    return _finding(
        evidence,
        title="发现失败的 systemd 服务",
        severity="critical",
        summary=f"发现 {len(failed)} 条失败服务记录",
        recommendation="读取对应服务状态和日志，修复动作必须进入审批。",
    )


def _port_finding(evidence: Mapping[str, Any]) -> Dict[str, Any] | None:
    content = str(evidence.get("content") or "")
    expected = re.search(r"^EXPECTED_PORT=(\d{1,5})$", content, re.MULTILINE)
    if not expected:
        return None
    port = int(expected.group(1))
    listening = any(
        re.search(rf":{port}\b", line)
        for line in content.splitlines()
        if not line.startswith("EXPECTED_PORT=")
    )
    if listening:
        return None
    return _finding(
        evidence,
        title=f"端口 {port} 未监听",
        severity="critical",
        summary=f"未在 ss 监听快照中发现端口 {port}",
        recommendation="关联服务状态和配置；任何修复或重启必须进入审批。",
    )


def _docker_finding(evidence: Mapping[str, Any]) -> Dict[str, Any] | None:
    content = str(evidence.get("content") or "")
    unhealthy = len(re.findall(r"\bunhealthy\b", content, re.IGNORECASE))
    exited = len(re.findall(r"\bexited\b", content, re.IGNORECASE))
    restart_counts = []
    if evidence.get("probe_id") == "docker_restarts":
        for line in content.splitlines():
            fields = line.split("\t")
            if len(fields) > 1:
                try:
                    restart_counts.append(int(fields[1]))
                except ValueError:
                    pass
    highest_restart = max(restart_counts or [0])
    if not (unhealthy or exited or highest_restart):
        return None
    severity = (
        "critical" if unhealthy or highest_restart >= 3 else "warning"
    )
    return _finding(
        evidence,
        title="Docker 容器状态异常",
        severity=severity,
        summary=(
            f"unhealthy={unhealthy}, exited={exited}, "
            f"最高重启次数={highest_restart}"
        ),
        recommendation="关联容器资源和日志，修复或重启必须进入审批。",
    )


def _log_error_count(evidence: Mapping[str, Any]) -> int:
    return len(re.findall(
        r"\b(error|failed|failure|panic|oom|out of memory)\b",
        str(evidence.get("content") or ""),
        re.IGNORECASE,
    ))


def _log_finding(
    evidence: Mapping[str, Any],
    *,
    baseline_evidence: Mapping[str, Any] | None = None,
) -> Dict[str, Any] | None:
    count = _log_error_count(evidence)
    if baseline_evidence is not None:
        baseline_count = _log_error_count(baseline_evidence)
        if count < 3 or count < max(3, baseline_count * 2):
            return None
        finding = _finding(
            evidence,
            title="日志错误信号突增",
            severity="critical" if count >= 10 else "warning",
            summary=(
                f"最近 5 分钟命中 {count} 个错误关键词，"
                f"此前 5 分钟为 {baseline_count} 个"
            ),
            recommendation="结合服务、资源水位和最近变更进一步缩小范围。",
        )
        if baseline_evidence is not None:
            finding["evidence_ids"].append(str(baseline_evidence["id"]))
        return finding
    if count < 3:
        return None
    return _finding(
        evidence,
        title="日志错误信号集中出现",
        severity="critical" if count >= 10 else "warning",
        summary=f"当前证据片段命中 {count} 个错误关键词",
        recommendation="结合服务、资源水位和最近变更进一步缩小范围。",
    )


class DeterministicAnalyzer:
    """Convert bounded evidence into reproducible, cited findings."""

    def analyze(self, evidence_items: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
        items = [dict(item) for item in evidence_items]
        cpu_count_by_asset: Dict[str, Dict[str, Any]] = {}
        log_baseline_by_asset: Dict[str, Dict[str, Any]] = {}
        for item in items:
            if (
                item.get("probe_id") == "cpu_count"
                and item.get("status") == "success"
                and _cpu_count(item) is not None
            ):
                cpu_count_by_asset[str(item.get("asset_alias"))] = item
            if (
                item.get("probe_id") == "warning_logs_baseline"
                and item.get("status") == "success"
                and str(item.get("content") or "").strip()
            ):
                log_baseline_by_asset[str(item.get("asset_alias"))] = item

        findings = []
        for item in items:
            if item.get("status") != "success":
                findings.append(_finding(
                    item,
                    title="诊断证据采集失败",
                    severity="warning",
                    summary=str(item.get("error") or "远程采集失败")[:240],
                    recommendation="检查资产连通性、凭据授权和探针依赖后重试。",
                ))
                continue
            kind = item.get("kind")
            finding = None
            if kind in ("disk", "inode"):
                finding = _usage_finding(item)
            elif kind == "memory" and item.get("probe_id") == "memory":
                finding = _memory_finding(item)
            elif kind == "load":
                cpu_evidence = cpu_count_by_asset.get(
                    str(item.get("asset_alias"))
                )
                if cpu_evidence is not None:
                    finding = _load_finding(item, cpu_evidence)
            elif kind == "service":
                finding = _service_finding(item)
            elif kind == "port":
                finding = _port_finding(item)
            elif kind == "docker":
                finding = _docker_finding(item)
            elif kind == "logs":
                if item.get("probe_id") == "warning_logs_current":
                    baseline = log_baseline_by_asset.get(
                        str(item.get("asset_alias"))
                    )
                    if baseline is not None:
                        finding = _log_finding(
                            item,
                            baseline_evidence=baseline,
                        )
                elif item.get("probe_id") != "warning_logs_baseline":
                    finding = _log_finding(item)
            if finding:
                findings.append(finding)

        severity = max(
            (item["severity"] for item in findings),
            key=lambda value: _SEVERITY_RANK.get(value, 0),
            default="info",
        )
        successful = sum(item.get("status") == "success" for item in items)
        insufficient = not items or successful == 0
        summary = (
            "证据不足，无法形成可靠结论"
            if insufficient
            else (
                f"发现 {len(findings)} 个需关注项"
                if findings else "未发现达到规则阈值的异常"
            )
        )
        return {
            "status": "completed",
            "summary": summary,
            "severity": severity,
            "findings": findings,
            "evidence_insufficient": insufficient,
        }
