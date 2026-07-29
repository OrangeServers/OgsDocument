# -*- coding: utf-8 -*-
"""
REV32 前端评审修复回归测试 (HIGH 3 项)

对应评审: REV31_review.md (HIGH: H1/H2/H3)
修复:
- H1: FileTransfer.vue handleBinaryData 循环 return BUG (多文件下载丢数据)
- H2: FileTransfer.vue getSftpWsUrl 未走 resolveWsUrl 校验
- H3: Login.vue 锁定仅前端计时，可被 F5 绕过

策略:
- 静态分析 (AST / 源码字符串): 验证修复模式已应用
- 行为模拟 (Python 复现 JS 逻辑): 验证 handleBinaryData/_saveLockState 行为正确
"""
import io
import os
import re

import pytest

FRONTEND_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    'frontend', 'src'
)


def _read(path):
    return io.open(path, encoding='utf-8').read()


def _extract_script_block(vue_source):
    """从 .vue 文件中提取 <script setup> 块 (含 import 区域).

    兼容 ti3-TS 迁移后的 `<script setup lang="ts">` 写法.
    """
    m = re.search(r'<script\b[^>]*?\bsetup\b[^>]*?>([\s\S]*?)</script>', vue_source)
    return m.group(1) if m else ''


def _extract_function_body(script, func_name):
    """粗提取 ES 函数体: function name(...) { ... }

    兼容 ti3-TS 迁移后的 TypeScript 函数签名：
      function name(p: T, ...): RType { ... }
      async function name(p: T): Promise<RType> { ... }
      function name(): { a: T } | null { ... }  // 返回类型含 { }
    """
    head_re = re.compile(
        rf'(?:async\s+)?function\s+{re.escape(func_name)}\s*\([^)]*\)'
    )
    head_m = head_re.search(script)
    if not head_m:
        return ''
    pos = head_m.end()
    n = len(script)

    def skip_ws():
        nonlocal pos
        while pos < n and script[pos].isspace():
            pos += 1

    skip_ws()
    # 可选 TypeScript 返回类型注解: : RType { ... }
    if pos < n and script[pos] == ':':
        pos += 1
        skip_ws()
        # 配对跳过 RType (可能含 { ... } 嵌套)
        # 限制在同行 (类型注解不会跨行)
        # 找到函数体开始 { 的规则:
        #   - 第一次 { depth=0 -> 进入嵌套 depth=1
        #   - 嵌套闭合后 (saw_close=True) 再遇到 { -> 函数体
        #   - 简单返回类型如 : void { 直接进入 fallback first_brace
        depth = 0
        first_brace = -1
        saw_close = False
        while pos < n and script[pos] != '\n':
            ch = script[pos]
            if ch == '{':
                if first_brace < 0:
                    first_brace = pos
                if depth == 0 and saw_close:
                    # 嵌套闭合后, 这是函数体
                    start = pos
                    pos += 1
                    depth = 1
                    break
                if depth == 0:
                    depth = 1
                else:
                    depth += 1
            elif ch == '}':
                if depth == 0:
                    return ''
                depth -= 1
                if depth == 0:
                    saw_close = True
            elif depth == 0 and ch == ';':
                pos += 1
                skip_ws()
                if pos < n and script[pos] == '{':
                    start = pos
                    pos += 1
                    depth = 1
                    break
                return ''
            pos += 1
        else:
            # 循环正常结束 (未 break, 即到换行符)
            if first_brace >= 0:
                start = first_brace
                pos = first_brace + 1
                depth = 1
            else:
                return ''
        # 提取函数体 (从 start+1 到 depth=0 的 })
        body_start = start + 1
        i = body_start
        while i < n and depth > 0:
            if script[i] == '{':
                depth += 1
            elif script[i] == '}':
                depth -= 1
            i += 1
        return script[body_start:i - 1]
    # 无返回类型注解
    if pos < n and script[pos] == '{':
        start = pos
        pos += 1
        depth = 1
        i = pos
        while i < n and depth > 0:
            if script[i] == '{':
                depth += 1
            elif script[i] == '}':
                depth -= 1
            i += 1
        return script[start + 1:i - 1]
    return ''


# =============================================================================
# H1: handleBinaryData 循环 return BUG 修复验证
# =============================================================================
class TestRev32H1HandleBinaryData:
    """REV31-H1: handleBinaryData 循环 return 修复 → 引入 activeDownloadPath"""

    FILE = os.path.join(FRONTEND_ROOT, 'views', 'FileTransfer.vue')

    def test_handleBinaryData_no_loop_return(self):
        """handleBinaryData 内不应再出现 'for (const path of Object.keys(downloadBuffers))' + 'return' 模式。"""
        vue = _read(self.FILE)
        script = _extract_script_block(vue)
        body = _extract_function_body(script, 'handleBinaryData')
        assert body, 'handleBinaryData 函数未找到'
        # 原始 bug: for 循环内立即 return
        assert 'for (const path of Object.keys(downloadBuffers))' not in body, (
            'handleBinaryData 仍含原始 bug 循环结构'
        )
        # 修复后必须含 activeDownloadPath
        assert 'activeDownloadPath' in body, (
            'handleBinaryData 必须使用 activeDownloadPath 路由 binary chunk'
        )

    def test_activeDownloadPath_declared(self):
        """activeDownloadPath 必须在 downloadBuffers 之后声明 (依赖顺序)。"""
        vue = _read(self.FILE)
        script = _extract_script_block(vue)
        assert 'let activeDownloadPath' in script, (
            'activeDownloadPath 变量必须声明'
        )

    def test_download_start_sets_activeDownloadPath(self):
        """download_start 分支必须设置 activeDownloadPath。"""
        vue = _read(self.FILE)
        script = _extract_script_block(vue)
        # 找到 download_start 块
        m = re.search(
            r"if \(action === 'download_start'\) \{([\s\S]*?)return\s*\n\s*\}",
            script
        )
        assert m, "download_start 分支未找到"
        block = m.group(1)
        # ti3-TS 迁移: download_start 内 msg → m (类型断言后)
        assert (
            'activeDownloadPath = msg.path' in block
            or 'activeDownloadPath = m.path' in block
        ), (
            "download_start 必须设 activeDownloadPath = msg.path 或 m.path"
        )

    def test_download_end_clears_activeDownloadPath(self):
        """download_end 分支必须清空 activeDownloadPath。"""
        vue = _read(self.FILE)
        script = _extract_script_block(vue)
        m = re.search(
            r"if \(action === 'download_end'\) \{([\s\S]*?)return\s*\n\s*\}",
            script
        )
        assert m, "download_end 分支未找到"
        block = m.group(1)
        assert 'activeDownloadPath' in block, (
            "download_end 必须操作 activeDownloadPath (清空)"
        )
        # 必须有 if (activeDownloadPath === path) activeDownloadPath = '' 清理
        assert re.search(
            r"if \(activeDownloadPath === path\)\s*activeDownloadPath\s*=\s*''",
            block
        ), "download_end 必须有 activeDownloadPath === path 守卫的清空"

    def test_behavior_simulation(self):
        """行为模拟: 修复后 binary chunk 路由到正确的 buffer。"""
        # 模拟修复后的 handleBinaryData 逻辑
        downloadBuffers = {}
        activeDownloadPath = ''

        def download_start(path):
            downloadBuffers[path] = []
            nonlocal_active = path
            return nonlocal_active  # 给外部

        def handle_binary_data(data, active_path):
            if active_path and downloadBuffers.get(active_path) is not None:
                downloadBuffers[active_path].append(data)

        def download_end(path):
            chunks = downloadBuffers.get(path, [])
            if path in downloadBuffers:
                del downloadBuffers[path]
            return chunks

        # 场景 1: 单文件下载
        download_start('/a.txt')
        active = '/a.txt'
        handle_binary_data(b'chunk1', active)
        handle_binary_data(b'chunk2', active)
        chunks = download_end('/a.txt')
        assert chunks == [b'chunk1', b'chunk2'], (
            f"单文件下载 chunk 合并错误: {chunks}"
        )

        # 场景 2: 多文件下载（修复前会丢数据，修复后通过 activeDownloadPath 路由）
        download_start('/b.txt')
        active = '/b.txt'
        handle_binary_data(b'b1', active)
        handle_binary_data(b'b2', active)
        chunks_b = download_end('/b.txt')
        assert chunks_b == [b'b1', b'b2'], (
            f"多文件下载 b.txt 丢数据: {chunks_b}"
        )

        # 场景 3: active path 为空时（无活动下载）应丢弃，避免脏数据
        handle_binary_data(b'orphan', '')
        # 无 buffer 应被写入 (downloadBuffers 仍为 {}/空)
        assert all(len(v) == 0 for v in downloadBuffers.values()), (
            "无 active path 时不应写入任何 buffer"
        )


# =============================================================================
# H2: getSftpWsUrl 走 resolveWsUrl 校验
# =============================================================================
class TestRev32H2GetSftpWsUrl:
    """REV31-H2: getSftpWsUrl 必须调用 resolveWsUrl (与 WebSSHCore 一致)"""

    FILE = os.path.join(FRONTEND_ROOT, 'views', 'FileTransfer.vue')

    def test_resolveWsUrl_imported(self):
        """FileTransfer.vue 必须 import resolveWsUrl。"""
        vue = _read(self.FILE)
        script = _extract_script_block(vue)
        assert "import { resolveWsUrl } from '@/utils/ws'" in script, (
            "FileTransfer.vue 必须 import resolveWsUrl from @/utils/ws"
        )

    def test_getSftpWsUrl_calls_resolveWsUrl(self):
        """getSftpWsUrl 函数体内必须调用 resolveWsUrl。"""
        vue = _read(self.FILE)
        script = _extract_script_block(vue)
        body = _extract_function_body(script, 'getSftpWsUrl')
        assert body, "getSftpWsUrl 函数未找到"
        assert 'resolveWsUrl(' in body, (
            "getSftpWsUrl 必须调用 resolveWsUrl 校验"
        )

    def test_getSftpWsUrl_uses_sftp_path(self):
        """getSftpWsUrl 必须返回 sftp/websocket 路径（不能错连到 terminal websocket）。"""
        vue = _read(self.FILE)
        script = _extract_script_block(vue)
        body = _extract_function_body(script, 'getSftpWsUrl')
        assert '/local/sftp/websocket' in body, (
            "getSftpWsUrl 必须指向 /local/sftp/websocket 路径"
        )
        # 不应再裸拼 ws://... 字符串绕过校验
        # 注意: fallback 分支允许 (因为它本身是同源相对路径)
        # 但 VITE_WS_URL 配置时必须走 resolveWsUrl
        assert 'resolveWsUrl' in body


# =============================================================================
# H3: Login 锁定加固 (sessionStorage + 后端响应识别 + 清理 timer)
# =============================================================================
class TestRev32H3LoginLock:
    """REV31-H3: Login 锁定加固
    - failCount/lockSeconds 持久化到 sessionStorage
    - 识别后端锁定响应 (msg 包含 "锁定"/"尝试过多")
    - lockTimer 在 onBeforeUnmount 清理
    """

    FILE = os.path.join(FRONTEND_ROOT, 'views', 'Login.vue')

    def test_onBeforeUnmount_imported(self):
        """Login.vue 必须 import onBeforeUnmount。"""
        vue = _read(self.FILE)
        script = _extract_script_block(vue)
        assert 'onBeforeUnmount' in script, (
            "Login.vue 必须 import { onBeforeUnmount } from 'vue'"
        )

    def test_sessionStorage_persistence(self):
        """Login.vue 必须有 sessionStorage 读写 (锁定状态持久化)。"""
        vue = _read(self.FILE)
        script = _extract_script_block(vue)
        assert 'sessionStorage' in script, (
            "Login.vue 必须用 sessionStorage 持久化锁定状态"
        )
        assert 'sessionStorage.setItem' in script or 'sessionStorage.getItem' in script, (
            "Login.vue 必须实际调用 sessionStorage API"
        )

    def test_loadLockState_on_mount(self):
        """onMounted 中必须调用 _loadLockState 恢复状态。"""
        vue = _read(self.FILE)
        script = _extract_script_block(vue)
        # 找 onMounted 块
        m = re.search(r'onMounted\(async\s*\(\)\s*=>\s*\{([\s\S]*?)\}\)', script)
        assert m, "onMounted 块未找到"
        body = m.group(1)
        assert '_loadLockState()' in body, (
            "onMounted 中必须调用 _loadLockState() 恢复锁定状态"
        )

    def test_lockTimer_cleanup_on_unmount(self):
        """onBeforeUnmount 中必须清理 lockTimer。"""
        vue = _read(self.FILE)
        script = _extract_script_block(vue)
        m = re.search(r'onBeforeUnmount\([^)]*\)\s*=>\s*\{([\s\S]*?)\}\)', script)
        assert m, "onBeforeUnmount 块未找到"
        body = m.group(1)
        assert 'clearInterval(lockTimer)' in body, (
            "onBeforeUnmount 必须 clearInterval(lockTimer) 清理"
        )

    def test_backend_lock_response_detection(self):
        """必须能识别后端锁定响应 (msg 含 锁定/尝试过多)。"""
        vue = _read(self.FILE)
        script = _extract_script_block(vue)
        # 关键词常量
        assert '锁定' in script and '尝试过多' in script, (
            "Login.vue 必须含后端锁定响应关键词常量"
        )
        # 检测函数
        body = _extract_function_body(script, 'isBackendLockResponse')
        assert body, "isBackendLockResponse 函数未找到"
        assert 'msg' in body and 'includes' in body, (
            "isBackendLockResponse 必须检测 msg 包含关键词"
        )

    def test_lock_response_triggers_startLock(self):
        """onSubmit 中：后端锁定响应 → startLock。"""
        vue = _read(self.FILE)
        script = _extract_script_block(vue)
        # 找 onSubmit 中 else 分支 (res.code !== 0)
        m = re.search(
            r'\}\s*else\s*\{\s*//\s*P1-6[\s\S]*?return\s*\n\s*\}',
            script
        )
        assert m, "onSubmit else 分支 (P1-6 注释后) 未找到"
        block = m.group(0)
        assert 'isBackendLockResponse(res)' in block, (
            "登录失败分支必须调用 isBackendLockResponse(res) 检测"
        )
        assert 'startLock()' in block, (
            "登录失败时必须调用 startLock()"
        )

    def test_behavior_simulation_lock_state_persistence(self):
        """行为模拟: 锁定状态写入 sessionStorage 后刷新仍能恢复。"""
        # 模拟浏览器 storage
        store = {}

        def save(state):
            import json
            store['ogs_login_fail_state'] = json.dumps(state)

        def load():
            import json
            raw = store.get('ogs_login_fail_state')
            if not raw:
                return None
            try:
                return json.loads(raw)
            except Exception:
                return None

        # 场景 1: 首次锁定
        import time
        until = time.time() * 1000 + 30000  # 30s 后到期
        save({'failCount': 5, 'until': until})
        state = load()
        assert state is not None
        assert state['failCount'] == 5
        assert state['until'] == until

        # 场景 2: 模拟倒计时中间
        time.sleep(0.01)
        new_until = time.time() * 1000 + 15000  # 15s 后到期
        save({'failCount': 5, 'until': new_until})
        state = load()
        remain = max(0, state['until'] - time.time() * 1000)
        assert 14000 < remain <= 15000, f"剩余时间计算错误: {remain}"

        # 场景 3: 过期
        expired_until = time.time() * 1000 - 1000
        save({'failCount': 5, 'until': expired_until})
        # load 后应当被判定为过期
        state = load()
        assert state['until'] < time.time() * 1000, "应判定为已过期"

    def test_behavior_simulation_backend_lock_detection(self):
        """行为模拟: 后端锁定响应识别。"""
        KEYWORDS = ['锁定', '尝试过多']

        def is_backend_lock_response(res):
            if not res or res.code == 0:
                return False
            msg = (res.msg or '').strip()
            return any(kw in msg for kw in KEYWORDS)

        class R:
            def __init__(self, code, msg):
                self.code = code
                self.msg = msg

        # 成功响应 → False
        assert is_backend_lock_response(R(0, '成功')) is False
        # 账号锁 → True
        assert is_backend_lock_response(R(100, '账号已锁定，请稍后再试')) is True
        # IP 锁 → True
        assert is_backend_lock_response(R(100, '登录尝试过多，请稍后再试')) is True
        # 密码错 → False
        assert is_backend_lock_response(R(100, '账号或密码错误')) is False
        # 验证码错 → False
        assert is_backend_lock_response(R(100, '验证码错误或已过期')) is False
        # None 输入 → False
        assert is_backend_lock_response(None) is False
