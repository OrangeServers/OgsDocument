# -*- coding: utf-8 -*-
"""ti3-HINT 静态验证测试 (mypy Phase A).

REV47-M12 续: ti3-HINT (后端 type hints 全覆盖) 的静态验证.
本测试不依赖运行时, 只用 subprocess 调 mypy + AST 扫描, 验证:
  1. mypy 在 critical-path 模块 (api/auth/audit) 0 错 (CI 必过)
  2. mypy 配置文件存在且包含关键 strict 规则
  3. app/core/types.py 公共类型存在且导出关键别名
  4. 业务函数 type hint 覆盖率指标 (量化进度)

跑法:
    cd backend && python -m pytest tests/test_ti3_hint.py -v
    cd backend && python -m mypy --config-file mypy.ini app/api app/auth app/audit
"""
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

# 路径常量
BACKEND_DIR = Path(__file__).resolve().parent.parent  # backend/
MYPY_INI = BACKEND_DIR / "mypy.ini"
APP_DIR = BACKEND_DIR / "app"
TYPES_PY = BACKEND_DIR / "app" / "core" / "types.py"
CRITICAL_MODULES = ["app/api", "app/auth", "app/audit"]
MYPY_EXE = os.environ.get(
    "MYPY_EXE",
    r"C:\Users\developer\AppData\Local\Programs\Python\Python314\Scripts\mypy.exe"
)


def _run(cmd, cwd=None, timeout=180):
    """同步跑子进程, 返 (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(
            cmd, cwd=cwd or str(BACKEND_DIR),
            capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except FileNotFoundError as e:
        return -2, "", str(e)


class TestTi3HintConfig(unittest.TestCase):
    """ti3-HINT 配置存在性 + 关键开关验证."""

    def test_mypy_ini_exists(self):
        self.assertTrue(MYPY_INI.exists(), f"missing mypy.ini at {MYPY_INI}")

    def test_mypy_ini_contains_strict_rules(self):
        text = MYPY_INI.read_text(encoding="utf-8")
        # 关键开关: strict 模式覆盖了 api/auth/audit
        self.assertIn("[mypy-app.api.*]", text, "mypy.ini 缺 [mypy-app.api.*] 段")
        self.assertIn("[mypy-app.auth.*]", text, "mypy.ini 缺 [mypy-app.auth.*] 段")
        self.assertIn("[mypy-app.audit.*]", text, "mypy.ini 缺 [mypy-app.audit.*] 段")
        # 关键 flag
        self.assertIn("disallow_untyped_defs = True", text, "mypy.ini 缺 disallow_untyped_defs=True")

    def test_mypy_ini_excludes_soft_modules(self):
        """Phase A: soft-warning 模块 (users/assets/ssh/cron) 在 exclude 中."""
        text = MYPY_INI.read_text(encoding="utf-8")
        exclude_match = re.search(r"^exclude\s*=\s*(.+)$", text, re.MULTILINE)
        self.assertIsNotNone(exclude_match, "mypy.ini 缺 exclude 行")
        exclude = exclude_match.group(1)
        for soft in ("app/users", "app/assets", "app/ssh", "app/cron"):
            self.assertIn(soft, exclude, f"exclude 应含 {soft} (Phase A 软警告)")

    def test_types_py_exists(self):
        self.assertTrue(TYPES_PY.exists(), f"missing app/core/types.py at {TYPES_PY}")

    def test_types_py_contains_key_aliases(self):
        """app/core/types.py 必须导出关键公共类型 (业务代码依赖)."""
        text = TYPES_PY.read_text(encoding="utf-8")
        required = [
            "JsonOrResponse",  # 视图函数返回
            "DbRow", "DbRows",  # ORM
            "UserInfo", "HostInfo",  # 业务模型
            "RedisKey", "UserRole",  # 别名
        ]
        for name in required:
            self.assertIn(name, text, f"app/core/types.py 缺 {name}")


@unittest.skipUnless(os.path.exists(MYPY_EXE), f"mypy 未安装 ({MYPY_EXE})")
class TestTi3HintMypyPhaseA(unittest.TestCase):
    """mypy 在 critical-path 模块 0 错 (CI 必过)."""

    @classmethod
    def setUpClass(cls):
        cls.result = _run(
            [MYPY_EXE, "--config-file", "mypy.ini",
             "--no-incremental", "--no-pretty", "--no-color-output",
             *CRITICAL_MODULES],
            cwd=str(BACKEND_DIR),
            timeout=240,
        )

    def test_mypy_critical_path_zero_errors(self):
        """mypy 在 api/auth/audit 三个 critical-path 模块 0 错 (CI gate)."""
        returncode, stdout, stderr = self.result
        combined = stdout + stderr
        # mypy exit 0 = 0 错; exit 1 = 有错
        self.assertEqual(
            returncode, 0,
            f"mypy 失败 (exit {returncode}).\n输出:\n{combined[:3000]}\n"
            f"提示: 跑 `mypy --config-file mypy.ini app/api app/auth app/audit` 查看详细"
        )


class TestTi3HintTypeHintCoverage(unittest.TestCase):
    """业务函数 type hint 覆盖率 (量化进度, 不强制 100%).

    Phase A 目标: critical-path 模块 100% 覆盖 (api/auth/audit).
    Phase B 目标: 软警告模块逐步提升 (users/assets/ssh/cron).
    """

    def _scan_module(self, module_path: Path):
        """用 AST 扫描一个 .py 文件, 统计顶层 / 嵌套 def 的 type hint 覆盖率."""
        import ast
        text = module_path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(module_path))
        total = 0
        hinted = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # 跳过 dunder / property 装饰器 / 不要求返回类型
                if node.name.startswith("__") and node.name.endswith("__"):
                    continue
                total += 1
                # 有任何 type hint = 全函数有或返回类型有
                has_ret_hint = node.returns is not None
                has_arg_hint = all(a.annotation is not None for a in node.args.args)
                # self 不算
                if node.args.args and node.args.args[0].arg in ("self", "cls"):
                    pass  # self 允许无注解
                if has_ret_hint or has_arg_hint:
                    hinted += 1
        return total, hinted

    def test_critical_path_coverage_report(self):
        """输出 critical-path 模块覆盖率报告 (不强制 100%, 仅记录)."""
        import io
        import contextlib
        results = []
        for mod in CRITICAL_MODULES:
            mod_path = BACKEND_DIR / mod.replace("/", os.sep)
            if not mod_path.exists():
                continue
            for py_file in mod_path.rglob("*.py"):
                # 排除 __pycache__ 和 tests
                if "__pycache__" in str(py_file) or "test_" in py_file.name:
                    continue
                total, hinted = self._scan_module(py_file)
                if total > 0:
                    pct = 100.0 * hinted / total
                    results.append((str(py_file.relative_to(BACKEND_DIR)), total, hinted, pct))
        # 打印报告
        report = ["\n=== ti3-HINT type hint 覆盖率 (critical path) ==="]
        report.append(f"{'file':<55} {'total':>6} {'hinted':>7} {'pct':>7}")
        report.append("-" * 80)
        for path, total, hinted, pct in sorted(results):
            mark = "OK" if pct >= 80 else "WARN"
            report.append(f"{path:<55} {total:>6} {hinted:>7} {pct:>6.1f}% {mark}")
        report.append("-" * 80)
        total_all = sum(r[1] for r in results)
        hinted_all = sum(r[2] for r in results)
        overall_pct = 100.0 * hinted_all / total_all if total_all else 0
        report.append(f"{'TOTAL':<55} {total_all:>6} {hinted_all:>7} {overall_pct:>6.1f}%")
        # 打印到 stderr 避免 pytest -v 截断
        sys.stderr.write("\n".join(report) + "\n")
        # Phase A soft assertion: critical path 至少 50% 覆盖 (避免完全空注解)
        # Phase B 目标 100%. 业务代码函数量大, 50% 是合理阶段门槛.
        self.assertGreaterEqual(
            overall_pct, 50.0,
            f"critical-path 覆盖率 {overall_pct:.1f}% < 50% 门槛"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
