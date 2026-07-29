# -*- coding: utf-8 -*-
"""
R2-1 (REV46-H19): _check_dangerous_command 误拦截修复

问题: 旧实现用子串匹配, "rm -rf /" 会误拦 "rm -rf /home/xxx"
修复: 改用 regex + 词边界 (\s ; & | 字符串起止)
测试维度:
  1) 误拦截场景 (rm -rf /home/xxx 等合法子路径) 不再被拦
  2) 真危险命令仍被拦
  3) 边界字符场景 (; & | 串联)
  4) 缓存机制
  5) 边界条件 (空命令 / None)
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# 让 backend/app 可导入
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


# =============================================================================
# 1) 误拦截场景: 合法子路径命令不再被拦
# =============================================================================
class TestNoFalsePositive:
    """R2-1: 合法子路径命令应返回 None (放行)"""

    @pytest.fixture(autouse=True)
    def reset_regex_cache(self):
        """每个测试前清缓存, 避免 SSH_DANGEROUS_COMMANDS patch 失效"""
        from app.tools import shellcmd
        shellcmd._DANGEROUS_REGEX_CACHE = None
        yield
        shellcmd._DANGEROUS_REGEX_CACHE = None

    def test_01_rm_rf_home_dir_passes(self):
        """'rm -rf /home/xxx' 不应被拦 (旧版会拦)"""
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS',
                   ['rm -rf /', 'mkfs', 'shutdown']):
            assert _check_dangerous_command('rm -rf /home/xxx') is None

    def test_02_rm_rf_tmp_dir_passes(self):
        """'rm -rf /tmp/build' 不应被拦"""
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS',
                   ['rm -rf /', 'mkfs']):
            assert _check_dangerous_command('rm -rf /tmp/build') is None

    def test_03_rm_rf_var_dir_passes(self):
        """'rm -rf /var/log/app' 不应被拦"""
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS',
                   ['rm -rf /']):
            assert _check_dangerous_command('rm -rf /var/log/app') is None

    def test_04_mkfs_in_path_passes(self):
        """'echo /sbin/mkfs.ext4' 不应被拦 (mkfs 后面跟 .ext4)"""
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', ['mkfs']):
            # mkfs 后面跟 .ext4, . 与 ext4 不在边界字符集
            assert _check_dangerous_command('echo /sbin/mkfs.ext4') is None

    def test_05_shutdown_in_word_passes(self):
        """'echo MyShutdownIsScheduled' 不应被拦 (shutdown 前后是字母)"""
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', ['shutdown']):
            assert _check_dangerous_command('echo MyShutdownIsScheduled') is None

    def test_06_reboot_in_word_passes(self):
        """'echo autoreboot_daemon' 不应被拦"""
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', ['reboot']):
            assert _check_dangerous_command('echo autoreboot_daemon') is None


# =============================================================================
# 2) 真危险命令仍被拦
# =============================================================================
class TestTruePositive:
    """R2-1: 真危险命令必须仍被拦"""

    @pytest.fixture(autouse=True)
    def reset_regex_cache(self):
        from app.tools import shellcmd
        shellcmd._DANGEROUS_REGEX_CACHE = None
        yield
        shellcmd._DANGEROUS_REGEX_CACHE = None

    def test_01_rm_rf_root_blocked(self):
        """'rm -rf /' 必须被拦 (前面是字符串起止, 后面是字符串起止)"""
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', ['rm -rf /']):
            assert _check_dangerous_command('rm -rf /') == 'rm -rf /'

    def test_02_mkfs_command_blocked(self):
        """'mkfs /dev/sda' 必须被拦"""
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', ['mkfs']):
            assert _check_dangerous_command('mkfs /dev/sda') == 'mkfs'

    def test_03_shutdown_blocked(self):
        """'shutdown -h now' 必须被拦 (shutdown 前面是字符串起止)"""
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', ['shutdown']):
            assert _check_dangerous_command('shutdown -h now') == 'shutdown'

    def test_04_reboot_blocked(self):
        """'reboot' 必须被拦"""
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', ['reboot']):
            assert _check_dangerous_command('reboot') == 'reboot'

    def test_05_fork_bomb_blocked(self):
        """':(){:|:&};:' fork 炸弹必须被拦"""
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS',
                   [':(){:|:&};:']):
            assert _check_dangerous_command(':(){:|:&};:') == ':(){:|:&};:'

    def test_06_dd_if_blocked(self):
        """'dd if=/dev/zero of=/dev/sda' 必须被拦"""
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', ['dd if=']):
            assert _check_dangerous_command('dd if=/dev/zero of=/dev/sda') == 'dd if='

    def test_07_chmod_777_blocked(self):
        """'chmod -R 777 /' 必须被拦"""
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS',
                   ['chmod -R 777 /']):
            assert _check_dangerous_command('chmod -R 777 /') == 'chmod -R 777 /'


# =============================================================================
# 3) 边界字符场景
# =============================================================================
class TestBoundaryChars:
    """R2-1: 边界字符 (; & |) 串联命令的拦截判断"""

    @pytest.fixture(autouse=True)
    def reset_regex_cache(self):
        from app.tools import shellcmd
        shellcmd._DANGEROUS_REGEX_CACHE = None
        yield
        shellcmd._DANGEROUS_REGEX_CACHE = None

    def test_01_semicolon_chained_dangerous(self):
        """'ls; rm -rf /' 必须被拦 (; 是边界字符)"""
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', ['rm -rf /']):
            assert _check_dangerous_command('ls; rm -rf /') == 'rm -rf /'

    def test_02_semicolon_chained_safe(self):
        """'ls; rm -rf /home/xxx' 不应被拦 (; 是边界但 /home 不在危险模式)"""
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', ['rm -rf /']):
            assert _check_dangerous_command('ls; rm -rf /home/xxx') is None

    def test_03_pipe_chained_dangerous(self):
        """'cat /etc/passwd | shutdown' 必须被拦 (| 是边界)"""
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', ['shutdown']):
            assert _check_dangerous_command('cat /etc/passwd | shutdown') == 'shutdown'

    def test_04_and_chained_dangerous(self):
        """'cd /tmp && rm -rf /' 必须被拦 (& 是边界)"""
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', ['rm -rf /']):
            assert _check_dangerous_command('cd /tmp && rm -rf /') == 'rm -rf /'

    def test_05_start_of_string_dangerous(self):
        """命令开头就是危险模式必须被拦"""
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', ['reboot']):
            assert _check_dangerous_command('reboot now') == 'reboot'

    def test_06_end_of_string_dangerous(self):
        """命令结尾就是危险模式必须被拦"""
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', ['reboot']):
            assert _check_dangerous_command('sudo reboot') == 'reboot'

    def test_07_with_spaces_around_dangerous(self):
        """危险命令前后有空格必须被拦"""
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', ['reboot']):
            assert _check_dangerous_command('  reboot  ') == 'reboot'


# =============================================================================
# 4) 缓存机制
# =============================================================================
class TestRegexCache:
    """R2-1: 编译缓存避免重复编译"""

    @pytest.fixture(autouse=True)
    def reset_regex_cache(self):
        from app.tools import shellcmd
        shellcmd._DANGEROUS_REGEX_CACHE = None
        yield
        shellcmd._DANGEROUS_REGEX_CACHE = None

    def test_01_cache_hit_returns_same_object(self):
        from app.tools.shellcmd import _get_dangerous_regex
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', ['rm -rf /']):
            r1 = _get_dangerous_regex()
            r2 = _get_dangerous_regex()
            # 同一对象 (缓存命中)
            assert r1 is r2

    def test_02_cache_built_once(self):
        """多次调用只编译一次"""
        from app.tools import shellcmd
        from app.tools.shellcmd import _get_dangerous_regex, _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', ['rm -rf /']):
            _get_dangerous_regex()
            initial_cache = shellcmd._DANGEROUS_REGEX_CACHE
            # 多次调用 check, 缓存不应重建
            _check_dangerous_command('rm -rf /home')
            _check_dangerous_command('rm -rf /tmp')
            assert shellcmd._DANGEROUS_REGEX_CACHE is initial_cache

    def test_03_cache_contains_pattern_and_label(self):
        """缓存项 = (compiled_pattern, label) 元组"""
        from app.tools.shellcmd import _get_dangerous_regex
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS',
                   ['rm -rf /', 'mkfs']):
            cache = _get_dangerous_regex()
            assert len(cache) == 2
            for pattern, label in cache:
                import re as _re
                assert isinstance(pattern, _re.Pattern)
                assert isinstance(label, str)

    def test_04_empty_dangerous_list(self):
        """空 SSH_DANGEROUS_COMMANDS 应返回空缓存"""
        from app.tools.shellcmd import _get_dangerous_regex
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', []):
            assert _get_dangerous_regex() == []

    def test_05_none_dangerous_list(self):
        """SSH_DANGEROUS_COMMANDS=None 应不报错"""
        from app.tools.shellcmd import _get_dangerous_regex
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', None):
            assert _get_dangerous_regex() == []


# =============================================================================
# 5) 边界条件
# =============================================================================
class TestEdgeCases:
    """R2-1: 边界条件"""

    @pytest.fixture(autouse=True)
    def reset_regex_cache(self):
        from app.tools import shellcmd
        shellcmd._DANGEROUS_REGEX_CACHE = None
        yield
        shellcmd._DANGEROUS_REGEX_CACHE = None

    def test_01_none_command(self):
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', ['reboot']):
            assert _check_dangerous_command(None) == 'cmd not a string'

    def test_02_empty_command(self):
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', ['reboot']):
            assert _check_dangerous_command('') is None

    def test_03_whitespace_only_command(self):
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', ['reboot']):
            assert _check_dangerous_command('   \t  ') is None

    def test_04_int_command(self):
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', ['reboot']):
            assert _check_dangerous_command(123) == 'cmd not a string'

    def test_05_special_chars_in_pattern_re_escaped(self):
        """危险命令含 regex 特殊字符应被 re.escape 转义"""
        from app.tools.shellcmd import _check_dangerous_command
        # 含 . * 等 regex 特殊字符的危险命令
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS',
                   ['chmod 777 .*']):
            # "chmod 777 ." 后面跟其他字符, 不应误匹配
            assert _check_dangerous_command('echo chmod 777 .bak') is None
            # 真匹配必须能拦
            assert _check_dangerous_command('chmod 777 .*') == 'chmod 777 .*'

    def test_06_normal_safe_command(self):
        """普通 ls / cat 命令应放行"""
        from app.tools.shellcmd import _check_dangerous_command
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS',
                   ['rm -rf /', 'mkfs', 'shutdown', 'reboot']):
            assert _check_dangerous_command('ls -la /home') is None
            assert _check_dangerous_command('cat /etc/passwd') is None
            assert _check_dangerous_command('echo hello') is None
            assert _check_dangerous_command('cd /opt && ls') is None


# =============================================================================
# 6) 实际 SSH_DANGEROUS_COMMANDS 默认值场景
# =============================================================================
class TestDefaultConfig:
    """R2-1: 默认 .env 中的 SSH_DANGEROUS_COMMANDS 场景"""

    @pytest.fixture(autouse=True)
    def reset_regex_cache(self):
        from app.tools import shellcmd
        shellcmd._DANGEROUS_REGEX_CACHE = None
        yield
        shellcmd._DANGEROUS_REGEX_CACHE = None

    def test_01_default_block_list(self):
        """.env.example 中默认黑名单全部行为正确"""
        from app.tools.shellcmd import _check_dangerous_command
        # .env.example OGS_SSH_DANGEROUS_COMMANDS 默认值
        default_list = (
            'rm -rf /,mkfs,dd if=,shutdown,reboot,'
            'init 0,init 6,halt,poweroff,'
            ':(){:|:&};:,chmod -R 777 /,chown -R'
        ).split(',')
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', default_list):
            # 全部默认危险命令应被拦
            for cmd in [
                'rm -rf /',
                'mkfs /dev/sda',
                'dd if=/dev/zero of=/dev/sda',
                'shutdown -h now',
                'reboot',
                'init 0',
                'halt',
                ':(){:|:&};:',
                'chmod -R 777 /',
            ]:
                result = _check_dangerous_command(cmd)
                assert result is not None, f'{cmd!r} 应被拦'

    def test_02_legitimate_user_commands_pass(self):
        """用户合法命令应放行"""
        from app.tools.shellcmd import _check_dangerous_command
        default_list = (
            'rm -rf /,mkfs,dd if=,shutdown,reboot,'
            'init 0,init 6,halt,poweroff,'
            ':(){:|:&};:,chmod -R 777 /,chown -R'
        ).split(',')
        with patch('app.tools.shellcmd.SSH_DANGEROUS_COMMANDS', default_list):
            # 合法命令
            for cmd in [
                'ls -la',
                'rm -rf /home/user/old',
                'rm -rf /tmp/build',
                'chmod 755 /home/user/file',
                'chown user:user /home/user/file',
                'cat /etc/hostname',
                'systemctl status nginx',
                'ps aux | grep python',
            ]:
                result = _check_dangerous_command(cmd)
                assert result is None, f'{cmd!r} 不应被拦, 实际: {result}'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
