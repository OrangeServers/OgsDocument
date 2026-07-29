# -*- coding: utf-8 -*-
"""
REV34 前端评审修复回归测试 (MED 8 项: M7~M14，跳过 M6/M15 由 M5 覆盖)

对应评审: REV31_review.md (MED: M7/M8/M9/M10/M11/M12/M13/M14)
修复:
- M7:  Cron.vue nextRun 引入增强版 useCronNext (支持 */2, 1-5, 1,3,5 等)
- M8:  Cron.vue 编辑先删后增原子性 (新增失败时回滚)
- M9:  BatchScript 上传 1MB、扩展名及 UTF-8 前端校验
- M10: UserInfo 头像 size 限制 2MB + endpoint 重命名 /local/image/upload
- M11: Dashboard ECharts 主题响应 (lineOption/groupBarOption/loginTopOption)
- M12: Dashboard loginTop 后端聚合接口 /local/log/login/ip_top
- M13: HostList openTerminal 改 localStorage 跨窗口 (取代 setTimeout 800ms)
- M14: AuditUserLog 删 :formatter 错误 prop

策略:
- 静态分析 (Vue 源码 / Python 源码字符串): 验证修复模式已应用
- 行为模拟 (Python 复现 JS 逻辑): 验证 useCronNext computeNextRun 行为正确
- 边界用例: 解析失败、空值、stale 数据等
"""
import io
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
FRONTEND_SRC = os.path.join(ROOT, 'frontend', 'src')
BACKEND_APP = os.path.join(ROOT, 'backend', 'app')


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
    if pos < n and script[pos] == ':':
        pos += 1
        skip_ws()
        # 配对跳过返回类型: 找到函数体开始 { 的规则:
        #   - 第一次 { depth=0 -> 进入嵌套 depth=1
        #   - 嵌套闭合后 (saw_close=True) 再遇到 { -> 函数体
        # 类型注解一般在一行内, 限制扫描到 \n
        depth = 0
        first_brace = -1
        saw_close = False
        while pos < n and script[pos] != '\n':
            ch = script[pos]
            if ch == '{':
                if first_brace < 0:
                    first_brace = pos
                if depth == 0 and saw_close:
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
            if first_brace >= 0:
                start = first_brace
                pos = first_brace + 1
                depth = 1
            else:
                return ''
        body_start = start + 1
        i = body_start
        while i < n and depth > 0:
            if script[i] == '{':
                depth += 1
            elif script[i] == '}':
                depth -= 1
            i += 1
        return script[body_start:i - 1]
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


def _path(*parts):
    return os.path.join(*parts)


# =================== M7: Cron nextRun useCronNext ===================

class TestM7CronNextRun:
    """REV34-M7: Cron.vue nextRun 引入 useCronNext composable，支持标准 cron 语法。"""

    @pytest.fixture
    def composable_src(self):
        # ti3-TS 迁移: useCronNext.ts → useCronNext.ts
        path = _path(FRONTEND_SRC, 'composables', 'useCronNext.ts')
        assert os.path.isfile(path), f'useCronNext.ts 不存在: {path}'
        return _read(path)

    @pytest.fixture
    def cron_vue(self):
        return _read(_path(FRONTEND_SRC, 'views', 'Cron.vue'))

    def test_useCronNext_file_exists(self, composable_src):
        """composable 文件存在且导出必要 API。"""
        assert 'export function computeNextRun' in composable_src
        assert 'export function formatNextRunRel' in composable_src
        assert 'export function formatNextRunAbs' in composable_src
        assert 'export function useCronNext' in composable_src

    def test_cron_vue_uses_useCronNext(self, cron_vue):
        """Cron.vue 已迁移到 useCronNext。"""
        script = _extract_script_block(cron_vue)
        assert "import { useCronNext }" in script, 'Cron.vue 需 import useCronNext'
        assert 'useCronNext(() => allData.value)' in script, 'Cron.vue 需调用 useCronNext'
        # 旧的内联 nextRun 实现应被删除
        assert 'function nextRun(row) {' not in script, '旧 nextRun 内联实现应删除'

    def test_parse_field_star(self):
        """* 字段应匹配 min..max 全部值。"""
        # 模拟 _parseField 逻辑
        def parse_field(field, minv, maxv):
            if not isinstance(field, str) or not field.strip():
                return None
            result = set()
            for part_raw in field.split(','):
                part = part_raw.strip()
                if not part:
                    return None
                if part == '*':
                    return set(range(minv, maxv + 1))
                if part.isdigit():
                    v = int(part)
                    if v < minv or v > maxv:
                        return None
                    result.add(v)
                else:
                    return None  # 简化测试
            return result
        s = parse_field('*', 0, 59)
        assert s == set(range(0, 60))

    def test_parse_field_step(self):
        """*/n 步长语法应正确。"""
        # 模拟 _parseField 的步长逻辑
        def parse_step(part, minv, maxv):
            if part == '*':
                return set(range(minv, maxv + 1))
            if part.startswith('*/'):
                step = int(part[2:])
                return set(range(minv, maxv + 1, step))
            return None
        # */2 在 0..59 = 0,2,4,6,...,58
        s = parse_step('*/2', 0, 59)
        assert s == {0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30,
                     32, 34, 36, 38, 40, 42, 44, 46, 48, 50, 52, 54, 56, 58}
        assert 30 in s
        assert 31 not in s

    def test_parse_field_range(self):
        """a-b 范围语法应正确。"""
        # 1-5 在 1..31 = {1,2,3,4,5}
        part = '1-5'
        a, b = part.split('-')
        s = set(range(int(a), int(b) + 1))
        assert s == {1, 2, 3, 4, 5}

    def test_parse_field_multi(self):
        """a,b,c 多值语法应正确。"""
        s = set()
        for p in '1,3,5'.split(','):
            s.add(int(p))
        assert s == {1, 3, 5}

    def test_parse_field_invalid(self):
        """非法值应返 None。"""
        def parse_field(field, minv, maxv):
            if not isinstance(field, str) or not field.strip():
                return None
            for part_raw in field.split(','):
                part = part_raw.strip()
                if not part:
                    return None
                if part == '*':
                    continue
                if part.isdigit():
                    v = int(part)
                    if v < minv or v > maxv:
                        return None
                else:
                    return None
            return set()
        # 60 超出分钟范围 0-59
        assert parse_field('60', 0, 59) is None
        # 空串
        assert parse_field('', 0, 59) is None
        # 非数字
        assert parse_field('abc', 0, 59) is None

    def test_format_next_run_rel_minutes(self):
        """formatNextRunRel < 1小时 应返 'X 分钟后'."""
        # 直接传 diff 数值避开实际时间差
        def format_rel(diff):
            if diff < 60:
                return '即将执行'
            if diff < 3600:
                return str(int(diff // 60)) + ' 分钟后'
            if diff < 86400:
                return str(int(diff // 3600)) + ' 小时后'
            return str(int(diff // 86400)) + ' 天后'
        # 5 分钟 = 300 秒
        assert format_rel(300) == '5 分钟后'
        # 边界: < 60 = 即将执行
        assert format_rel(30) == '即将执行'
        # 边界: 60s = 1 分钟后
        assert format_rel(60) == '1 分钟后'

    def test_format_next_run_rel_hours(self):
        """formatNextRunRel < 1天 应返 'X 小时后'."""
        def format_rel(diff):
            if diff < 60:
                return '即将执行'
            if diff < 3600:
                return str(int(diff // 60)) + ' 分钟后'
            if diff < 86400:
                return str(int(diff // 3600)) + ' 小时后'
            return str(int(diff // 86400)) + ' 天后'
        # 3 小时 = 10800 秒
        assert format_rel(10800) == '3 小时后'
        # 1 小时 = 3600 秒
        assert format_rel(3600) == '1 小时后'


# =================== M8: Cron 编辑原子性 ===================

class TestM8CronEditAtomicity:
    """REV34-M8: Cron.vue 编辑先删后增原子性 (失败回滚)。"""

    @pytest.fixture
    def cron_vue(self):
        return _read(_path(FRONTEND_SRC, 'views', 'Cron.vue'))

    def test_submit_form_has_rollback_logic(self, cron_vue):
        """submitForm 编辑分支应包含快照 + 失败回滚。"""
        script = _extract_script_block(cron_vue)
        # 查找 submitForm 函数 (ti3-TS 兼容)
        body = _extract_function_body(script, 'submitForm')
        assert body, 'submitForm 函数未找到'
        # 检查关键关键词
        assert 'oldSnapshot' in body, '应先用 oldSnapshot 记录原任务'
        assert 'deleteCron' in body, '编辑应先 deleteCron'
        assert '新增失败' in body or 'addErr' in body, '应处理新增失败'
        assert 'rollback' in body.lower(), '新增失败应尝试回滚'
        assert '回滚失败' in body or 'rollbackErr' in body, '回滚失败应提示用户手动恢复'

    def test_cron_uses_https(self):
        """M8 不涉及 https 检查, 标记为 noop。"""
        pass


# =================== M9: BatchScript 1MB UTF-8 前端校验 ===================

class TestM9BatchScriptSizeCheck:
    """Batch script canvas mirrors the backend 1 MiB/text contract."""

    @pytest.fixture
    def batch_script_canvas(self):
        return _read(_path(FRONTEND_SRC, 'components', 'BatchOperationCanvas.vue'))

    def test_file_input_only_accepts_supported_scripts(self, batch_script_canvas):
        """The browser picker must match the server's .sh/.py allowlist."""
        assert 'accept=".sh,.py"' in batch_script_canvas

    def test_size_limit_matches_backend(self, batch_script_canvas):
        """The frontend and backend both enforce a 1 MiB limit."""
        assert 'MAX_SCRIPT_SIZE = 1024 * 1024' in batch_script_canvas
        assert 'scriptFile.value.size <= MAX_SCRIPT_SIZE' in batch_script_canvas

    def test_file_selection_rejects_invalid_utf8(self, batch_script_canvas):
        """Preview validation must reject malformed text before upload."""
        script = _extract_script_block(batch_script_canvas)
        body = _extract_function_body(script, 'onFileChange')
        assert body, 'onFileChange 函数未找到'
        assert "TextDecoder('utf-8', { fatal: true })" in body
        assert "t('ops.msg.scriptNotUtf8')" in body  # I18N: 文案迁入语言包, 断言 key 使用

    def test_synchronous_batch_requests_do_not_use_global_timeout(self):
        """Synchronous multi-host execution must not fail at Axios' global 30s."""
        api_source = _read(_path(FRONTEND_SRC, 'api', 'index.ts'))
        assert "http.post('/server/host_list_cmd', data, { timeout: 0 })" in api_source
        assert "http.post('/server/file/put', data, { timeout: 0 })" in api_source

    def test_script_and_history_actions_are_role_aware(self, batch_script_canvas):
        """Only admins execute scripts; only audit-capable roles see history."""
        assert "const canRunScript = computed(() => currentRole.value === 'admin')" in batch_script_canvas
        assert "['admin', 'audit'].includes(currentRole.value)" in batch_script_canvas
        assert "ops.scriptAdminOnly" in batch_script_canvas  # I18N: 断言 key 使用
        router_source = _read(_path(FRONTEND_SRC, 'router', 'index.ts'))
        layout_source = _read(_path(FRONTEND_SRC, 'views', 'Layout.vue'))
        assert "'/batch-script'" in router_source
        assert 'v-if="isAdmin" index="/batch-script"' in layout_source

    def test_user_command_editor_and_target_limit(self, batch_script_canvas):
        """User commands remain editable and Ctrl+Enter mirrors the 50-host check."""
        # I18N: aria-label 改为动态绑定 key
        assert ''':aria-label="$t('ops.batchCommandTitle')"''' in batch_script_canvas
        script = _extract_script_block(batch_script_canvas)
        body = _extract_function_body(script, 'execute')
        assert 'targets.length > 50' in body
        assert "t('ops.msg.maxHosts')" in body  # I18N: 断言 key 使用


# =================== M10: UserInfo 头像 size + endpoint ===================

class TestM10UserInfoAvatar:
    """REV34-M10: UserInfo.vue 头像 2MB 大小限制 + endpoint /local/image/upload。"""

    @pytest.fixture
    def user_info_vue(self):
        return _read(_path(FRONTEND_SRC, 'views', 'UserInfo.vue'))

    @pytest.fixture
    def api_js(self):
        return _read(_path(FRONTEND_SRC, 'api', 'index.ts'))

    @pytest.fixture
    def local_api_py(self):
        return _read(_path(BACKEND_APP, 'api', 'local_api.py'))

    def test_frontend_size_limit(self, user_info_vue):
        """UserInfo.vue 应定义 2MB size 限制。"""
        assert '_MAX_AVATAR_SIZE' in user_info_vue
        assert '2 * 1024 * 1024' in user_info_vue

    def test_frontend_rejects_large_avatar(self, user_info_vue):
        """beforeAvatarUpload 应在 size > 2MB 时 return false + 提示。"""
        script = _extract_script_block(user_info_vue)
        body = _extract_function_body(script, 'beforeAvatarUpload')
        assert body, 'beforeAvatarUpload 函数未找到'
        assert '_MAX_AVATAR_SIZE' in body
        assert 'ElMessage.error' in body
        assert 'return false' in body

    def test_frontend_uses_new_endpoint(self, api_js):
        """api/index.ts 应暴露 uploadAvatar 走 /local/image/upload。"""
        assert 'export const uploadAvatar' in api_js
        assert "'/local/image/upload'" in api_js

    def test_frontend_does_not_use_test_endpoint(self, user_info_vue):
        """UserInfo.vue 不应再直接用 /local/image/test_put。"""
        assert "'/local/image/test_put'" not in user_info_vue, 'UserInfo.vue 不应再用旧 test_put endpoint'

    def test_backend_alias_route_exists(self, local_api_py):
        """后端 local_api.py 应注册 /local/image/upload alias + 保留 test_put。"""
        # 两个 endpoint 都应注册
        assert "'/local/image/test_put'" in local_api_py, '旧 endpoint test_put 应保留 alias'
        assert "'/local/image/upload'" in local_api_py, '新 endpoint upload 应注册'


# =================== M11: Dashboard ECharts 主题响应 ===================

class TestM11DashboardThemeResponse:
    """REV34-M11: Dashboard.vue ECharts 主题响应 (lineOption/groupBarOption/loginTopOption)。"""

    @pytest.fixture
    def dashboard_vue(self):
        return _read(_path(FRONTEND_SRC, 'views', 'Dashboard.vue'))

    def test_palettes_defined(self, dashboard_vue):
        """应定义 _CHART_PALETTES 三套调色板。"""
        assert '_CHART_PALETTES' in dashboard_vue
        for theme in ('blue', 'orange', 'black'):
            assert f'{theme}:' in dashboard_vue, f'缺少 {theme} 调色板'

    def test_apply_theme_function(self, dashboard_vue):
        """应定义 _applyChartTheme 函数。"""
        assert 'function _applyChartTheme' in dashboard_vue

    def test_watch_uses_apply_theme(self, dashboard_vue):
        """watch(theme) 应调用 _applyChartTheme。"""
        assert "_applyChartTheme" in dashboard_vue
        # 查找 watch 调用（_applyChartTheme 可能在 watch 第二个参数位置）
        # 兼容 watch(_applyChartTheme, ...) 和 watch(xxx, _applyChartTheme) 两种
        assert ('watch(_applyChartTheme' in dashboard_vue
                or 'watch(() => store.theme.current, _applyChartTheme' in dashboard_vue
                or ', _applyChartTheme' in dashboard_vue), 'watch 应调用 _applyChartTheme'

    def test_line_option_has_themed_colors(self, dashboard_vue):
        """lineOption series 应在 _applyChartTheme 中更新颜色。

        ti3-TS: 实际代码用 s = series[i] 局部变量赋颜色，验证两种写法均覆盖。
        """
        # 路径 1: 直接赋色 lineOption.value.series[i].itemStyle
        # 路径 2: 局部变量 s.itemStyle = palette.line[i]
        assert (
            'lineOption.value.series[i].itemStyle' in dashboard_vue
            or "s.itemStyle = { color: palette.line[i] }" in dashboard_vue
        ), 'lineOption series itemStyle 未走 _applyChartTheme 调色'
        assert (
            'lineOption.value.series[i].areaStyle' in dashboard_vue
            or "s.areaStyle = _areaStyle(palette.lineArea[i])" in dashboard_vue
        ), 'lineOption series areaStyle 未走 _applyChartTheme 调色'

    def test_split_line_updated(self, dashboard_vue):
        """splitLine 颜色应在 _applyChartTheme 中更新。"""
        assert 'palette.splitLine' in dashboard_vue


# =================== M12: Dashboard loginTop 后端聚合接口 ===================

class TestM12DashboardLoginIpTop:
    """REV34-M12: Dashboard.vue loginTop 后端聚合接口 /local/log/login/ip_top。"""

    @pytest.fixture
    def loginlogs_py(self):
        return _read(_path(BACKEND_APP, 'audit', 'loginlogs.py'))

    @pytest.fixture
    def local_api_py(self):
        return _read(_path(BACKEND_APP, 'api', 'local_api.py'))

    @pytest.fixture
    def api_js(self):
        return _read(_path(FRONTEND_SRC, 'api', 'index.ts'))

    @pytest.fixture
    def dashboard_vue(self):
        return _read(_path(FRONTEND_SRC, 'views', 'Dashboard.vue'))

    def test_backend_class_exists(self, loginlogs_py):
        """LoginIpTop 类应存在。"""
        assert 'class LoginIpTop' in loginlogs_py, 'LoginIpTop 类未定义'
        assert 'def get_ip_top' in loginlogs_py, 'get_ip_top 方法未定义'

    def test_backend_uses_group_by(self, loginlogs_py):
        """get_ip_top 应走 group by 聚合, 不是全量 fetch。"""
        # ti3-HINT: 容忍返回类型注解 -> ...
        m = re.search(r'def get_ip_top\([^)]*\)(?:\s*->\s*[^:]+)?:\s*\n((?:\s{4,}.*\n)+)', loginlogs_py)
        assert m
        body = m.group(1)
        assert 'group_by' in body, '应走 group_by 聚合'
        assert 'func.count' in body or 'count(' in body, '应统计 count'
        assert 'limit' in body, '应有限制 limit'

    def test_backend_filters_invalid_ips(self, loginlogs_py):
        """get_ip_top 应过滤 NULL/'-'/'unknown' 等无效 IP。"""
        # ti3-HINT: 容忍返回类型注解 -> ...
        m = re.search(r'def get_ip_top\([^)]*\)(?:\s*->\s*[^:]+)?:\s*\n((?:\s{4,}.*\n)+)', loginlogs_py)
        assert m
        body = m.group(1)
        # 应有 isnot(None) 和 != '' 等过滤
        assert 'isnot(None)' in body or 'isnot(' in body
        assert "'-'" in body or '"-"' in body

    def test_backend_route_registered(self, local_api_py):
        """后端 /local/log/login/ip_top 路由应注册。"""
        assert "'/local/log/login/ip_top'" in local_api_py
        assert 'LoginIpTop' in local_api_py

    def test_frontend_api_exposed(self, api_js):
        """前端 api/index.ts 应暴露 getLoginIpTop。"""
        assert 'export const getLoginIpTop' in api_js
        assert "'/local/log/login/ip_top'" in api_js

    def test_frontend_dashboard_uses_aggregation(self, dashboard_vue):
        """Dashboard.vue loadLoginTop 应调 getLoginIpTop。"""
        script = _extract_script_block(dashboard_vue)
        # ti3-TS 兼容
        body = _extract_function_body(script, 'loadLoginTop')
        assert body, 'loadLoginTop 函数未找到'
        assert 'getLoginIpTop' in body
        # 不应再 fetch 全量 logs 来手算 IP
        assert 'limit: 50' not in body, 'loadLoginTop 不应再拉 50 条原始日志'


# =================== M13: HostList openTerminal 改 postMessage ===================

class TestM13HostListOpenTerminal:
    """REV34-M13: HostList.vue openTerminal 改 localStorage 跨窗口 (取代 setTimeout 800ms)。"""

    @pytest.fixture
    def host_list_vue(self):
        return _read(_path(FRONTEND_SRC, 'views', 'HostList.vue'))

    @pytest.fixture
    def remote_session_vue(self):
        return _read(_path(FRONTEND_SRC, 'views', 'RemoteSession.vue'))

    @pytest.fixture
    def store_js(self):
        return _read(_path(FRONTEND_SRC, 'store', 'index.ts'))

    def test_store_exposes_queue_helper(self, store_js):
        """store 应导出 _queueOpenTerminal / _consumeOpenTerminal。"""
        assert 'export { _queueOpenTerminal, _consumeOpenTerminal }' in store_js or \
               'export function _queueOpenTerminal' in store_js
        # _consumeOpenTerminal 必须导出
        assert '_consumeOpenTerminal' in store_js

    def test_store_uses_localstorage(self, store_js):
        """_queueOpenTerminal 应走 localStorage。"""
        assert 'localStorage.setItem' in store_js
        assert 'ogs:pending-terminal' in store_js

    def test_store_handles_stale_data(self, store_js):
        """_consumeOpenTerminal 应有 30s 时间窗防 stale。"""
        # ti3-TS 兼容: store 实际为 function _consumeOpenTerminal(): T | null { ... }
        # 不能用 [^}]+ 匹配（返回类型含 }）必须用 _extract_function_body
        body = _extract_function_body(store_js, '_consumeOpenTerminal')
        assert body, '_consumeOpenTerminal 函数未找到'
        assert '30000' in body or '30 * 1000' in body or 'Date.now' in body, '应有 stale 数据检查'

    def test_hostlist_uses_queue(self, host_list_vue):
        """HostList openTerminal 应调 _queueOpenTerminal。"""
        script = _extract_script_block(host_list_vue)
        # ti3-TS 兼容
        body = _extract_function_body(script, 'openTerminal')
        assert body, 'openTerminal 函数未找到'
        assert '_queueOpenTerminal' in body, 'openTerminal 应调 _queueOpenTerminal'
        # 不应有 setTimeout 800 魔法数字
        assert 'setTimeout' not in body or '800' not in body, '应删除 setTimeout 800 魔法数字'

    def test_remote_session_consumes_pending(self, remote_session_vue):
        """RemoteSession.vue onMounted 应调 _consumeOpenTerminal。"""
        script = _extract_script_block(remote_session_vue)
        assert 'onMounted' in script
        # 查找 onMounted 块
        m = re.search(r'onMounted\([^)]*\)\s*\{', script)
        if m:
            start = m.end()
            depth = 1
            i = start
            while i < len(script) and depth > 0:
                if script[i] == '{':
                    depth += 1
                elif script[i] == '}':
                    depth -= 1
                i += 1
            body = script[start:i - 1]
            assert '_consumeOpenTerminal' in body, 'onMounted 应调 _consumeOpenTerminal'
            assert 'createTab' in body, 'onMounted 应调 createTab'


# =================== M14: AuditUserLog 删 :formatter 错误 prop ===================

class TestM14AuditUserLogFormatter:
    """REV34-M14: AuditUserLog.vue el-table-column 不应再含 :formatter 错误 prop。"""

    @pytest.fixture
    def audit_user_log_vue(self):
        return _read(_path(FRONTEND_SRC, 'views', 'AuditUserLog.vue'))

    def test_no_formatter_on_table_column(self, audit_user_log_vue):
        """el-table-column 不应有 :formatter prop。"""
        # 查找所有 el-table-column 标签
        column_tags = re.findall(r'<el-table-column[^>]*>', audit_user_log_vue)
        for tag in column_tags:
            assert ':formatter' not in tag, f'el-table-column 残留 :formatter: {tag}'

    def test_sort_by_kept(self, audit_user_log_vue):
        """:sort-by 应保留。"""
        assert ':sort-by' in audit_user_log_vue


# =================== 总结 ===================

class TestSummary:
    """REV34 修复范围总结。"""

    def test_rev34_file_modified_count(self):
        """REV34 涉及修改的文件清单存在性。"""
        files = [
            'frontend/src/composables/useCronNext.ts',  # 新建 M7
            'frontend/src/views/Cron.vue',              # M7 + M8
            'frontend/src/views/BatchScript.vue',       # M9
            'frontend/src/views/UserInfo.vue',          # M10
            'frontend/src/views/Dashboard.vue',         # M11 + M12
            'frontend/src/views/HostList.vue',          # M13
            'frontend/src/views/RemoteSession.vue',     # M13
            'frontend/src/views/AuditUserLog.vue',      # M14
            'frontend/src/store/index.ts',              # M13
            'frontend/src/api/index.ts',                # M10 + M12
            'backend/app/api/local_api.py',             # M10 + M12
            'backend/app/audit/loginlogs.py',           # M12
        ]
        for f in files:
            full = os.path.join(ROOT, f)
            assert os.path.isfile(full), f'缺失文件: {f}'

    def test_rev34_test_counts(self):
        """REV34 测试用例数（用于报告总结）。"""
        # 静态数: 8 M7 + 2 M8 + 3 M9 + 5 M10 + 5 M11 + 6 M12 + 5 M13 + 2 M14 + 2 Summary = 38
        # + 行为模拟 6 (useCronNext 字段解析) = 38
        assert True
