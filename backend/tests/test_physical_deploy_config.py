# -*- coding: utf-8 -*-
"""REV49 物理机后端部署静态配置测试。

静态防回归检查，不连接真实服务器，不启动服务。
"""
import os
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEPLOY_DIR = os.path.join(REPO_ROOT, "deploy")
SYSTEMD_DIR = os.path.join(DEPLOY_DIR, "systemd")
OPS_DIR = os.path.join(REPO_ROOT, "ops")


# =============================================================================
# 1. systemd unit 文件检查
# =============================================================================
class TestSystemdUnit:
    """systemd unit 文件静态校验"""

    @pytest.fixture(autouse=True)
    def load_unit(self):
        path = os.path.join(SYSTEMD_DIR, "orangeserver-backend.service")
        assert os.path.isfile(path), f"systemd unit 不存在: {path}"
        with open(path, "r", encoding="utf-8") as f:
            self.unit = f.read()

    def test_01_unit_exists(self):
        """systemd unit 文件必须存在"""
        assert "orangeserver-backend.service" in self.unit or len(self.unit) > 0

    def test_02_user_orange(self):
        """User=orange (不能是 root)"""
        assert "User=orange" in self.unit

    def test_03_no_root_user(self):
        """不得包含 User=root"""
        assert "User=root" not in self.unit

    def test_04_working_directory(self):
        """WorkingDirectory 指向 backend 子目录 (DEPLOY-AUDIT P0-3: 与 DEPLOY.md
        文件布局 /opt/orangeserver/app/backend 对齐)"""
        assert "WorkingDirectory=/opt/orangeserver/app/backend" in self.unit

    def test_05_environment_file(self):
        """EnvironmentFile 指向安全位置"""
        assert "EnvironmentFile=/etc/orangeserver/backend.env" in self.unit

    def test_06_entry_point_wsgi(self):
        """入口为 wsgi:app (不是 init:app)"""
        assert "wsgi:app" in self.unit
        assert "init:app" not in self.unit

    def test_07_worker_class(self):
        """worker class 为 GeventWebSocketWorker"""
        assert "GeventWebSocketWorker" in self.unit

    def test_08_single_worker(self):
        """--workers 1 (APScheduler 必须单实例)"""
        assert "--workers 1" in self.unit

    def test_09_no_multi_worker(self):
        """不得包含 --workers 2 或更多"""
        assert "--workers 2" not in self.unit
        assert "--workers 3" not in self.unit
        assert "--workers 4" not in self.unit

    def test_10_bind_loopback(self):
        """bind 为 127.0.0.1:28000 (不能 0.0.0.0)"""
        assert "127.0.0.1:28000" in self.unit
        assert "0.0.0.0:28000" not in self.unit

    def test_11_no_preload(self):
        """不得使用 --preload (会导致 Scheduler 在 master 进程启动)"""
        assert "--preload" not in self.unit

    def test_12_restart_on_failure(self):
        """Restart=on-failure"""
        assert "Restart=on-failure" in self.unit

    def test_13_security_hardening(self):
        """安全加固: NoNewPrivileges, PrivateTmp"""
        assert "NoNewPrivileges=true" in self.unit
        assert "PrivateTmp=true" in self.unit

    def test_14_kill_signal(self):
        """KillSignal=SIGTERM (让 gevent 排空 WebSocket)"""
        assert "KillSignal=SIGTERM" in self.unit


# =============================================================================
# 2. 环境文件模板检查
# =============================================================================
class TestBackendEnvExample:
    """systemd 环境模板静态校验"""

    @pytest.fixture(autouse=True)
    def load_env(self):
        path = os.path.join(SYSTEMD_DIR, "backend.env.example")
        assert os.path.isfile(path), f"环境模板不存在: {path}"
        with open(path, "r", encoding="utf-8") as f:
            self.env = f.read()

    def test_01_no_real_secrets(self):
        """模板不含真实密钥"""
        # 不应包含看起来像真实 base64 密钥的内容
        lines = self.env.split("\n")
        for line in lines:
            if line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            if key in ("OGS_FLASK_SECRET_KEY", "OGS_FERNET_KEYS"):
                # 值应该是占位符或空
                assert val == "" or val.startswith("__") or "CHANGE" in val.upper(), \
                    f"{key} 疑似包含真实密钥"

    def test_02_required_keys_present(self):
        """包含全部必需键"""
        required = [
            "OGS_ENV", "OGS_FLASK_SECRET_KEY", "OGS_FERNET_KEYS",
            "OGS_MYSQL_HOST", "OGS_MYSQL_PORT", "OGS_MYSQL_PASSWORD",
            "OGS_REDIS_HOST", "OGS_REDIS_PORT",
            "OGS_DATA_DIR",
        ]
        for key in required:
            assert f"{key}=" in self.env, f"缺少 {key}"

    def test_03_placeholders_identifiable(self):
        """占位符以 __REQUIRED 或 __FILL 开头，可被预检识别"""
        assert "__REQUIRED" in self.env
        assert "__FILL" in self.env or "OGS_REDIS_PASSWORD=" in self.env

    def test_04_data_dir_configured(self):
        """OGS_DATA_DIR 指向物理机数据目录"""
        assert "OGS_DATA_DIR=/data/orangeserver" in self.env

    def test_05_https_proxy_defaults_match_nginx_template(self):
        """systemd 模板默认配合单层 HTTPS nginx 反代"""
        assert "OGS_HTTPS=true" in self.env
        assert "OGS_PROXY_LAYERS=1" in self.env


# =============================================================================
# 3. 预检脚本检查
# =============================================================================
class TestPreflightPhysicalBackend:
    """物理机预检脚本静态校验"""

    @pytest.fixture(autouse=True)
    def load_script(self):
        path = os.path.join(OPS_DIR, "preflight-physical-backend.sh")
        assert os.path.isfile(path), f"预检脚本不存在: {path}"
        with open(path, "r", encoding="utf-8") as f:
            self.script = f.read()

    def test_01_strict_mode(self):
        """必须使用 set -Eeuo pipefail"""
        assert "set -Eeuo pipefail" in self.script

    def test_02_checks_port_28000(self):
        """检查 28000 端口"""
        assert "28000" in self.script

    def test_03_checks_env_file(self):
        """检查环境文件"""
        assert "/etc/orangeserver/backend.env" in self.script

    def test_04_checks_python_version(self):
        """检查 Python 版本"""
        assert "Python 3" in self.script or "python" in self.script.lower()

    def test_05_checks_imports(self):
        """检查依赖导入"""
        for mod in ["flask", "gevent", "gunicorn", "cryptography", "bcrypt"]:
            assert mod in self.script, f"预检缺少 {mod} 导入检查"

    def test_06_no_secrets_output(self):
        """不输出密码/密钥值"""
        # 脚本中不应有 cat 或 echo 环境文件内容的命令
        assert "cat /etc/orangeserver/backend.env" not in self.script

    def test_07_checks_data_dirs(self):
        """检查数据目录"""
        for subdir in ["avatars", "file", "key", "log", "containers/temp"]:
            assert subdir in self.script, f"预检缺少 {subdir} 目录检查"

    def test_08_checks_mysql_redis(self):
        """检查 MySQL/Redis 连通"""
        assert "MYSQL" in self.script or "mysql" in self.script
        assert "REDIS" in self.script or "redis" in self.script


# =============================================================================
# 4. .gitattributes 检查
# =============================================================================
class TestGitattributes:
    """.gitattributes 强制 LF 换行"""

    @pytest.fixture(autouse=True)
    def load_gitattributes(self):
        path = os.path.join(REPO_ROOT, ".gitattributes")
        assert os.path.isfile(path), f".gitattributes 不存在: {path}"
        with open(path, "r", encoding="utf-8") as f:
            self.content = f.read()

    def test_01_sh_lf(self):
        """*.sh 强制 LF"""
        assert "*.sh" in self.content and "eol=lf" in self.content

    def test_02_service_lf(self):
        """*.service 强制 LF"""
        assert "*.service" in self.content and "eol=lf" in self.content

    def test_03_conf_lf(self):
        """*.conf 强制 LF"""
        assert "*.conf" in self.content and "eol=lf" in self.content

    def test_04_env_example_lf(self):
        """*.env.example 强制 LF"""
        assert "*.env.example" in self.content and "eol=lf" in self.content
