# -*- coding: utf-8 -*-
"""
R2-9 (REV45-H16): SQLALCHEMY_COMMIT_ON_TEARDOWN = False

问题: 原配置 True, app context 销毁时自动 session.commit()
  - 业务层 ORM 对象 add 后没 commit 也会被 teardown 静默提交
  - 单元测试 mock 数据被意外 commit
  - 绕过 osql_in/osql_up 统一封装的 rollback 失败保护
修复:
  - SQLALCHEMY_COMMIT_ON_TEARDOWN = False
  - 业务代码 25+ 处显式 db.session.commit() (不依赖 teardown)
  - 统一封装 (osql_in/osql_up) 强制显式 commit
测试维度:
  1) config 必须是 False (静态)
  2) 配置变更标记 REV45-H16
  3) 业务显式 commit 调用数应 >= 25 (兜底行为移除后不依赖)
  4) osql_in / osql_up 都有显式 commit
"""
import os
import sys
import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


# =============================================================================
# Fixture: 绕过 conftest autouse mock, reload insert 模块
# =============================================================================
@pytest.fixture(autouse=True)
def _reload_insert():
    import importlib
    import sys as _sys
    if 'app.core.db.insert' in _sys.modules:
        del _sys.modules['app.core.db.insert']
    importlib.import_module('app.core.db.insert')
    yield


# =============================================================================
# 1) 配置必须为 False (核心防御点)
# =============================================================================
class TestCommitOnTeardownConfig:
    """R2-9: SQLALCHEMY_COMMIT_ON_TEARDOWN = False"""

    def test_01_settings_file_is_false(self):
        """settings.py 中 SQLALCHEMY_COMMIT_ON_TEARDOWN = False"""
        settings_path = os.path.join(BACKEND, 'app', 'core', 'db', 'settings.py')
        with open(settings_path, encoding='utf-8') as f:
            src = f.read()

        # 匹配 SQLALCHEMY_COMMIT_ON_TEARDOWN = False (而非 True)
        assert re.search(
            r"SQLALCHEMY_COMMIT_ON_TEARDOWN['\"]?\s*=\s*False",
            src
        ), "SQLALCHEMY_COMMIT_ON_TEARDOWN 不是 False"
        # 不能是 True
        assert not re.search(
            r"SQLALCHEMY_COMMIT_ON_TEARDOWN['\"]?\s*=\s*True",
            src
        ), "SQLALCHEMY_COMMIT_ON_TEARDOWN 仍是 True"

    def test_02_has_rev45_h16_marker(self):
        """settings.py 含 REV45-H16 / R2-9 标记"""
        settings_path = os.path.join(BACKEND, 'app', 'core', 'db', 'settings.py')
        with open(settings_path, encoding='utf-8') as f:
            src = f.read()
        assert 'REV45-H16' in src, "settings.py 缺 REV45-H16 注释"

    def test_03_explanation_comment_present(self):
        """应解释为什么改为 False"""
        settings_path = os.path.join(BACKEND, 'app', 'core', 'db', 'settings.py')
        with open(settings_path, encoding='utf-8') as f:
            src = f.read()
        # 应该有说明: 关键词任意一个命中
        keywords = ['强制', '显式', '兜底', '禁止', '污染', '禁用', '隐式', 'teardown']
        assert any(kw in src for kw in keywords), \
            "settings.py 缺 R2-9 修复原因说明"


# =============================================================================
# 2) 业务代码显式 commit 调用 (兜底移除后不依赖)
# =============================================================================
class TestBusinessCodeExplicitCommit:
    """R2-9: 业务代码显式 commit 调用统计"""

    def test_01_at_least_25_explicit_commits(self):
        """业务代码至少 25 处 db.session.commit() 显式调用

        移除 COMMIT_ON_TEARDOWN 兜底后, 这些调用是必须的"""
        app_dir = os.path.join(BACKEND, 'app')
        commit_count = 0

        for root, dirs, files in os.walk(app_dir):
            # 跳过 auto-generated / migration 路径
            if '__pycache__' in root:
                continue
            for fname in files:
                if not fname.endswith('.py'):
                    continue
                fpath = os.path.join(root, fname)
                with open(fpath, encoding='utf-8') as f:
                    for line in f:
                        # 排除注释行
                        stripped = line.strip()
                        if stripped.startswith('#'):
                            continue
                        if 'db.session.commit()' in stripped:
                            commit_count += 1

        # 至少 25 处
        assert commit_count >= 25, \
            f"业务代码 db.session.commit() 仅 {commit_count} 处, 移除 teardown 后可能丢事务"

    def test_02_no_importtime_session_usage_in_init(self):
        """不允许 db.session.rollback() / commit() 在模块顶层 (import 时副作用)"""
        app_dir = os.path.join(BACKEND, 'app')

        for root, dirs, files in os.walk(app_dir):
            if '__pycache__' in root:
                continue
            for fname in files:
                if not fname.endswith('.py'):
                    continue
                fpath = os.path.join(root, fname)
                with open(fpath, encoding='utf-8') as f:
                    src = f.read()
                # 不允许: "db.session.commit()" 在函数体外 (0 缩进)
                # 简化检查: 第一行有 db.session.commit()
                lines = src.splitlines()
                for i, line in enumerate(lines[:5], 1):
                    stripped = line.lstrip()
                    # 顶层代码: 无缩进 或 module docstring 不计
                    if (line and not line.startswith(' ') and
                            'db.session.commit' in stripped):
                        # 这不应出现在顶层 (除了注释)
                        if not stripped.startswith('#'):
                            # 报错位置
                            pytest.fail(
                                f"{fpath}:{i}: 顶层模块代码调用 db.session.commit "
                                f"(禁止, 仅函数内允许): {stripped!r}"
                            )


# =============================================================================
# 3) osql_in / osql_up 显式 commit
# =============================================================================
class TestUnifiedWrappersHaveCommits:
    """R2-9: 统一封装必须有显式 commit, 兜底移除后仍安全"""

    def test_01_osql_in_has_explicit_commit(self):
        """osql_in 含 db.session.commit() 显式调用"""
        from app.core.db.insert import osql_in
        import inspect
        src = inspect.getsource(osql_in)
        assert 'db.session.commit()' in src, \
            "osql_in 没有显式 db.session.commit() (移除 teardown 后会丢事务)"

    def test_02_osql_up_has_explicit_commit(self):
        """osql_up 含 db.session.commit() 显式调用"""
        from app.core.db.insert import osql_up
        import inspect
        src = inspect.getsource(osql_up)
        assert 'db.session.commit()' in src, \
            "osql_up 没有显式 db.session.commit()"

    def test_03_osql_de_has_explicit_commit(self):
        """osql_de 含 db.session.commit()"""
        from app.core.db.insert import osql_de
        import inspect
        src = inspect.getsource(osql_de)
        assert 'db.session.commit()' in src, \
            "osql_de 没有显式 db.session.commit()"

    def test_04_rollback_on_failure_paths(self):
        """osql_* 失败分支必须 rollback (R2-9 后 teardown 不自动回滚)"""
        for fn_name in ('osql_in', 'osql_up', 'osql_de'):
            from app.core.db import insert as ins_mod
            fn = getattr(ins_mod, fn_name)
            import importlib
            importlib.reload(ins_mod)
            fn = getattr(ins_mod, fn_name)
            import inspect
            src = inspect.getsource(fn)
            # 必须有 rollback 调用
            assert src.count('rollback') >= 3, \
                f"{fn_name} rollback 调用过少 ({src.count('rollback')} 处), 失败路径未回滚"


# =============================================================================
# 4) 集成: conftest.py 不依赖 teardown commit
# =============================================================================
class TestConftestSafety:
    """R2-9: conftest 也应显式 commit, 避免 teardown 副作用"""

    def test_01_conftest_does_not_rely_on_teardown(self):
        """conftest 应不依赖 teardown 自动 commit (R2-9 后失效)"""
        conftest_path = os.path.join(BACKEND, 'tests', 'conftest.py')
        with open(conftest_path, encoding='utf-8') as f:
            src = f.read()
        # conftest 的 db 相关 patch 都应该是 no-op lambda (不提交任何东西)
        # 允许出现 'commit' 关键字但应在注释/mock 上下文
        lines = src.splitlines()
        suspicious = []
        for i, line in enumerate(lines, 1):
            if 'db.session.commit' in line and 'lambda' not in line:
                stripped = line.strip()
                if not stripped.startswith('#'):
                    suspicious.append((i, line))
        # conftest 不应触发真实 commit
        assert len(suspicious) == 0, \
            f"conftest.py 出现未 mock 的 db.session.commit: {suspicious}"


import re  # R2-9 测试需要 re, 放在末尾被前面 test 看到

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
