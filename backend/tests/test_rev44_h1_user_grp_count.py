# -*- coding: utf-8 -*-
"""
R2-10 (REV44-H1): user_grp_count 失败不应静默

问题: user_grp_count / host_grp_count 失败只 log.error + return False,
  9 处 caller 全部忽略返回值, 组成员数和实际计数长期不一致.
修复:
  - 加 AuthAutoUpdate.safe_host_grp_count / safe_user_grp_count
  - 失败时 caller 侧再记 WARNING (含 op_label 定位调用方)
  - 异常路径也兜底, 不抛回 caller (向后兼容)
测试维度:
  1) auto_update.py: 安全 wrapper 函数存在
  2) safe_user_grp_count 成功时返 True
  3) safe_user_grp_count 失败时返 False + log WARNING
  4) safe_host_grp_count 成功时返 True
  5) safe_host_grp_count 失败时返 False + log WARNING
  6) 异常路径也 log WARNING 不抛
  7) WARNING 含 op_label
  8) WARNING 含 group 名 (定位哪个组计数失败)
  9) 原 host_grp_count / user_grp_count 行为不变 (向后兼容)
"""
import os
import sys
import logging
import pytest
from unittest.mock import patch, MagicMock

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


# =============================================================================
# 1) 安全 wrapper 函数存在
# =============================================================================
class TestSafeWrappersExist:
    """R2-10: AuthAutoUpdate 提供 safe_* wrapper 函数"""

    def test_01_safe_host_grp_count_exists(self):
        from app.tools.auto_update import AuthAutoUpdate
        assert hasattr(AuthAutoUpdate, 'safe_host_grp_count')
        assert callable(AuthAutoUpdate.safe_host_grp_count)

    def test_02_safe_user_grp_count_exists(self):
        from app.tools.auto_update import AuthAutoUpdate
        assert hasattr(AuthAutoUpdate, 'safe_user_grp_count')
        assert callable(AuthAutoUpdate.safe_user_grp_count)

    def test_03_original_host_grp_count_preserved(self):
        """原 host_grp_count 行为不变 (向后兼容)"""
        from app.tools.auto_update import AuthAutoUpdate
        assert hasattr(AuthAutoUpdate, 'host_grp_count')
        assert callable(AuthAutoUpdate.host_grp_count)

    def test_04_original_user_grp_count_preserved(self):
        """原 user_grp_count 行为不变"""
        from app.tools.auto_update import AuthAutoUpdate
        assert hasattr(AuthAutoUpdate, 'user_grp_count')
        assert callable(AuthAutoUpdate.user_grp_count)

    def test_05_rev44_h1_marker(self):
        """auto_update.py 含 R2-10 / REV44-H1 注释"""
        auto_update = os.path.join(BACKEND, 'app', 'tools', 'auto_update.py')
        with open(auto_update, encoding='utf-8') as f:
            src = f.read()
        assert 'R2-10' in src, "auto_update.py 缺 R2-10 修复标记"
        assert 'REV44-H1' in src, "auto_update.py 缺 REV44-H1 评审引用"


# =============================================================================
# 2) safe_user_grp_count 行为
# =============================================================================
class TestSafeUserGrpCount:
    """R2-10: safe_user_grp_count 成功时返 True"""

    def test_01_success_returns_true(self):
        """原 user_grp_count 成功, safe_ 也返 True"""
        from app.tools.auto_update import AuthAutoUpdate
        with patch.object(AuthAutoUpdate, 'user_grp_count',
                          return_value=True):
            result = AuthAutoUpdate.safe_user_grp_count('admin', op_label='test_op')
            assert result is True

    def test_02_failure_returns_false_and_logs_warning(self, caplog):
        """原 user_grp_count 失败, safe_ 返 False + WARNING"""
        from app.tools.auto_update import AuthAutoUpdate
        with patch.object(AuthAutoUpdate, 'user_grp_count',
                          return_value=False):
            with caplog.at_level(logging.WARNING):
                result = AuthAutoUpdate.safe_user_grp_count('admin',
                                                           op_label='user_register_op')
            assert result is False
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) >= 1
        assert any('R2-10' in r.message for r in warnings)

    def test_03_warning_includes_op_label(self, caplog):
        """WARNING 应含 op_label (定位 caller)"""
        from app.tools.auto_update import AuthAutoUpdate
        with patch.object(AuthAutoUpdate, 'user_grp_count',
                          return_value=False):
            with caplog.at_level(logging.WARNING):
                AuthAutoUpdate.safe_user_grp_count('admin',
                                                   op_label='unique_op_label_xyz')
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert any('unique_op_label_xyz' in r.message for r in warnings)

    def test_04_warning_includes_group_name(self, caplog):
        """WARNING 应含 group 名"""
        from app.tools.auto_update import AuthAutoUpdate
        with patch.object(AuthAutoUpdate, 'user_grp_count',
                          return_value=False):
            with caplog.at_level(logging.WARNING):
                AuthAutoUpdate.safe_user_grp_count('unique_group_name_abc',
                                                   op_label='op')
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert any('unique_group_name_abc' in r.message for r in warnings)


# =============================================================================
# 3) safe_host_grp_count 行为
# =============================================================================
class TestSafeHostGrpCount:
    """R2-10: safe_host_grp_count 镜像 safe_user_grp_count"""

    def test_01_success_returns_true(self):
        from app.tools.auto_update import AuthAutoUpdate
        with patch.object(AuthAutoUpdate, 'host_grp_count',
                          return_value=True):
            result = AuthAutoUpdate.safe_host_grp_count('default',
                                                       op_label='test')
            assert result is True

    def test_02_failure_returns_false_and_logs(self, caplog):
        from app.tools.auto_update import AuthAutoUpdate
        with patch.object(AuthAutoUpdate, 'host_grp_count',
                          return_value=False):
            with caplog.at_level(logging.WARNING):
                result = AuthAutoUpdate.safe_host_grp_count('default',
                                                           op_label='host_add_op')
            assert result is False
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert any('R2-10' in r.message for r in warnings)
        assert any('host_add_op' in r.message for r in warnings)


# =============================================================================
# 4) 异常路径防御
# =============================================================================
class TestExceptionDefense:
    """R2-10: counter 抛异常时, safe_ 不抛回 caller (向后兼容 + log warning)"""

    def test_01_counter_exception_swallowed(self, caplog):
        """原 counter 抛异常, safe_ 捕到 + WARNING + 返回 False"""
        from app.tools.auto_update import AuthAutoUpdate
        with patch.object(AuthAutoUpdate, 'user_grp_count',
                          side_effect=Exception('boom')):
            with caplog.at_level(logging.WARNING):
                result = AuthAutoUpdate.safe_user_grp_count('admin',
                                                           op_label='op')
            # 不应抛回
            assert result is False
        # 必有 WARNING
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert any('R2-10' in r.message for r in warnings)
        # WARNING 含异常描述
        assert any('boom' in r.message for r in warnings)

    def test_02_host_counter_exception_swallowed(self, caplog):
        """host_grp_count 抛异常也不向上抛"""
        from app.tools.auto_update import AuthAutoUpdate
        with patch.object(AuthAutoUpdate, 'host_grp_count',
                          side_effect=Exception('net error')):
            with caplog.at_level(logging.WARNING):
                result = AuthAutoUpdate.safe_host_grp_count('default',
                                                           op_label='op')
            assert result is False
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert any('net error' in r.message for r in warnings)


# =============================================================================
# 5) 默认 op_label
# =============================================================================
class TestDefaultOpLabel:
    """R2-10: op_label 参数默认值"""

    def test_01_default_op_label_present(self, caplog):
        """未传 op_label 时, WARNING 仍存在 (有默认 'host_grp' / 'user_grp')"""
        from app.tools.auto_update import AuthAutoUpdate
        with patch.object(AuthAutoUpdate, 'user_grp_count',
                          return_value=False):
            with caplog.at_level(logging.WARNING):
                AuthAutoUpdate.safe_user_grp_count('admin')
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        # 应至少有 WARNING, 且含 'user_grp' (默认 op_label)
        assert len(warnings) >= 1
        assert any('user_grp' in r.message for r in warnings)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
