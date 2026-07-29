# -*- coding: utf-8 -*-
"""ti3-TS 前端 TypeScript 迁移静态验证测试.

ti3-TS (前端 TS 全量迁移) 完工验收的静态校验.
本测试不依赖运行时, 只用:
  - 文件存在性 + JSON 解析
  - 正则扫描 .vue 文件 <script setup lang="ts">
  - subprocess 调 vue-tsc + vite build

覆盖:
  1. tsconfig.json 存在 + strict 模式关键开关
  2. vite.config.ts 是主入口 (vite.config.js 不应被实际引用)
  3. 公共类型 src/types/ 存在 + 9 个 module + 统一 index.ts 导出
  4. 入口文件 main.ts + router/index.ts + store/index.ts + api/index.ts 都已 .ts 化
  5. 21 个 views 全部使用 <script setup lang="ts">
  6. utils/ (7) + composables/ (6) 全部 .ts
  7. vue-tsc --noEmit 0 错 (CI 必过)

跑法:
    cd backend && python -m pytest tests/test_ti3_ts.py -v
"""
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

# 路径常量
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # OrangeServer/
FRONTEND_DIR = PROJECT_ROOT / "frontend"
SRC_DIR = FRONTEND_DIR / "src"
TSCONFIG = FRONTEND_DIR / "tsconfig.json"
TYPES_DIR = SRC_DIR / "types"

# 关键 .vue/.ts 入口文件
EXPECTED_TYPES_MODULES = [
    "common.ts", "api.ts", "auth.ts", "host.ts",
    "cron.ts", "audit.ts", "terminal.ts", "setting.ts", "index.ts",
]

EXPECTED_ENTRY_FILES = [
    SRC_DIR / "main.ts",
    SRC_DIR / "App.vue",
    SRC_DIR / "api" / "index.ts",
    SRC_DIR / "router" / "index.ts",
    SRC_DIR / "store" / "index.ts",
]

# 所有页面组件都要求 script setup lang=ts
EXPECTED_VIEWS = [
    "Layout.vue", "Login.vue", "Register.vue",
    "Dashboard.vue", "HostList.vue", "UserList.vue", "UserInfo.vue",
    "GroupList.vue", "UserGroupList.vue", "SysUserList.vue",
    "Authority.vue", "Settings.vue", "Cron.vue",
    "BatchCommand.vue", "BatchScript.vue", "AIAgent.vue",
    "FileTransfer.vue", "RemoteSession.vue",
    "AuditUserLog.vue", "AuditComLog.vue", "AuditCzLog.vue",
]

EXPECTED_COMPONENTS = [
    "AssetTreePanel.vue", "AuthShell.vue", "DataTablePanel.vue",
    "HostDetailDialog.vue", "OpsLayout.vue", "ResultPanel.vue",
    "WebSSHCore.vue",
]

EXPECTED_UTILS = [
    "danger.ts", "datetime.ts", "groupClassifier.ts",
    "host.ts", "logStatus.ts", "ws.ts", "dev-auth-mock.ts",
]

EXPECTED_COMPOSABLES = [
    "useClipboard.ts", "useCronNext.ts", "useListCrud.ts",
    "useLogTable.ts", "usePasswordStrength.ts", "useWebSSH.ts",
]


def _run(cmd, cwd=None, timeout=240):
    """同步跑子进程, 返 (returncode, stdout, stderr).

    Windows 上 npm/npx 是 .cmd, 直接 subprocess 找不到; 用 shell=True 跨平台.
    """
    try:
        proc = subprocess.run(
            cmd, cwd=cwd or str(FRONTEND_DIR),
            capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
            shell=True,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except FileNotFoundError as e:
        return -2, "", str(e)


def _has_script_setup_ts(vue_path: Path) -> bool:
    """检查 .vue 文件是否含 <script setup lang=\"ts\"> 块.

    支持多行匹配, 同时允许属性间多空格.
    """
    if not vue_path.exists():
        return False
    text = vue_path.read_text(encoding="utf-8", errors="replace")
    # 模式: <script 任意属性 setup lang="ts" 任意属性 > 或变体
    # 最简形式: <script setup lang="ts">
    pattern = re.compile(
        r"<script\b[^>]*?\bsetup\b[^>]*?\blang\s*=\s*[\"']ts[\"'][^>]*?>",
        re.DOTALL,
    )
    return bool(pattern.search(text))


class TestTi3TsConfig(unittest.TestCase):
    """ti3-TS 工程配置验证."""

    def test_tsconfig_exists_and_strict(self):
        """tsconfig.json 存在 + 关键 strict 开关."""
        self.assertTrue(TSCONFIG.exists(), f"missing {TSCONFIG}")
        data = json.loads(TSCONFIG.read_text(encoding="utf-8"))
        co = data.get("compilerOptions", {})
        # strict mode 关键开关
        self.assertTrue(co.get("strict"), "tsconfig.json strict 应为 true")
        self.assertTrue(co.get("noImplicitAny"), "缺 noImplicitAny=true")
        self.assertTrue(co.get("strictNullChecks"), "缺 strictNullChecks=true")
        # 路径 alias
        paths = co.get("paths", {})
        self.assertIn("@/*", paths, "tsconfig.json 缺 @/* 路径 alias")
        # include 覆盖 src/**/*.ts + src/**/*.vue
        inc = data.get("include", [])
        self.assertIn("src/**/*.ts", inc, "tsconfig.json include 缺 src/**/*.ts")
        self.assertIn("src/**/*.vue", inc, "tsconfig.json include 缺 src/**/*.vue")

    def test_vite_config_uses_ts(self):
        """vite.config.ts 是主入口."""
        ts_cfg = FRONTEND_DIR / "vite.config.ts"
        self.assertTrue(ts_cfg.exists(), f"missing {ts_cfg}")
        text = ts_cfg.read_text(encoding="utf-8")
        # 必须含 vite/plugin-vue 引入 (标志性 vite ts 配置)
        self.assertIn("plugin-vue", text, "vite.config.ts 缺 plugin-vue 引入")


class TestTi3TsPublicTypes(unittest.TestCase):
    """ti3-TS 公共类型 (src/types/) 验证."""

    def test_types_directory_exists(self):
        self.assertTrue(TYPES_DIR.exists(), f"missing {TYPES_DIR}")

    def test_all_types_modules_exist(self):
        """9 个公共类型 module 全部存在."""
        for name in EXPECTED_TYPES_MODULES:
            p = TYPES_DIR / name
            self.assertTrue(p.exists(), f"missing {p}")

    def test_types_index_exports_all(self):
        """src/types/index.ts 统一导出所有子 module."""
        idx = TYPES_DIR / "index.ts"
        self.assertTrue(idx.exists(), f"missing {idx}")
        text = idx.read_text(encoding="utf-8")
        expected_exports = [
            "./common", "./api", "./auth", "./host",
            "./cron", "./audit", "./terminal", "./setting",
        ]
        for mod in expected_exports:
            self.assertIn(mod, text, f"src/types/index.ts 缺 export * from '{mod}'")


class TestTi3TsEntryFiles(unittest.TestCase):
    """ti3-TS 入口文件 (.ts 化) 验证."""

    def test_all_entry_files_exist(self):
        for p in EXPECTED_ENTRY_FILES:
            self.assertTrue(p.exists(), f"missing {p}")

    def test_main_ts_has_createapp(self):
        """main.ts 必须调用 createApp().mount()."""
        p = SRC_DIR / "main.ts"
        text = p.read_text(encoding="utf-8")
        self.assertIn("createApp", text, "main.ts 缺 createApp 调用")
        self.assertIn(".mount(", text, "main.ts 缺 .mount() 调用")

    def test_api_index_ts_has_axios(self):
        """api/index.ts 必须含 axios 实例."""
        p = SRC_DIR / "api" / "index.ts"
        text = p.read_text(encoding="utf-8")
        self.assertIn("axios", text, "api/index.ts 缺 axios 引用")
        self.assertIn("interceptor", text.lower(), "api/index.ts 缺 interceptor 拦截器")


class TestTi3TsScriptSetupTs(unittest.TestCase):
    """所有 21 views + 7 components 必须用 <script setup lang=\"ts\">."""

    def test_all_views_have_script_setup_ts(self):
        views_dir = SRC_DIR / "views"
        missing = []
        for name in EXPECTED_VIEWS:
            p = views_dir / name
            if not p.exists():
                missing.append(f"NOT_FOUND:{name}")
                continue
            if not _has_script_setup_ts(p):
                missing.append(f"NO_TS:{name}")
        self.assertEqual(
            missing, [],
            "以下 views 不符合 <script setup lang=\"ts\"> 要求:\n  " + "\n  ".join(missing)
        )

    def test_all_components_have_script_setup_ts(self):
        comp_dir = SRC_DIR / "components"
        missing = []
        for name in EXPECTED_COMPONENTS:
            p = comp_dir / name
            if not p.exists():
                missing.append(f"NOT_FOUND:{name}")
                continue
            if not _has_script_setup_ts(p):
                missing.append(f"NO_TS:{name}")
        self.assertEqual(
            missing, [],
            "以下 components 不符合 <script setup lang=\"ts\"> 要求:\n  " + "\n  ".join(missing)
        )


class TestTi3TsUtilsComposables(unittest.TestCase):
    """utils (7) + composables (6) 全部 .ts 验证."""

    def test_all_utils_are_ts(self):
        utils_dir = SRC_DIR / "utils"
        for name in EXPECTED_UTILS:
            p = utils_dir / name
            self.assertTrue(p.exists(), f"missing util {p}")

    def test_all_composables_are_ts(self):
        comp_dir = SRC_DIR / "composables"
        for name in EXPECTED_COMPOSABLES:
            p = comp_dir / name
            self.assertTrue(p.exists(), f"missing composable {p}")

    def test_no_legacy_js_in_migrated_dirs(self):
        """utils/ + composables/ + api/ + router/ + store/ 目录无遗留 .js."""
        legacy_dirs = [
            SRC_DIR / "utils",
            SRC_DIR / "composables",
            SRC_DIR / "api",
            SRC_DIR / "router",
            SRC_DIR / "store",
        ]
        legacy_files = []
        for d in legacy_dirs:
            if not d.exists():
                continue
            for f in d.iterdir():
                if f.is_file() and f.suffix == ".js":
                    legacy_files.append(str(f.relative_to(FRONTEND_DIR)))
        self.assertEqual(
            legacy_files, [],
            "以下 .js 文件应已迁移到 .ts:\n  " + "\n  ".join(legacy_files)
        )


@unittest.skipUnless(
    (FRONTEND_DIR / "node_modules" / ".bin" / "vue-tsc.cmd").exists()
    or (FRONTEND_DIR / "node_modules" / ".bin" / "vue-tsc").exists(),
    "vue-tsc 未安装 (node_modules 缺失)"
)
class TestTi3TsVueTsc(unittest.TestCase):
    """vue-tsc 0 错 (CI 必过)."""

    @classmethod
    def setUpClass(cls):
        # 优先用 npx, 跨平台
        cls.result = _run(
            ["npx", "vue-tsc", "--noEmit"],
            cwd=str(FRONTEND_DIR),
            timeout=300,
        )

    def test_vue_tsc_zero_errors(self):
        returncode, stdout, stderr = self.result
        combined = stdout + stderr
        self.assertEqual(
            returncode, 0,
            f"vue-tsc 失败 (exit {returncode}).\n输出:\n{combined[:3000]}\n"
            f"提示: 跑 `cd frontend && npx vue-tsc --noEmit` 查看详细"
        )


@unittest.skipUnless(
    (FRONTEND_DIR / "node_modules").exists(),
    "node_modules 缺失"
)
class TestTi3TsViteBuild(unittest.TestCase):
    """vite build 验证 (集成在 npm run build = vue-tsc + vite)."""

    @classmethod
    def setUpClass(cls):
        # 跑 npm run build, 内部已含 vue-tsc --noEmit && vite build
        cls.result = _run(
            ["npm", "run", "build"],
            cwd=str(FRONTEND_DIR),
            timeout=300,
        )

    def test_vite_build_succeeds(self):
        returncode, stdout, stderr = self.result
        combined = stdout + stderr
        # 检查关键标志: 'built in' = vite 成功提示
        self.assertEqual(
            returncode, 0,
            f"npm run build 失败 (exit {returncode}).\n输出:\n{combined[:3000]}\n"
        )
        self.assertIn(
            "built in", combined.lower(),
            "vite build 输出缺 'built in' 标志, 可能未真正完成构建"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
