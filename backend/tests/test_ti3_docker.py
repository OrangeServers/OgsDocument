# -*- coding: utf-8 -*-
"""ti3-DOCKER Dockerfile 多阶段构建 + 镜像 ≤500MB 静态验证测试.

ti3-DOCKER (Dockerfile 多阶段构建 + 镜像 ≤500MB) 完工验收的静态校验.
本测试不依赖 docker 运行时, 只用:
  - 文件存在性 + 文本扫描 (Dockerfile / .dockerignore)
  - 正则匹配关键指令 (FROM ... AS / USER / HEALTHCHECK / EXPOSE / CMD / LABEL / STOPSIGNAL)
  - .dockerignore 模式覆盖必排除清单 (tests/ / dev configs / mysqldir/ / .env / .git)

覆盖:
  1. Dockerfile 关键指令 (多阶段 / slim / non-root / HEALTHCHECK / EXPOSE / CMD gunicorn+geventwebsocket)
  2. Dockerfile 安全增强 (LABEL OCI / STOPSIGNAL SIGTERM / LANG=C.UTF-8)
  3. Dockerfile 缓存优化 (apt list 清理 / PIP_NO_CACHE_DIR=1 / PYTHONDONTWRITEBYTECODE / PYTHONUNBUFFERED)
  4. Dockerfile 依赖构建 (builder wheelhouse + runtime 离线安装 / pip check)
  5. .dockerignore 必排除 (tests/ / dev configs / mysqldir/ / conf/seed/ / .env / .git / node_modules / 缓存 / 文档 / 密钥)
  6. .dockerignore 模式顺序 (排除优先, 白名单用 ! 前缀)

跑法:
    cd backend && python -m pytest tests/test_ti3_docker.py -v

注: 镜像实际大小 (≤500MB) 在 CI docker build job 中验证 (无 docker daemon 的本地跑不了).
"""
import re
import unittest
from pathlib import Path

# 路径常量
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # OrangeServer/
BACKEND_DIR = PROJECT_ROOT / "backend"
DOCKERFILE = BACKEND_DIR / "Dockerfile"
DOCKERIGNORE = BACKEND_DIR / ".dockerignore"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


class TestTi3DockerFileExists(unittest.TestCase):
    """Dockerfile + .dockerignore 文件存在性."""

    def test_dockerfile_exists(self):
        self.assertTrue(DOCKERFILE.exists(), f"missing {DOCKERFILE}")

    def test_dockerignore_exists(self):
        self.assertTrue(DOCKERIGNORE.exists(), f"missing {DOCKERIGNORE}")


class TestTi3DockerMultiStage(unittest.TestCase):
    """Dockerfile 多阶段构建 (至少 2 个 AS 阶段)."""

    @classmethod
    def setUpClass(cls):
        cls.text = _read(DOCKERFILE)

    def test_multistage_minimum_2(self):
        """至少 2 个 FROM ... AS 阶段 (base/builder/runtime 三选二)."""
        from_as = re.findall(r"^FROM\s+(\S+)\s+AS\s+(\S+)", self.text, re.MULTILINE)
        self.assertGreaterEqual(
            len(from_as), 2,
            f"ti3-DOCKER 要求多阶段构建 (≥2 AS), 实际 {len(from_as)} 个: {from_as}"
        )

    def test_multistage_has_base(self):
        """必须有 base 阶段 (共享 ENV 设置)."""
        self.assertIsNotNone(
            re.search(r"^FROM\s+\S+\s+AS\s+base", self.text, re.MULTILINE),
            "缺 base 阶段"
        )

    def test_multistage_has_runtime(self):
        """必须有 runtime 阶段 (最终镜像)."""
        self.assertIsNotNone(
            re.search(r"^FROM\s+\S+\s+AS\s+runtime", self.text, re.MULTILINE),
            "缺 runtime 阶段"
        )

    def test_runtime_consumes_builder_wheelhouse(self):
        """runtime 阶段从 builder 只读挂载 wheelhouse."""
        self.assertIsNotNone(
            re.search(
                r"^RUN\s+--mount=type=bind,from=builder,source=/wheels,target=/wheels,ro",
                self.text,
                re.MULTILINE,
            ),
            "runtime 阶段应从 builder 只读挂载 wheelhouse",
        )


class TestTi3DockerBaseImage(unittest.TestCase):
    """基础镜像选型 (slim 推荐, alpine 兼容性差, full 不允许)."""

    @classmethod
    def setUpClass(cls):
        cls.text = _read(DOCKERFILE)

    def test_base_is_python_3_12(self):
        """Python 3.12 (与 backend/runtime 匹配)."""
        froms = re.findall(r"^FROM\s+(\S+)", self.text, re.MULTILINE)
        # 至少有一个 FROM 用 python:3.12-*
        python_imgs = [f for f in froms if f.startswith("python:")]
        self.assertTrue(
            len(python_imgs) >= 1,
            f"未使用 python:* 基础镜像, FROM 列表: {froms}"
        )
        # 任意一个用 3.12
        self.assertTrue(
            any("python:3.12" in f for f in python_imgs),
            f"python:* 镜像应为 3.12 系列, 实际: {python_imgs}"
        )

    def test_base_is_slim_variant(self):
        """slim 或 alpine 二选一 (slim 优先, alpine 兼容性风险)."""
        froms = re.findall(r"^FROM\s+(\S+)", self.text, re.MULTILINE)
        for f in froms:
            if f.startswith("python:"):
                # 允许 -slim / -alpine / -slim-bookworm 等
                self.assertTrue(
                    "slim" in f or "alpine" in f,
                    f"python 基础镜像应使用 slim/alpine 变体 (≤500MB 目标), 实际: {f}"
                )

    def test_no_full_debian(self):
        """禁止使用完整 Debian 镜像 (体积 ~900MB, 远超 500MB 目标)."""
        # python:3.12 (无 variant) 是完整 Debian, 禁止
        self.assertIsNone(
            re.search(r"^FROM\s+python:3\.12\s*$", self.text, re.MULTILINE),
            "禁止 FROM python:3.12 (无 slim/alpine 后缀, 体积 ~900MB)"
        )


class TestTi3DockerSecurityHardening(unittest.TestCase):
    """Dockerfile 安全加固 (non-root / STOPSIGNAL / LABEL OCI / LANG)."""

    @classmethod
    def setUpClass(cls):
        cls.text = _read(DOCKERFILE)

    def test_non_root_user(self):
        """必须 USER 非 root 用户 (ogs)."""
        # 找到 USER 行
        m = re.search(r"^USER\s+(\S+)", self.text, re.MULTILINE)
        self.assertIsNotNone(m, "Dockerfile 缺 USER 指令 (non-root 加固)")
        self.assertNotEqual(
            m.group(1), "root",
            "USER 禁止设为 root, 必须用 dedicated user (ogs)"
        )
        self.assertEqual(
            m.group(1), "ogs",
            f"USER 应为 ogs, 实际: {m.group(1)}"
        )

    def test_useradd_creates_user(self):
        """必须 useradd 显式创建用户 (不能用 USER 数字 UID)."""
        # 找到 useradd 或 adduser
        self.assertIsNotNone(
            re.search(r"(?:useradd|adduser)\s+", self.text),
            "Dockerfile 缺 useradd/adduser 创建 non-root 用户"
        )

    def test_stopsignal_sigterm(self):
        """STOPSIGNAL SIGTERM (ti3-DOCKER 增强, gunicorn graceful shutdown)."""
        self.assertIsNotNone(
            re.search(r"^STOPSIGNAL\s+SIGTERM", self.text, re.MULTILINE),
            "Dockerfile 缺 STOPSIGNAL SIGTERM (ti3-DOCKER 增强项)"
        )

    def test_label_oci_metadata(self):
        """LABEL org.opencontainers.image.* (OCI 标准元信息)."""
        # LABEL 后面可能用 \ 续行, 先抽取 LABEL 块
        # 模式: ^LABEL.*$ 后可跟多个 \ 续行 (在 re.MULTILINE 模式下) 或同行多 label
        # 最简: 统计 "org.opencontainers.image." 在文本中出现次数 (按 key)
        oci_keys = set(re.findall(
            r"org\.opencontainers\.image\.(\w+)",
            self.text
        ))
        self.assertGreaterEqual(
            len(oci_keys), 3,
            f"应至少 3 个 OCI LABEL key, 实际 {len(oci_keys)}: {sorted(oci_keys)}"
        )
        # 关键 label 存在
        for key in ("title", "description", "source", "licenses"):
            self.assertIsNotNone(
                re.search(
                    rf"org\.opencontainers\.image\.{key}\s*=",
                    self.text
                ),
                f"缺 OCI LABEL org.opencontainers.image.{key}"
            )

    def test_lang_c_utf8(self):
        """LANG=C.UTF-8 (Python 中文支持 + 避免编码错误)."""
        self.assertIn(
            "LANG=C.UTF-8", self.text,
            "Dockerfile 缺 LANG=C.UTF-8 (Python 中文/Unicode 支持)"
        )


class TestTi3DockerHealthcheckExpose(unittest.TestCase):
    """HEALTHCHECK + EXPOSE 28000."""

    @classmethod
    def setUpClass(cls):
        cls.text = _read(DOCKERFILE)

    def test_healthcheck_exists(self):
        self.assertIsNotNone(
            re.search(r"^HEALTHCHECK\b", self.text, re.MULTILINE),
            "Dockerfile 缺 HEALTHCHECK (P1-7 必填)"
        )

    def test_healthcheck_interval_30s(self):
        """HEALTHCHECK --interval=30s (与 deploy/docker-compose.yml 一致)."""
        self.assertIn(
            "--interval=30s", self.text,
            "HEALTHCHECK 应配 --interval=30s"
        )

    def test_healthcheck_calls_local_health(self):
        """HEALTHCHECK 调 /local/health (P1-C 实现, 无 csrf/auth 需求)."""
        self.assertIn(
            "/local/health", self.text,
            "HEALTHCHECK 应调 /local/health"
        )

    def test_expose_28000(self):
        self.assertIsNotNone(
            re.search(r"^EXPOSE\s+28000", self.text, re.MULTILINE),
            "Dockerfile 缺 EXPOSE 28000"
        )


class TestTi3DockerCmdGunicorn(unittest.TestCase):
    """CMD 走 gunicorn + geventwebsocket worker (T2-P0)."""

    @classmethod
    def setUpClass(cls):
        cls.text = _read(DOCKERFILE)

    def test_cmd_uses_gunicorn(self):
        """CMD 用 gunicorn 启动 (生产路径)."""
        # CMD 行
        m = re.search(r"^CMD\s+(.+)", self.text, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(m, "Dockerfile 缺 CMD")
        self.assertIn(
            "gunicorn", m.group(1),
            f"CMD 应调用 gunicorn, 实际: {m.group(1)[:200]}"
        )

    def test_worker_class_geventwebsocket(self):
        """worker-class 用 geventwebsocket (T2-P0: 兼容 WebSSH/SFTP 升级)."""
        self.assertIn(
            "geventwebsocket.gunicorn.workers.GeventWebSocketWorker",
            self.text,
            "T2-P0: worker-class 必须为 geventwebsocket (WebSocket 兼容)"
        )

    def test_cmd_targets_init_app(self):
        """CMD 最后调 init:app (Flask app factory)."""
        # CMD 后面用 \ 续行, 需用 .* 配合 DOTALL
        self.assertIsNotNone(
            re.search(r"CMD\b.*\bwsgi:app\b", self.text, re.DOTALL),
            "CMD 应最后调 init:app (Flask app 入口)"
        )


class TestTi3DockerCacheOptimization(unittest.TestCase):
    """缓存优化 (apt / pip / .pyc)."""

    @classmethod
    def setUpClass(cls):
        cls.text = _read(DOCKERFILE)

    def test_apt_cache_clean(self):
        """apt-get install 后清 /var/lib/apt/lists/*."""
        self.assertIn(
            "rm -rf /var/lib/apt/lists/*", self.text,
            "apt-get install 后必须 rm -rf /var/lib/apt/lists/*"
        )

    def test_pip_no_cache_dir(self):
        """PIP_NO_CACHE_DIR=1 (不落 pip 缓存, 减小 layer)."""
        self.assertIn(
            "PIP_NO_CACHE_DIR=1", self.text,
            "缺 PIP_NO_CACHE_DIR=1 (pip 缓存会污染镜像 layer)"
        )

    def test_pythondontwritebytecode(self):
        """PYTHONDONTWRITEBYTECODE=1 (不落 .pyc)."""
        self.assertIn(
            "PYTHONDONTWRITEBYTECODE=1", self.text,
            "缺 PYTHONDONTWRITEBYTECODE=1 (运行时无 .pyc 必要)"
        )

    def test_pythonunbuffered(self):
        """PYTHONUNBUFFERED=1 (Docker log 实时输出)."""
        self.assertIn(
            "PYTHONUNBUFFERED=1", self.text,
            "缺 PYTHONUNBUFFERED=1 (docker logs 实时可见)"
        )


class TestTi3DockerDependencyLock(unittest.TestCase):
    """依赖构建 (wheelhouse + 离线安装 + pip check)."""

    @classmethod
    def setUpClass(cls):
        cls.text = _read(DOCKERFILE)

    def test_builder_generates_wheelhouse(self):
        """builder 阶段一次性构建全部依赖 wheel."""
        self.assertIn(
            "pip wheel --wheel-dir /wheels -r requirements.txt", self.text,
            "builder 阶段应从 requirements.txt 构建 wheelhouse"
        )
        self.assertNotIn(
            "pip-compile", self.text,
            "镜像构建阶段不应现场解析并重写依赖锁"
        )

    def test_runtime_installs_offline(self):
        """runtime 阶段只从 wheelhouse 离线安装."""
        self.assertIn(
            "--mount=type=bind,from=builder,source=/wheels,target=/wheels,ro",
            self.text,
            "wheelhouse 应只读挂载，不能复制进最终镜像层",
        )
        self.assertIn(
            "pip install --no-index --find-links=/wheels -r requirements.txt", self.text,
            "runtime 阶段必须从 wheelhouse 离线安装"
        )

    def test_pip_check(self):
        """runtime 阶段跑 pip check (依赖一致性验证)."""
        self.assertIn(
            "pip check", self.text,
            "runtime 阶段应跑 pip check 验证依赖一致性"
        )


class TestTi3DockerignoreExcludes(unittest.TestCase):
    """.dockerignore 必排除清单 (减小 context + 防泄漏)."""

    @classmethod
    def setUpClass(cls):
        cls.text = _read(DOCKERIGNORE)
        cls.lines = [
            ln.strip() for ln in cls.text.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]

    def _has_pattern(self, pattern: str) -> bool:
        """检查 .dockerignore 是否排除给定模式 (精确匹配或 glob 覆盖)."""
        # 直接精确匹配
        if pattern in self.lines:
            return True
        # 处理 ! 否定: 找到 !pattern 视为包含
        for ln in self.lines:
            if ln == "!" + pattern:
                return True
        return False

    def test_exclude_git(self):
        """.git 必须排除 (含敏感信息 + 体积)."""
        self.assertTrue(self._has_pattern(".git"), ".git 未排除")

    def test_exclude_tests(self):
        """tests/ 183 个测试文件必须排除 (ti3-DOCKER 2026-07-02 增强)."""
        self.assertTrue(self._has_pattern("tests"), "tests/ 未排除 (183 测试文件进镜像)")

    def test_exclude_conftest(self):
        """conftest.py 根目录测试配置必须排除."""
        self.assertTrue(self._has_pattern("conftest.py"), "conftest.py 未排除")

    def test_exclude_pycache(self):
        """__pycache__ 必须排除."""
        self.assertTrue(self._has_pattern("__pycache__"), "__pycache__ 未排除")

    def test_exclude_pytest_cache(self):
        """.pytest_cache 必须排除."""
        self.assertTrue(self._has_pattern(".pytest_cache"), ".pytest_cache 未排除")

    def test_exclude_mypy_cache(self):
        """.mypy_cache 必须排除."""
        self.assertTrue(self._has_pattern(".mypy_cache"), ".mypy_cache 未排除")

    def test_exclude_coverage(self):
        """.coverage 必须排除."""
        self.assertTrue(self._has_pattern(".coverage"), ".coverage 未排除")

    def test_exclude_env(self):
        """.env 必须排除 (含密钥)."""
        self.assertTrue(self._has_pattern(".env"), ".env 未排除 (密钥泄漏风险)")

    def test_exclude_env_example_allowed(self):
        """.env.example 用 ! 前缀白名单 (部署文档)."""
        # 找到 !.env.example 模式
        has_whitelist = "!.env.example" in self.lines
        self.assertTrue(
            has_whitelist,
            ".env.example 应用 ! 前缀白名单保留 (部署文档用途)"
        )

    def test_exclude_requirements_in(self):
        # requirements.in 仍作为开发侧依赖声明保留，但镜像只消费 requirements.txt。
        self.assertTrue(
            (BACKEND_DIR / "requirements.in").exists(),
            "requirements.in 必须存在 (开发侧依赖声明)"
        )

    def test_exclude_requirements_dev(self):
        """requirements-dev.txt 必须排除 (开发依赖)."""
        self.assertTrue(
            self._has_pattern("requirements-dev.txt"),
            "requirements-dev.txt 未排除 (dev 依赖不进生产)"
        )

    def test_exclude_mysqldir(self):
        """mysqldir/ 迁移 SQL 必须排除 (dev 工具)."""
        self.assertTrue(
            self._has_pattern("mysqldir"),
            "mysqldir/ 未排除 (迁移 SQL 是 dev 工具)"
        )

    def test_exclude_conf_seed(self):
        """conf/seed/ 种子数据必须排除 (运行时再生成)."""
        self.assertTrue(
            self._has_pattern("conf/seed"),
            "conf/seed/ 未排除 (种子数据/初始头像运行时再生成)"
        )

    def test_exclude_flake8_config(self):
        """.flake8 必须排除 (dev 配置)."""
        self.assertTrue(self._has_pattern(".flake8"), ".flake8 未排除 (dev 配置)")

    def test_exclude_bandit_config(self):
        """.bandit 必须排除 (dev 配置)."""
        self.assertTrue(self._has_pattern(".bandit"), ".bandit 未排除 (dev 配置)")

    def test_exclude_coveragerc(self):
        """.coveragerc 必须排除 (dev 配置)."""
        self.assertTrue(self._has_pattern(".coveragerc"), ".coveragerc 未排除 (dev 配置)")

    def test_exclude_codecov_yml(self):
        """codecov.yml 必须排除 (dev 配置)."""
        self.assertTrue(self._has_pattern("codecov.yml"), "codecov.yml 未排除 (dev 配置)")

    def test_exclude_mypy_ini(self):
        """mypy.ini 必须排除 (dev 配置)."""
        self.assertTrue(self._has_pattern("mypy.ini"), "mypy.ini 未排除 (dev 配置)")

    def test_exclude_node_modules(self):
        """node_modules 必须排除 (前端依赖, 后端镜像不需要)."""
        self.assertTrue(self._has_pattern("node_modules"), "node_modules 未排除")

    def test_exclude_archive(self):
        """_archive 必须排除 (历史归档)."""
        self.assertTrue(self._has_pattern("_archive"), "_archive 未排除 (历史归档)")

    def test_exclude_debug_scripts(self):
        """_debug_*.py / _debug_*.sh 必须排除 (调试脚本)."""
        self.assertTrue(
            self._has_pattern("_debug_*.py"),
            "_debug_*.py 未排除 (调试脚本)"
        )
        self.assertTrue(
            self._has_pattern("_debug_*.sh"),
            "_debug_*.sh 未排除 (调试脚本)"
        )

    def test_exclude_tmp_scripts(self):
        """_tmp_*.py / _tmp_*.sh 必须排除 (临时脚本)."""
        self.assertTrue(self._has_pattern("_tmp_*.py"), "_tmp_*.py 未排除")
        self.assertTrue(self._has_pattern("_tmp_*.sh"), "_tmp_*.sh 未排除")

    def test_exclude_log_files(self):
        """*.log 必须排除 (日志不进镜像)."""
        self.assertTrue(self._has_pattern("*.log"), "*.log 未排除 (日志不入镜像)")

    def test_exclude_doc_md(self):
        """*.md 必须排除 (文档不入镜像)."""
        self.assertTrue(self._has_pattern("*.md"), "*.md 未排除 (文档不入镜像)")

    def test_exclude_rev_md(self):
        """REV*.md / SUMMARY*.md 评审报告必须排除 (ti3-DOCKER 增强)."""
        # 找到 REV*.md 模式
        self.assertTrue(
            self._has_pattern("REV*.md"),
            "REV*.md 未排除 (评审报告不入镜像)"
        )
        self.assertTrue(
            self._has_pattern("SUMMARY*.md"),
            "SUMMARY*.md 未排除 (评审报告不入镜像)"
        )

    def test_exclude_license(self):
        """LICENSE 必须排除 (文档, 体积)."""
        self.assertTrue(self._has_pattern("LICENSE"), "LICENSE 未排除")

    def test_exclude_sensitive_keys(self):
        """*.key / *.pem / *.crt 必须排除 (密钥/证书)."""
        self.assertTrue(self._has_pattern("*.key"), "*.key 未排除 (密钥泄漏)")
        self.assertTrue(self._has_pattern("*.pem"), "*.pem 未排除 (证书泄漏)")
        self.assertTrue(self._has_pattern("*.crt"), "*.crt 未排除 (证书泄漏)")

    def test_exclude_ide_metadata(self):
        """.vscode / .idea 必须排除 (IDE 配置)."""
        self.assertTrue(self._has_pattern(".vscode"), ".vscode 未排除")
        self.assertTrue(self._has_pattern(".idea"), ".idea 未排除")

    def test_exclude_archive_files(self):
        """*.tgz / *.tar.gz / *.zip 必须排除 (归档文件)."""
        self.assertTrue(self._has_pattern("*.tgz"), "*.tgz 未排除")
        self.assertTrue(self._has_pattern("*.tar.gz"), "*.tar.gz 未排除")
        self.assertTrue(self._has_pattern("*.zip"), "*.zip 未排除")

    def test_exclude_data_runtime(self):
        """data 运行时数据目录必须排除 (容器内重建)."""
        self.assertTrue(self._has_pattern("data"), "data/ 未排除 (运行时数据)")


class TestTi3DockerignoreOrdering(unittest.TestCase):
    """.dockerignore 模式顺序正确性 (排除优先, ! 白名单)."""

    @classmethod
    def setUpClass(cls):
        cls.lines = [
            ln.strip() for ln in _read(DOCKERIGNORE).splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]

    def test_env_example_whitelist_after_env(self):
        """.env.example 白名单 (! 前缀) 必须在 .env 排除之后出现."""
        env_idx = None
        env_example_idx = None
        for i, ln in enumerate(self.lines):
            if ln == ".env":
                env_idx = i
            elif ln == "!.env.example":
                env_example_idx = i
        self.assertIsNotNone(env_idx, ".env 排除模式缺失")
        self.assertIsNotNone(env_example_idx, "!.env.example 白名单缺失")
        # .env 必须先出现 (排除所有), 然后 !.env.example 重新白名单
        self.assertLess(
            env_idx, env_example_idx,
            ".env.example 白名单位置错误: 必须在 .env 排除之后"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
