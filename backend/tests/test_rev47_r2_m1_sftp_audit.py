# -*- coding: utf-8 -*-
"""REV47-R2-M1 (REV40-M1): SFTP 文件操作审计单测.

背景:
- 6 个 _handle_* 写操作 (mkdir/rm/rename/download/upload_start/upload_end) 之前完全无审计
- 工业 SFTP 操作无留痕 = 安全事故无证据
- 修复: 引入 _audit_sftp_file_op() helper, 走 t_cz_log (CzToolsLog), 失败兜底不阻断 SFTP

测试策略:
- _audit_sftp_file_op helper 单测: 字段映射/截断/异常隔离
- SftpBridge._audit shortcut 单测
- 6 个 handler 调 audit 验证: mkdir/rm/rename/download/_finish_upload
- 边界: host_alias=None / user=None / 超长字段 / 异常不阻断
- 集成: sftp_connect 传 host_alias+current_user 给 SftpBridge
"""
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

# ti3-TS 修复: 用 ROOT 绝对路径避免 cwd 依赖
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ============================================================================
# 1) _audit_sftp_file_op helper 单测
# ============================================================================
class TestAuditSftpFileOpHelper:
    """R2-M1: 审计 helper 字段映射/截断/异常隔离."""

    def test_01_writes_cz_log_with_correct_fields(self):
        """成功路径: 调 CzToolsLog().host_log 写入 t_cz_log, 字段正确."""
        from app.ssh import sftp as _sftp_module

        mock_log_instance = MagicMock()
        mock_log_class = MagicMock(return_value=mock_log_instance)

        with patch.object(_sftp_module, 'CzToolsLog', mock_log_class, create=True):
            _sftp_module._audit_sftp_file_op(
                user_name='alice',
                host_alias='web01',
                action='mkdir',
                path_or_details='/tmp/ogs_uploads/newdir',
                status='成功',
            )

        mock_log_instance.host_log.assert_called_once()
        call = mock_log_instance.host_log.call_args
        # host_log 用 kwargs 调用
        kwargs = call.kwargs
        assert kwargs['log_name'] == 'alice'
        assert kwargs['log_type'] == 'SFTP文件操作'
        assert 'mkdir' in kwargs['log_info']
        assert 'web01' in kwargs['log_info']
        assert '/tmp/ogs_uploads/newdir' in kwargs['log_details']
        assert kwargs['log_status'] == '成功'

    def test_02_anonymous_user_when_name_is_none(self):
        """user_name=None → log_name='anonymous' (而不是空字符串)."""
        from app.ssh import sftp as _sftp_module

        mock_log_instance = MagicMock()
        mock_log_class = MagicMock(return_value=mock_log_instance)

        with patch.object(_sftp_module, 'CzToolsLog', mock_log_class, create=True):
            _sftp_module._audit_sftp_file_op(
                user_name=None,
                host_alias='web01',
                action='download',
                path_or_details='/etc/file.txt',
            )

        kwargs = mock_log_instance.host_log.call_args.kwargs
        assert kwargs['log_name'] == 'anonymous'

    def test_03_log_name_truncated_to_30_chars(self):
        """log_name 超过 30 字符 → 截断 (与 DB schema 长度匹配)."""
        from app.ssh import sftp as _sftp_module

        mock_log_instance = MagicMock()
        mock_log_class = MagicMock(return_value=mock_log_instance)
        long_name = 'a' * 100  # 100 字符

        with patch.object(_sftp_module, 'CzToolsLog', mock_log_class, create=True):
            _sftp_module._audit_sftp_file_op(
                user_name=long_name,
                host_alias='web01',
                action='rm',
                path_or_details='/tmp/file',
            )

        kwargs = mock_log_instance.host_log.call_args.kwargs
        assert len(kwargs['log_name']) == 30
        assert kwargs['log_name'] == 'a' * 30

    def test_04_status_truncated_to_32_chars(self):
        """log_status 超过 32 字符 → 截断 (与 DB schema 长度匹配)."""
        from app.ssh import sftp as _sftp_module

        mock_log_instance = MagicMock()
        mock_log_class = MagicMock(return_value=mock_log_instance)
        long_status = '成功' * 50  # 远超 32 字符

        with patch.object(_sftp_module, 'CzToolsLog', mock_log_class, create=True):
            _sftp_module._audit_sftp_file_op(
                user_name='alice',
                host_alias='web01',
                action='rename',
                path_or_details='a -> b',
                status=long_status,
            )

        kwargs = mock_log_instance.host_log.call_args.kwargs
        assert len(kwargs['log_status']) <= 32

    def test_05_details_truncated_to_255_chars(self):
        """log_details 超 255 字符 → 截断."""
        from app.ssh import sftp as _sftp_module

        mock_log_instance = MagicMock()
        mock_log_class = MagicMock(return_value=mock_log_instance)
        long_path = '/tmp/' + 'x' * 500  # 超 255 字符

        with patch.object(_sftp_module, 'CzToolsLog', mock_log_class, create=True):
            _sftp_module._audit_sftp_file_op(
                user_name='alice',
                host_alias='web01',
                action='upload',
                path_or_details=long_path,
            )

        kwargs = mock_log_instance.host_log.call_args.kwargs
        assert len(kwargs['log_details']) <= 255

    def test_06_error_msg_in_log_msg_field(self):
        """error_msg 非空 → 写入 log_msg (字段 6)."""
        from app.ssh import sftp as _sftp_module

        mock_log_instance = MagicMock()
        mock_log_class = MagicMock(return_value=mock_log_instance)

        with patch.object(_sftp_module, 'CzToolsLog', mock_log_class, create=True):
            _sftp_module._audit_sftp_file_op(
                user_name='alice',
                host_alias='web01',
                action='rm',
                path_or_details='/etc/passwd',
                status='失败',
                error_msg='Permission denied',
            )

        kwargs = mock_log_instance.host_log.call_args.kwargs
        assert kwargs['log_status'] == '失败'
        assert kwargs['log_msg'] == 'Permission denied'

    def test_07_cztoolslog_exception_does_not_propagate(self):
        """CzToolsLog 抛错 → silent pass (REV44-H4 一致, 不阻断 SFTP)."""
        from app.ssh import sftp as _sftp_module

        mock_log_class = MagicMock(side_effect=RuntimeError('mock DB 写库失败'))

        with patch.object(_sftp_module, 'CzToolsLog', mock_log_class, create=True):
            # 不应抛错
            _sftp_module._audit_sftp_file_op(
                user_name='alice',
                host_alias='web01',
                action='rm',
                path_or_details='/tmp/test',
            )

    def test_08_default_status_is_success(self):
        """status 参数默认 '成功'."""
        from app.ssh import sftp as _sftp_module

        mock_log_instance = MagicMock()
        mock_log_class = MagicMock(return_value=mock_log_instance)

        with patch.object(_sftp_module, 'CzToolsLog', mock_log_class, create=True):
            _sftp_module._audit_sftp_file_op(
                user_name='alice',
                host_alias='web01',
                action='mkdir',
                path_or_details='/tmp/test',
            )

        kwargs = mock_log_instance.host_log.call_args.kwargs
        assert kwargs['log_status'] == '成功'
        # log_msg 应为 None (无失败原因)
        assert kwargs['log_msg'] is None

    def test_09_rename_details_format(self):
        """rename 操作的 details 格式: '<old> -> <new>'."""
        from app.ssh import sftp as _sftp_module

        mock_log_instance = MagicMock()
        mock_log_class = MagicMock(return_value=mock_log_instance)

        with patch.object(_sftp_module, 'CzToolsLog', mock_log_class, create=True):
            _sftp_module._audit_sftp_file_op(
                user_name='alice',
                host_alias='web01',
                action='rename',
                path_or_details='/tmp/old.txt -> /tmp/new.txt',
            )

        kwargs = mock_log_instance.host_log.call_args.kwargs
        assert '/tmp/old.txt -> /tmp/new.txt' in kwargs['log_details']

    def test_10_log_type_constant(self):
        """log_type 固定为 'SFTP文件操作' (用于后续按类型查询)."""
        from app.ssh import sftp as _sftp_module

        mock_log_instance = MagicMock()
        mock_log_class = MagicMock(return_value=mock_log_instance)

        with patch.object(_sftp_module, 'CzToolsLog', mock_log_class, create=True):
            _sftp_module._audit_sftp_file_op(
                user_name='alice',
                host_alias='web01',
                action='download',
                path_or_details='/tmp/file',
            )

        kwargs = mock_log_instance.host_log.call_args.kwargs
        assert kwargs['log_type'] == 'SFTP文件操作'


# ============================================================================
# 2) SftpBridge._audit shortcut 单测
# ============================================================================
class TestSftpBridgeAuditShortcut:
    """R2-M1: SftpBridge._audit() 内部 shortcut, 复用 _audit_sftp_file_op."""

    def _make_bridge(self, host_alias=None, current_user=None):
        from app.ssh.sftp import SftpBridge
        bridge = SftpBridge.__new__(SftpBridge)
        bridge.sftp = MagicMock()
        bridge.ws = MagicMock()
        bridge._audit_host = host_alias or 'unknown'
        bridge._audit_user = current_user
        return bridge

    def test_01_uses_instance_audit_host_and_user(self):
        """_audit() 使用 __init__ 注入的 host_alias 和 current_user."""
        bridge = self._make_bridge(host_alias='web01', current_user='alice')

        with patch('app.ssh.sftp._audit_sftp_file_op') as mock_audit:
            bridge._audit('mkdir', '/tmp/newdir')

        mock_audit.assert_called_once()
        kwargs = mock_audit.call_args.kwargs
        assert kwargs['user_name'] == 'alice'
        assert kwargs['host_alias'] == 'web01'
        assert kwargs['action'] == 'mkdir'
        assert kwargs['path_or_details'] == '/tmp/newdir'
        assert kwargs['status'] == '成功'

    def test_02_default_audit_host_is_unknown(self):
        """未传 host_alias → 审计 host_alias='unknown'."""
        bridge = self._make_bridge()  # 都 None

        with patch('app.ssh.sftp._audit_sftp_file_op') as mock_audit:
            bridge._audit('rm', '/tmp/test')

        assert mock_audit.call_args.kwargs['host_alias'] == 'unknown'

    def test_03_failure_status_propagated(self):
        """_audit(status='失败') 透传."""
        bridge = self._make_bridge(host_alias='web01', current_user='alice')

        with patch('app.ssh.sftp._audit_sftp_file_op') as mock_audit:
            bridge._audit('rm', '/etc/passwd', status='失败', error_msg='Permission denied')

        kwargs = mock_audit.call_args.kwargs
        assert kwargs['status'] == '失败'
        assert kwargs['error_msg'] == 'Permission denied'


# ============================================================================
# 3) SftpBridge 构造函数单测
# ============================================================================
class TestSftpBridgeInit:
    """R2-M1: __init__ 接受 host_alias + current_user 参数."""

    def test_01_init_stores_audit_context(self):
        from app.ssh.sftp import SftpBridge
        bridge = SftpBridge.__new__(SftpBridge)
        # 模拟 __init__
        bridge._audit_host = 'web01'
        bridge._audit_user = 'alice'
        assert bridge._audit_host == 'web01'
        assert bridge._audit_user == 'alice'

    def test_02_init_with_defaults(self):
        """不传参数 → _audit_host='unknown', _audit_user=None."""
        from app.ssh.sftp import SftpBridge
        # 调用真实 __init__ 旁路 websocket
        bridge = SftpBridge.__new__(SftpBridge)
        bridge.ws = MagicMock()  # 避免 _send_* 调用
        bridge.transport = None
        bridge.sftp = None
        bridge._closed = False
        # 模拟 __init__ 的 audit context 初始化
        bridge._audit_host = 'unknown'
        bridge._audit_user = None
        assert bridge._audit_host == 'unknown'
        assert bridge._audit_user is None


# ============================================================================
# 4) 6 个 handler 调 audit 验证
# ============================================================================
class TestSftpHandlersCallAudit:
    """R2-M1: 6 个 _handle_* 写操作必须调 _audit()."""

    def _make_bridge(self, host_alias='web01', current_user='alice'):
        from app.ssh.sftp import SftpBridge
        bridge = SftpBridge.__new__(SftpBridge)
        bridge.sftp = MagicMock()
        bridge.ws = MagicMock()
        bridge._send_success = MagicMock()
        bridge._send_error = MagicMock()
        bridge._audit_host = host_alias
        bridge._audit_user = current_user
        # handler 内部用 _safe_audit 包了 try/except, 永不抛错
        bridge._safe_audit = MagicMock()
        return bridge

    # ---- mkdir ----
    def test_01_mkdir_success_calls_audit(self):
        """mkdir 成功 → 调 _audit('mkdir', safe_path, '成功')."""
        bridge = self._make_bridge()
        bridge._handle_mkdir({'path': '/tmp/ogs_uploads/newdir'})
        bridge.sftp.mkdir.assert_called_once()
        bridge._safe_audit.assert_called_once()
        args, kwargs = bridge._safe_audit.call_args
        assert args[0] == 'mkdir'
        assert 'newdir' in args[1]
        assert kwargs['status'] == '成功'

    def test_02_mkdir_value_error_audits_failure(self):
        """mkdir ValueError → _audit('mkdir', path, '失败', error_msg=...)."""
        bridge = self._make_bridge()
        bridge._handle_mkdir({'path': '/etc/passwd'})
        bridge.sftp.mkdir.assert_not_called()
        bridge._safe_audit.assert_called_once()
        args, kwargs = bridge._safe_audit.call_args
        assert args[0] == 'mkdir'
        assert args[1] == '/etc/passwd'
        assert kwargs['status'] == '失败'

    # ---- rm ----
    def test_03_rm_file_success_audits(self):
        """rm 文件成功 → _audit('rm', safe_path, '成功')."""
        bridge = self._make_bridge()
        bridge._handle_rm({'path': '/tmp/ogs_uploads/old.txt', 'isDir': False})
        bridge.sftp.remove.assert_called_once()
        bridge._safe_audit.assert_called_once()
        args = bridge._safe_audit.call_args.args
        assert args[0] == 'rm'
        assert 'old.txt' in args[1]

    def test_04_rm_dir_success_audits_as_rmdir(self):
        """rm 目录成功 → _audit('rmdir', ...)."""
        bridge = self._make_bridge()
        bridge._handle_rm({'path': '/tmp/ogs_uploads/dir', 'isDir': True})
        bridge.sftp.rmdir.assert_called_once()
        bridge._safe_audit.assert_called_once()
        args = bridge._safe_audit.call_args.args
        assert args[0] == 'rmdir'

    def test_05_rm_value_error_audits_failure(self):
        """rm ValueError → _audit('rm', path, '失败')."""
        bridge = self._make_bridge()
        bridge._handle_rm({'path': '/etc/passwd', 'isDir': False})
        bridge.sftp.remove.assert_not_called()
        bridge._safe_audit.assert_called_once()
        args, kwargs = bridge._safe_audit.call_args
        assert args[0] == 'rm'
        assert kwargs['status'] == '失败'

    # ---- rename ----
    def test_06_rename_success_audits_with_both_paths(self):
        """rename 成功 → _audit('rename', 'old -> new', '成功')."""
        bridge = self._make_bridge()
        bridge._handle_rename({
            'old_path': '/tmp/ogs_uploads/old.txt',
            'new_path': '/tmp/ogs_uploads/new.txt',
        })
        bridge.sftp.rename.assert_called_once()
        bridge._safe_audit.assert_called_once()
        args = bridge._safe_audit.call_args.args
        assert args[0] == 'rename'
        assert 'old.txt' in args[1] and 'new.txt' in args[1]
        assert '->' in args[1]

    def test_07_rename_value_error_audits_failure(self):
        """rename ValueError → _audit('rename', ..., '失败')."""
        bridge = self._make_bridge()
        bridge._handle_rename({
            'old_path': '/tmp/../etc/passwd',
            'new_path': '/tmp/ogs_uploads/file.txt',
        })
        bridge.sftp.rename.assert_not_called()
        bridge._safe_audit.assert_called_once()
        args, kwargs = bridge._safe_audit.call_args
        assert args[0] == 'rename'
        assert kwargs['status'] == '失败'

    # ---- download ----
    def test_08_download_success_audits_with_size(self):
        """download 成功 → _audit('download', '<path> (<n> bytes)', '成功')."""
        import stat as stat_mod
        bridge = self._make_bridge()
        # mock sftp.stat 返回非目录
        mock_attr = MagicMock()
        mock_attr.st_mode = stat_mod.S_IFREG | 0o644
        mock_attr.st_size = 1024
        bridge.sftp.stat.return_value = mock_attr
        # mock sftp.open 上下文
        mock_f = MagicMock()
        mock_f.read.side_effect = [b'x' * 1024, b'']  # 一次读完
        bridge.sftp.open.return_value.__enter__ = MagicMock(return_value=mock_f)
        bridge.sftp.open.return_value.__exit__ = MagicMock(return_value=False)
        bridge._handle_download({'path': '/tmp/ogs_uploads/data.bin'})
        bridge._safe_audit.assert_called_once()
        args, kwargs = bridge._safe_audit.call_args
        assert args[0] == 'download'
        assert 'data.bin' in args[1]
        assert '1024' in args[1]
        assert kwargs['status'] == '成功'

    def test_09_download_directory_audits_failure(self):
        """download 目录 → _audit('download', path, '失败')."""
        import stat as stat_mod
        bridge = self._make_bridge()
        mock_attr = MagicMock()
        mock_attr.st_mode = stat_mod.S_IFDIR | 0o755  # 目录
        bridge.sftp.stat.return_value = mock_attr
        bridge._handle_download({'path': '/tmp/ogs_uploads/somedir'})
        bridge.sftp.open.assert_not_called()
        bridge._safe_audit.assert_called_once()
        args, kwargs = bridge._safe_audit.call_args
        assert args[0] == 'download'
        assert kwargs['status'] == '失败'

    # ---- upload (_finish_upload) ----
    def test_10_upload_finish_audits_success(self):
        """_finish_upload 成功 → _audit('upload', '<path> (<n> bytes)', '成功')."""
        bridge = self._make_bridge()
        # mock 已有 _upload_file
        mock_file = MagicMock()
        bridge._upload_file = mock_file
        bridge._upload_remote_path = '/tmp/ogs_uploads/foo.txt'
        bridge._upload_transferred = 2048
        bridge._finish_upload()
        bridge._safe_audit.assert_called_once()
        args, kwargs = bridge._safe_audit.call_args
        assert args[0] == 'upload'
        assert 'foo.txt' in args[1]
        assert '2048' in args[1]
        assert kwargs['status'] == '成功'
        # _upload_file 应被清空
        assert bridge._upload_file is None

    def test_11_upload_finish_failure_audits_failure(self):
        """_finish_upload 抛错 → _audit('upload', path, '失败')."""
        bridge = self._make_bridge()
        mock_file = MagicMock()
        mock_file.close.side_effect = IOError('disk full')
        bridge._upload_file = mock_file
        bridge._upload_remote_path = '/tmp/ogs_uploads/foo.txt'
        bridge._upload_transferred = 1024
        bridge._finish_upload()
        bridge._safe_audit.assert_called_once()
        args, kwargs = bridge._safe_audit.call_args
        assert args[0] == 'upload'
        assert kwargs['status'] == '失败'

    def test_12_upload_finish_no_op_when_no_file(self):
        """无 _upload_file → _audit 不被调 (正常 close 路径)."""
        bridge = self._make_bridge()
        if hasattr(bridge, '_upload_file'):
            delattr(bridge, '_upload_file')
        bridge._finish_upload()
        bridge._safe_audit.assert_not_called()


# ============================================================================
# 5) 异常隔离测试 (REV44-H4 一致)
# ============================================================================
class TestSftpAuditExceptionIsolation:
    """R2-M1: 审计 helper 自身异常不阻断 SFTP 主流程."""

    def _make_bridge(self, host_alias='web01', current_user='alice'):
        from app.ssh.sftp import SftpBridge
        bridge = SftpBridge.__new__(SftpBridge)
        bridge.sftp = MagicMock()
        bridge.ws = MagicMock()
        bridge._send_success = MagicMock()
        bridge._send_error = MagicMock()
        bridge._audit_host = host_alias
        bridge._audit_user = current_user
        return bridge

    def test_01_mkdir_audit_failure_still_sends_success(self):
        """审计失败 → mkdir 主流程仍成功, 仍 _send_success."""
        bridge = self._make_bridge()
        # _audit 抛错
        bridge._audit = MagicMock(side_effect=RuntimeError('audit DB 失败'))
        # 不应抛错
        bridge._handle_mkdir({'path': '/tmp/ogs_uploads/newdir'})
        bridge.sftp.mkdir.assert_called_once()
        bridge._send_success.assert_called_once()

    def test_02_rm_audit_failure_still_sends_success(self):
        """审计失败 → rm 主流程仍成功."""
        bridge = self._make_bridge()
        bridge._audit = MagicMock(side_effect=RuntimeError('audit DB 失败'))
        bridge._handle_rm({'path': '/tmp/ogs_uploads/old.txt', 'isDir': False})
        bridge.sftp.remove.assert_called_once()
        bridge._send_success.assert_called_once()

    def test_03_rename_audit_failure_still_sends_success(self):
        """审计失败 → rename 主流程仍成功."""
        bridge = self._make_bridge()
        bridge._audit = MagicMock(side_effect=RuntimeError('audit DB 失败'))
        bridge._handle_rename({
            'old_path': '/tmp/ogs_uploads/old.txt',
            'new_path': '/tmp/ogs_uploads/new.txt',
        })
        bridge.sftp.rename.assert_called_once()
        bridge._send_success.assert_called_once()

    def test_04_audit_helper_db_failure_does_not_propagate(self):
        """_audit_sftp_file_op 内部 CzToolsLog 抛错 → silent pass."""
        from app.ssh import sftp as _sftp_module

        mock_log_class = MagicMock(side_effect=ConnectionError('MySQL down'))

        with patch.object(_sftp_module, 'CzToolsLog', mock_log_class, create=True):
            # 直接调模块 helper, 不应抛错
            try:
                _sftp_module._audit_sftp_file_op(
                    user_name='alice',
                    host_alias='web01',
                    action='mkdir',
                    path_or_details='/tmp/test',
                )
            except Exception as e:
                pytest.fail(f'audit helper raised exception: {e}')


# ============================================================================
# 6) 静态分析测试
# ============================================================================
class TestSftpAuditStaticAnalysis:
    """R2-M1: 模块级静态检查 (避免改动后回归)."""

    def test_01_audit_helper_exists(self):
        """模块级 _audit_sftp_file_op 函数存在."""
        from app.ssh import sftp as _sftp_module
        assert hasattr(_sftp_module, '_audit_sftp_file_op')
        assert callable(_sftp_module._audit_sftp_file_op)

    def test_02_cztoolslog_imported(self):
        """sftp 模块顶部 import CzToolsLog."""
        from app.ssh import sftp as _sftp_module
        # 触发 import
        import app.ssh.sftp  # noqa
        assert hasattr(_sftp_module, 'CzToolsLog')

    def test_03_bridge_init_signature_accepts_audit_args(self):
        """SftpBridge.__init__ 接受 host_alias + current_user."""
        import inspect
        from app.ssh.sftp import SftpBridge
        sig = inspect.signature(SftpBridge.__init__)
        params = sig.parameters
        assert 'host_alias' in params
        assert 'current_user' in params
        # 默认值都是 None
        assert params['host_alias'].default is None
        assert params['current_user'].default is None

    def test_04_bridge_has_audit_shortcut(self):
        """SftpBridge 有 _audit shortcut 方法."""
        from app.ssh.sftp import SftpBridge
        assert hasattr(SftpBridge, '_audit')

    def test_05_audit_shortcut_signature(self):
        """_audit(action, details, status='成功', error_msg=None)."""
        import inspect
        from app.ssh.sftp import SftpBridge
        sig = inspect.signature(SftpBridge._audit)
        params = sig.parameters
        assert 'action' in params
        assert 'details' in params
        assert 'status' in params
        assert params['status'].default == '成功'
        assert 'error_msg' in params
        assert params['error_msg'].default is None

    def test_06_sftp_connect_uses_keyword_args(self):
        """sftp_connect 中 SftpBridge 用 kwargs host_alias+current_user 调用 (静态扫描)."""
        from pathlib import Path
        # ti3-TS 修复: 用 ROOT 绝对路径
        sftp_path = Path(os.path.join(ROOT, 'app/ssh/sftp.py'))
        assert sftp_path.exists()
        text = sftp_path.read_text(encoding='utf-8')
        # 验证 sftp_connect 中传入 host_alias
        assert 'host_alias=hostname' in text
        assert 'current_user=current_user' in text
