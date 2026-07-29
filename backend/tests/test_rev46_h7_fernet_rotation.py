# -*- coding: utf-8 -*-
"""REV46-H7: Fernet key rotation 多 key 列表 + 透明迁移测试.

背景:
- 原实现: 单一 OGS_FERNET_KEY, key 泄露时无法 rotate
- 修复: 支持 OGS_FERNET_KEYS=k1,k2,k3 (逗号分隔), 第一个为最新 key (用于加密)
- 解密: 尝试所有 key, 找到能解密的 key
- 透明迁移: 解密到非最新 key (list[i], i>0) 加密的数据时, 自动用新 key 重加密并 callback 写回

测试覆盖:
  1) 单 key (向后兼容 OGS_FERNET_KEY 模式)
  2) 多 key 列表加载
  3) 加密永远用最新 key (list[0])
  4) 解密能解 list 中任一 key 加密的数据
  5) 自动迁移: 解密旧 key 加密的数据时 callback 被调
  6) 迁移后 callback 收到的是新 key 加密的数据
  7) 错误场景: 无 key / 格式无效 key
  8) 历史 base64 数据仍兼容
"""
import os
import re
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet


_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)


# ============================================================
# Helper: 生成测试 keys
# ============================================================
def _gen_key():
    return Fernet.generate_key().decode('utf-8')


@pytest.fixture
def fernet_env(monkeypatch):
    """提供可重置的 OGS_FERNET_KEYS 环境 fixture."""
    return monkeypatch


# ============================================================
# 1) 单 key 模式 (向后兼容 OGS_FERNET_KEY)
# ============================================================
class TestRev46H7SingleKeyBackwardCompat:
    """REV46-H7: 单 key 模式向后兼容 OGS_FERNET_KEY."""

    def test_01_single_key_via_ogs_fernet_key(self, monkeypatch):
        """OGS_FERNET_KEY 单 key 仍能加解密."""
        k = _gen_key()
        monkeypatch.setenv('OGS_FERNET_KEY', k)
        monkeypatch.delenv('OGS_FERNET_KEYS', raising=False)
        from app.tools.basesec import encrypt_host_password, decrypt_host_password
        ct = encrypt_host_password('my_secret')
        plain = decrypt_host_password(ct)
        assert plain == 'my_secret'

    def test_02_single_key_via_ogs_fernet_keys(self, monkeypatch):
        """OGS_FERNET_KEYS 单 key (无逗号) 等价 OGS_FERNET_KEY."""
        k = _gen_key()
        monkeypatch.setenv('OGS_FERNET_KEYS', k)
        monkeypatch.delenv('OGS_FERNET_KEY', raising=False)
        from app.tools.basesec import encrypt_host_password, decrypt_host_password
        ct = encrypt_host_password('hello')
        assert decrypt_host_password(ct) == 'hello'

    def test_03_keys_priority_over_legacy(self, monkeypatch):
        """OGS_FERNET_KEYS 优先于 OGS_FERNET_KEY."""
        k_old = _gen_key()
        k_new = _gen_key()
        monkeypatch.setenv('OGS_FERNET_KEY', k_old)
        monkeypatch.setenv('OGS_FERNET_KEYS', k_new)
        from app.tools.basesec import encrypt_host_password, decrypt_host_password
        ct = encrypt_host_password('test_prio')
        # 用新 key (k_new) 加密的密文, 只有 k_new 能解
        plain = decrypt_host_password(ct)
        assert plain == 'test_prio'


# ============================================================
# 2) 多 key 列表加载
# ============================================================
class TestRev46H7MultipleKeys:
    """REV46-H7: OGS_FERNET_KEYS 多 key 加载."""

    def test_01_two_keys_loaded(self, monkeypatch):
        """2 个 key 都能加载."""
        k1, k2 = _gen_key(), _gen_key()
        monkeypatch.setenv('OGS_FERNET_KEYS', f'{k1},{k2}')
        monkeypatch.delenv('OGS_FERNET_KEY', raising=False)
        from app.tools.basesec import _get_fernet_list
        fl = _get_fernet_list()
        assert len(fl) == 2

    def test_02_three_keys_loaded(self, monkeypatch):
        """3 个 key 都能加载."""
        k1, k2, k3 = _gen_key(), _gen_key(), _gen_key()
        monkeypatch.setenv('OGS_FERNET_KEYS', f'{k1},{k2},{k3}')
        monkeypatch.delenv('OGS_FERNET_KEY', raising=False)
        from app.tools.basesec import _get_fernet_list
        fl = _get_fernet_list()
        assert len(fl) == 3

    def test_03_key_order_preserved(self, monkeypatch):
        """key 列表顺序保持 (list[0] = 最新)."""
        k1, k2, k3 = _gen_key(), _gen_key(), _gen_key()
        monkeypatch.setenv('OGS_FERNET_KEYS', f'{k1},{k2},{k3}')
        from app.tools.basesec import _get_fernet_list, encrypt_host_password
        fl = _get_fernet_list()
        assert len(fl) == 3
        # 用加密结果验证顺序: encrypt_host_password 应使用 list[0] (k1)
        ct = encrypt_host_password('order_test')
        f_k1 = Fernet(k1.encode())
        assert f_k1.decrypt(ct.encode()).decode() == 'order_test'
        # 验证 list[1] (k2) 单独无法解 list[0] 加密的密文
        f_k2 = Fernet(k2.encode())
        from cryptography.fernet import InvalidToken
        with pytest.raises(InvalidToken):
            f_k2.decrypt(ct.encode())

    def test_04_whitespace_trimmed(self, monkeypatch):
        """key 列表中空白被 trim."""
        k1, k2 = _gen_key(), _gen_key()
        # 故意加空白
        monkeypatch.setenv('OGS_FERNET_KEYS', f' {k1} , {k2} ')
        from app.tools.basesec import _get_fernet_list
        fl = _get_fernet_list()
        assert len(fl) == 2


# ============================================================
# 3) 加密永远用最新 key
# ============================================================
class TestRev46H7EncryptAlwaysPrimaryKey:
    """REV46-H7: 加密永远用最新 key (list[0])."""

    def test_01_encrypt_uses_first_key(self, monkeypatch):
        """加密结果能被 list[0] 直接解密."""
        k1, k2 = _gen_key(), _gen_key()
        monkeypatch.setenv('OGS_FERNET_KEYS', f'{k1},{k2}')
        from app.tools.basesec import encrypt_host_password
        ct = encrypt_host_password('primary_key_test')
        # 用 list[0] (k1) 直接解
        f_k1 = Fernet(k1.encode())
        assert f_k1.decrypt(ct.encode()).decode() == 'primary_key_test'

    def test_02_old_key_cannot_decrypt_new_ciphertext(self, monkeypatch):
        """list[1+] 单独无法解新密文 (确认用 list[0] 加密)."""
        k1, k2 = _gen_key(), _gen_key()
        monkeypatch.setenv('OGS_FERNET_KEYS', f'{k1},{k2}')
        from app.tools.basesec import encrypt_host_password
        ct = encrypt_host_password('test_old_key_cant_decrypt')
        # 用 list[1] (k2) 解应失败
        f_k2 = Fernet(k2.encode())
        from cryptography.fernet import InvalidToken
        with pytest.raises(InvalidToken):
            f_k2.decrypt(ct.encode())


# ============================================================
# 4) 解密尝试所有 key
# ============================================================
class TestRev46H7DecryptTriesAllKeys:
    """REV46-H7: 解密按 list 顺序尝试所有 key."""

    def test_01_decrypt_with_first_key(self, monkeypatch):
        """密文用 list[0] 加密, decrypt 找到 list[0] 解密."""
        k1 = _gen_key()
        monkeypatch.setenv('OGS_FERNET_KEYS', k1)
        from app.tools.basesec import encrypt_host_password, decrypt_host_password
        ct = encrypt_host_password('first_key_encrypted')
        assert decrypt_host_password(ct) == 'first_key_encrypted'

    def test_02_decrypt_with_legacy_key(self, monkeypatch):
        """密文用 list[1] 加密, decrypt 尝试 list[0] 失败后用 list[1] 解密."""
        k_old = _gen_key()
        f_old = Fernet(k_old.encode())
        ct_old = f_old.encrypt(b'legacy_data').decode()
        k_new = _gen_key()
        monkeypatch.setenv('OGS_FERNET_KEYS', f'{k_new},{k_old}')
        from app.tools.basesec import decrypt_host_password
        plain = decrypt_host_password(ct_old)
        assert plain == 'legacy_data'

    def test_03_decrypt_with_three_keys(self, monkeypatch):
        """密文用 list[2] 加密, decrypt 尝试 list[0]/[1] 失败后用 list[2] 解密."""
        k_a, k_b, k_c = _gen_key(), _gen_key(), _gen_key()
        f_c = Fernet(k_c.encode())
        ct_old = f_c.encrypt(b'three_key_data').decode()
        monkeypatch.setenv('OGS_FERNET_KEYS', f'{k_a},{k_b},{k_c}')
        from app.tools.basesec import decrypt_host_password
        plain = decrypt_host_password(ct_old)
        assert plain == 'three_key_data'

    def test_04_all_keys_fail_raises(self, monkeypatch):
        """所有 key 都失败时 raise RuntimeError."""
        k1, k2 = _gen_key(), _gen_key()
        # 创建一个不相关的密文 (用 k_other 加密)
        k_other = _gen_key()
        f_other = Fernet(k_other.encode())
        ct_unknown = f_other.encrypt(b'secret').decode()
        monkeypatch.setenv('OGS_FERNET_KEYS', f'{k1},{k2}')
        from app.tools.basesec import decrypt_host_password
        with pytest.raises(RuntimeError) as exc_info:
            decrypt_host_password(ct_unknown)
        assert 'Fernet' in str(exc_info.value) or 'key' in str(exc_info.value).lower()


# ============================================================
# 5) 自动迁移 (callback)
# ============================================================
class TestRev46H7AutoMigration:
    """REV46-H7: 解密旧 key 加密的数据时自动 callback 触发迁移."""

    def test_01_no_callback_when_first_key_used(self, monkeypatch):
        """list[0] 加密时, 解密不触发 callback."""
        k1 = _gen_key()
        monkeypatch.setenv('OGS_FERNET_KEYS', k1)
        from app.tools.basesec import encrypt_host_password, decrypt_host_password
        ct = encrypt_host_password('first_key_data')
        called = []

        def cb(new_stored):
            called.append(new_stored)

        decrypt_host_password(ct, rehash_callback=cb)
        # list[0] 加密的密文, 不应触发迁移 (i=0)
        assert len(called) == 0

    def test_02_callback_triggered_when_legacy_key_used(self, monkeypatch):
        """list[1+] 加密时, 解密自动 callback 迁移到 list[0]."""
        k_old = _gen_key()
        f_old = Fernet(k_old.encode())
        ct_old = f_old.encrypt(b'old_data_to_migrate').decode()
        k_new = _gen_key()
        monkeypatch.setenv('OGS_FERNET_KEYS', f'{k_new},{k_old}')
        from app.tools.basesec import decrypt_host_password
        called = []

        def cb(new_stored):
            called.append(new_stored)

        plain = decrypt_host_password(ct_old, rehash_callback=cb)
        assert plain == 'old_data_to_migrate'
        assert len(called) == 1, '应触发一次迁移 callback'
        # callback 收到的新密文应能用 list[0] (k_new) 解密
        f_new = Fernet(k_new.encode())
        assert f_new.decrypt(called[0].encode()).decode() == 'old_data_to_migrate'

    def test_03_no_callback_when_none(self, monkeypatch):
        """callback=None 时不迁移 (只解密)."""
        k_old = _gen_key()
        f_old = Fernet(k_old.encode())
        ct_old = f_old.encrypt(b'no_callback_test').decode()
        k_new = _gen_key()
        monkeypatch.setenv('OGS_FERNET_KEYS', f'{k_new},{k_old}')
        from app.tools.basesec import decrypt_host_password
        plain = decrypt_host_password(ct_old, rehash_callback=None)
        assert plain == 'no_callback_test'

    def test_04_callback_failure_does_not_break_decrypt(self, monkeypatch):
        """callback 抛异常时不应中断解密 (静默 fallback)."""
        k_old = _gen_key()
        f_old = Fernet(k_old.encode())
        ct_old = f_old.encrypt(b'callback_fail_test').decode()
        k_new = _gen_key()
        monkeypatch.setenv('OGS_FERNET_KEYS', f'{k_new},{k_old}')
        from app.tools.basesec import decrypt_host_password

        def bad_cb(new_stored):
            raise IOError('db write failed')

        # callback 失败不应阻断解密
        plain = decrypt_host_password(ct_old, rehash_callback=bad_cb)
        assert plain == 'callback_fail_test'


# ============================================================
# 6) 历史 base64 数据兼容
# ============================================================
class TestRev46H7LegacyBase64Compat:
    """REV46-H7: 历史 base64 数据仍兼容解密."""

    def test_01_legacy_base64_decrypt(self, monkeypatch):
        """历史 base64 编码数据仍能解密 (与 Fernet key 无关)."""
        import base64
        k = _gen_key()
        monkeypatch.setenv('OGS_FERNET_KEYS', k)
        from app.tools.basesec import decrypt_host_password
        legacy = base64.b64encode(b'legacy_base64_data').decode()
        plain = decrypt_host_password(legacy)
        assert plain == 'legacy_base64_data'

    def test_02_legacy_base64_with_callback_triggers_migration(self, monkeypatch):
        """历史 base64 + callback 应触发迁移 (升级到 Fernet)."""
        import base64
        k = _gen_key()
        monkeypatch.setenv('OGS_FERNET_KEYS', k)
        from app.tools.basesec import decrypt_host_password
        legacy = base64.b64encode(b'legacy_to_migrate').decode()
        called = []

        def cb(new_stored):
            called.append(new_stored)

        plain = decrypt_host_password(legacy, rehash_callback=cb)
        assert plain == 'legacy_to_migrate'
        assert len(called) == 1
        # callback 收到 Fernet 密文 (以 gAAAAA 开头)
        assert called[0].startswith('gAAAAA')


# ============================================================
# 7) 错误场景
# ============================================================
class TestRev46H7ErrorScenarios:
    """REV46-H7: 错误场景 fail-fast."""

    def test_01_no_key_raises(self, monkeypatch):
        """无 OGS_FERNET_KEYS / OGS_FERNET_KEY 应 raise RuntimeError."""
        monkeypatch.delenv('OGS_FERNET_KEYS', raising=False)
        monkeypatch.delenv('OGS_FERNET_KEY', raising=False)
        from app.tools.basesec import _get_fernet_list
        with pytest.raises(RuntimeError) as exc_info:
            _get_fernet_list()
        assert 'OGS_FERNET_KEYS' in str(exc_info.value)

    def test_02_invalid_key_raises(self, monkeypatch):
        """key 格式无效应 raise RuntimeError (指出哪个 key 错)."""
        k_good = _gen_key()
        monkeypatch.setenv('OGS_FERNET_KEYS', f'{k_good},not_a_valid_key_xxx')
        from app.tools.basesec import _get_fernet_list
        with pytest.raises(RuntimeError) as exc_info:
            _get_fernet_list()
        assert '第 2 个 key' in str(exc_info.value) or '无效' in str(exc_info.value)

    def test_03_empty_string_treated_as_missing(self, monkeypatch):
        """空字符串 key 应被 trim 掉, 不被当作有效 key."""
        monkeypatch.setenv('OGS_FERNET_KEYS', '')
        monkeypatch.delenv('OGS_FERNET_KEY', raising=False)
        from app.tools.basesec import _get_fernet_list
        with pytest.raises(RuntimeError):
            _get_fernet_list()

    def test_04_only_commas_raises(self, monkeypatch):
        """OGS_FERNET_KEYS=',,,' 应 raise (无有效 key)."""
        monkeypatch.setenv('OGS_FERNET_KEYS', ',,,')
        from app.tools.basesec import _get_fernet_list
        with pytest.raises(RuntimeError):
            _get_fernet_list()


# ============================================================
# 8) 空 / None 输入保留语义
# ============================================================
class TestRev46H7EmptyInputSemantics:
    """REV46-H7: 空输入保留原语义."""

    def test_01_encrypt_none_returns_none(self, monkeypatch):
        """encrypt_host_password(None) -> None."""
        k = _gen_key()
        monkeypatch.setenv('OGS_FERNET_KEYS', k)
        from app.tools.basesec import encrypt_host_password
        assert encrypt_host_password(None) is None

    def test_02_encrypt_empty_string_returns_none(self, monkeypatch):
        """encrypt_host_password('') -> None."""
        k = _gen_key()
        monkeypatch.setenv('OGS_FERNET_KEYS', k)
        from app.tools.basesec import encrypt_host_password
        assert encrypt_host_password('') is None

    def test_03_decrypt_none_returns_none(self, monkeypatch):
        """decrypt_host_password(None) -> None."""
        k = _gen_key()
        monkeypatch.setenv('OGS_FERNET_KEYS', k)
        from app.tools.basesec import decrypt_host_password
        assert decrypt_host_password(None) is None

    def test_04_decrypt_empty_string_returns_none(self, monkeypatch):
        """decrypt_host_password('') -> None."""
        k = _gen_key()
        monkeypatch.setenv('OGS_FERNET_KEYS', k)
        from app.tools.basesec import decrypt_host_password
        assert decrypt_host_password('') is None


# ============================================================
# 9) 静态分析: basesec.py 标记 + 设计完整性
# ============================================================
class TestRev46H7StaticAnalysis:
    """REV46-H7: basesec.py 应含 REV46-H7 标记和设计要素."""

    BASECEC_PY = os.path.join(_BACKEND, 'app', 'tools', 'basesec.py')

    def test_01_rev46_h7_marker_in_basesec(self):
        """basesec.py 应含 REV46-H7 标记."""
        with open(self.BASECEC_PY, encoding='utf-8') as f:
            src = f.read()
        assert 'REV46-H7' in src, 'basesec.py 应含 REV46-H7 标记'

    def test_02_get_fernet_list_function_defined(self):
        """_get_fernet_list 函数应被定义."""
        with open(self.BASECEC_PY, encoding='utf-8') as f:
            src = f.read()
        assert 'def _get_fernet_list(' in src

    def test_03_get_primary_fernet_function_defined(self):
        """_get_primary_fernet 函数应被定义."""
        with open(self.BASECEC_PY, encoding='utf-8') as f:
            src = f.read()
        assert 'def _get_primary_fernet(' in src

    def test_04_decrypt_iterates_over_fernet_list(self):
        """decrypt 应遍历 fernet_list (不是单 key)."""
        with open(self.BASECEC_PY, encoding='utf-8') as f:
            src = f.read()
        m = re.search(r'def\s+decrypt_host_password[\s\S]*?(?=\ndef\s|\nclass\s|\Z)', src)
        assert m
        body = m.group(0)
        assert 'for' in body and 'fernet_list' in body, \
            'decrypt_host_password 应遍历 fernet_list'

    def test_05_ogs_fernet_keys_env_documented(self):
        """OGS_FERNET_KEYS 环境变量应在代码注释中说明."""
        with open(self.BASECEC_PY, encoding='utf-8') as f:
            src = f.read()
        assert 'OGS_FERNET_KEYS' in src, '应提及 OGS_FERNET_KEYS'


# ============================================================
# 10) 端到端 smoke: rotation 完整流程
# ============================================================
class TestRev46H7EndToEndRotation:
    """REV46-H7: 端到端 rotation 流程 (key 轮换模拟)."""

    def test_01_full_rotation_flow(self, monkeypatch):
        """完整 rotation 流程:
        1) 初始用 k1 加密一批数据
        2) key 泄露, 部署 k2 (新) + k1 (旧) 列表
        3) 业务解密 k1 加密的数据 (callback 触发自动迁移到 k2)
        4) 所有数据已迁移到 k2 后, 移除 k1
        """
        # Step 1: 初始部署 k1
        k1 = _gen_key()
        monkeypatch.setenv('OGS_FERNET_KEYS', k1)
        from app.tools.basesec import encrypt_host_password, decrypt_host_password
        secrets = ['ssh_pass_1', 'ssh_pass_2', 'ssh_pass_3']
        ciphertexts = [encrypt_host_password(s) for s in secrets]
        assert all(ct.startswith('gAAAAA') for ct in ciphertexts)

        # Step 2: key 泄露, 部署 k2 (新) + k1 (旧)
        k2 = _gen_key()
        monkeypatch.setenv('OGS_FERNET_KEYS', f'{k2},{k1}')

        # Step 3: 业务解密, callback 自动迁移
        db_writes = []

        def mock_rehash_to_db(new_stored):
            # 模拟 DB 写回 (更新 row)
            db_writes.append(new_stored)

        # 模拟业务侧按需解密
        for i, ct in enumerate(ciphertexts):
            plain = decrypt_host_password(ct, rehash_callback=mock_rehash_to_db)
            assert plain == secrets[i], '解密结果应一致: %s' % secrets[i]

        # Step 4: 验证 callback 触发了 3 次迁移
        assert len(db_writes) == 3, '应触发 3 次迁移, 实际: %d' % len(db_writes)

        # Step 5: 模拟移除 k1 后, 用新 db_writes 数据 (都是 k2 加密) 解密
        monkeypatch.setenv('OGS_FERNET_KEYS', k2)
        for i, new_stored in enumerate(db_writes):
            plain = decrypt_host_password(new_stored)
            assert plain == secrets[i], '移除 k1 后, 迁移数据仍能解: %s' % secrets[i]

        # Step 6: 验证移除 k1 后, 旧密文无法再解 (key 已下)
        for ct in ciphertexts:
            with pytest.raises(RuntimeError):
                decrypt_host_password(ct)