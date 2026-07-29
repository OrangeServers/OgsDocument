<template>
  <!-- REV33-M2: 复用 AuthShell 包装，只关注表单内容与品牌特色文案 -->
  <AuthShell meta-text="v2.0 · All systems operational">
    <template #brand>
      <h1 class="brand-title">
        {{ $t('auth.login.brandTitleLead') }}<br />
        <span class="brand-title-accent">{{ $t('auth.login.brandTitleAccent') }}</span>
      </h1>
      <p class="brand-desc">
        {{ $t('auth.login.brandDescLine1') }}<br />
        {{ $t('auth.login.brandDescLine2') }}
      </p>

      <div class="brand-features">
        <div class="feature-item">
          <span class="feature-dot"></span>
          <span class="feature-text">{{ $t('auth.login.feature1') }}</span>
        </div>
        <div class="feature-item">
          <span class="feature-dot"></span>
          <span class="feature-text">{{ $t('auth.login.feature2') }}</span>
        </div>
        <div class="feature-item">
          <span class="feature-dot"></span>
          <span class="feature-text">{{ $t('auth.login.feature3') }}</span>
        </div>
      </div>
    </template>

    <!-- 右侧登录表单 -->
    <div class="form-eyebrow">Sign in</div>
    <h2 class="form-title">{{ $t('auth.login.title') }}</h2>
    <p class="form-subtitle">{{ $t('auth.login.subtitle') }}</p>

        <el-form ref="formRef" :model="form" :rules="rules" @submit.prevent="onSubmit">
          <el-form-item prop="username">
            <label class="field-label">{{ $t('auth.field.username') }}</label>
            <el-input v-model="form.username" :placeholder="$t('auth.placeholder.username')" :prefix-icon="User" size="large" />
          </el-form-item>
          <el-form-item prop="password">
            <label class="field-label">{{ $t('auth.field.password') }}</label>
            <el-input v-model="form.password" type="password" :placeholder="$t('auth.placeholder.password')" :prefix-icon="Lock" size="large" show-password />
          </el-form-item>
          <el-form-item prop="yzm">
            <label class="field-label">{{ $t('auth.field.captcha') }}</label>
            <div class="captcha-row">
              <el-input v-model="form.yzm" :placeholder="$t('auth.placeholder.captchaResult')" size="large" style="flex:1" maxlength="3" />
              <!-- UI改造：算术验证码，点击刷新换一题 -->
              <div
                v-if="captchaExpr"
                class="captcha-expr"
                @click="refreshCaptcha"
                :title="$t('auth.login.captchaRefresh')"
              >{{ captchaExpr }}</div>
            </div>
          </el-form-item>
          <el-form-item style="margin-bottom: 8px">
            <el-button
              type="primary"
              size="large"
              class="submit-btn"
              :loading="loading"
              :disabled="lockSeconds > 0"
              native-type="submit"
            >
              {{ lockSeconds > 0 ? $t('auth.login.submitLocked', { s: lockSeconds }) : $t('auth.login.submit') }}
            </el-button>
          </el-form-item>
        </el-form>

        <div class="form-footer">
          <router-link v-if="registerOpen" to="/register" class="footer-link">{{ $t('auth.login.registerNow') }}</router-link>
          <el-link type="primary" :underline="false" @click="openForgotPwd" class="footer-link">{{ $t('auth.login.forgotPassword') }}</el-link>
        </div>

        <div class="form-legal">
          Copyright &copy; 2021-2026 by Xuzhiwei
        </div>

    <!-- 忘记密码弹窗 -->
    <el-dialog v-model="forgotVisible" :title="$t('auth.forgot.title')" width="420px" :close-on-click-modal="false">
      <el-form ref="forgotFormRef" :model="forgotForm" :rules="forgotRules" label-width="80px" @submit.prevent>
        <el-form-item :label="$t('auth.field.email')" prop="email">
          <el-input v-model="forgotForm.email" :placeholder="$t('auth.forgot.emailPlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('auth.field.captcha')" prop="code">
          <div style="display:flex;gap:10px;width:100%">
            <el-input v-model="forgotForm.code" :placeholder="$t('auth.forgot.codePlaceholder')" maxlength="6" style="flex:1" />
            <el-button :disabled="sendCooldown > 0" @click="sendForgotCode" :loading="sendingCode" style="white-space:nowrap">
              {{ sendCooldown > 0 ? sendCooldown + 's' : $t('auth.forgot.sendCode') }}
            </el-button>
          </div>
        </el-form-item>
        <el-form-item :label="$t('auth.field.newPassword')" prop="new_password">
          <el-input v-model="forgotForm.new_password" type="password" show-password :placeholder="$t('auth.forgot.newPasswordPlaceholder')" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="forgotVisible=false">{{ $t('common.action.cancel') }}</el-button>
        <el-button type="primary" @click="submitForgotReset" :loading="forgotSubmitting">{{ $t('auth.forgot.submit') }}</el-button>
      </template>
    </el-dialog>
  </AuthShell>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { login, checkAuth, getOpenSettings, forgotPwdSend, forgotPwdReset, getCaptcha } from '@/api'
import { t, setLocale } from '@/i18n'
import AuthShell from '@/components/AuthShell.vue'

/** 登录表单 */
interface LoginForm {
  username: string
  password: string
  yzm: string
}

/** 忘记密码表单 */
interface ForgotForm {
  email: string
  code: string
  new_password: string
}

/** 通用 API 响应 */
interface ApiResp {
  code: number
  msg?: string
  token?: string
  [k: string]: unknown
}

/** 验证码响应 */
interface CaptchaResp extends ApiResp {
  captcha_id?: string
  captcha_expr?: string
}

/** sessionStorage 状态 */
interface FailState {
  failCount: number
  until: number
}

/** 开放设置响应 */
interface OpenSettingsResp extends ApiResp {
  register_status?: string
  language?: string
}

const router = useRouter()
const formRef = ref<{ validate: () => Promise<boolean> } | null>(null)
const loading = ref<boolean>(false)
const registerOpen = ref<boolean>(false)
const captchaId = ref<string>('')        // P1-5: 后端返回的 captcha id
const captchaExpr = ref<string>('')      // UI改造: 算术验证码表达式（如 "3 + 5 = ?"）

// P1-6: 前端登录失败计数 + 临时禁用按钮 (5 次失败 → 锁 30s)
//   这是前端防"点太快"防御，作用是阻断脚本/用户的手动暴力
//   真正的账号/IP 锁定是后端 P1-3 阈值拆分控制 (账号 5, IP 20)
// REV31-H3: 额外加固
//   1. failCount / lockSeconds 持久化到 sessionStorage，避免 F5 刷新绕过
//   2. 识别后端锁定响应 (msg 包含 "锁定" / "尝试过多") → 同步进入锁定 UI
//   3. lockTimer 在 onBeforeUnmount 清理
const FAIL_STORAGE_KEY: string = 'ogs_login_fail_state'
const MAX_FAILS: number = 5
const LOCK_DURATION: number = 30
// 后端锁定响应特征文案 (后端 user.py login_dl 返回)
//   - '账号已锁定，请稍后再试' (P1-2: 账号锁)
//   - '登录尝试过多，请稍后再试' (P1-2: IP 锁)
const LOCK_RESPONSE_KEYWORDS: readonly string[] = ['锁定', '尝试过多'] // i18n-ignore

const failCount = ref<number>(0)
const lockSeconds = ref<number>(0)        // 剩余锁秒数
let lockTimer: ReturnType<typeof setInterval> | null = null

// 从 sessionStorage 恢复状态
function _loadLockState(): void {
  try {
    const raw = sessionStorage.getItem(FAIL_STORAGE_KEY)
    if (!raw) return
    const state = JSON.parse(raw) as FailState
    if (Date.now() < (state.until || 0)) {
      // 锁定未到期：恢复计数 + 倒计时
      const remain: number = Math.ceil((state.until - Date.now()) / 1000)
      lockSeconds.value = Math.max(remain, 0)
      failCount.value = state.failCount || MAX_FAILS
      if (lockSeconds.value > 0) startLock()
    } else {
      sessionStorage.removeItem(FAIL_STORAGE_KEY)
    }
  } catch {
    // 静默：sessionStorage 异常时仅当作无锁定状态
  }
}
function _saveLockState(): void {
  try {
    if (lockSeconds.value > 0) {
      const state: FailState = {
        failCount: failCount.value,
        until: Date.now() + lockSeconds.value * 1000,
      }
      sessionStorage.setItem(FAIL_STORAGE_KEY, JSON.stringify(state))
    } else {
      sessionStorage.removeItem(FAIL_STORAGE_KEY)
    }
  } catch {
    // 静默：sessionStorage 写失败不影响页面运行
  }
}

function startLock(): void {
  lockSeconds.value = LOCK_DURATION
  if (lockTimer) clearInterval(lockTimer)
  lockTimer = setInterval(() => {
    lockSeconds.value--
    _saveLockState()
    if (lockSeconds.value <= 0) {
      if (lockTimer) clearInterval(lockTimer)
      lockTimer = null
      lockSeconds.value = 0
      failCount.value = 0
      sessionStorage.removeItem(FAIL_STORAGE_KEY)
    }
  }, 1000)
  _saveLockState()
}

// REV31-H3: 检测后端锁定响应 → 同步 UI 锁定
function isBackendLockResponse(res: ApiResp | null | undefined): boolean {
  if (!res || res.code === 0) return false
  const msg = (res.msg || '').trim()
  return LOCK_RESPONSE_KEYWORDS.some(kw => msg.includes(kw))
}

// P1-5: 从后端拿 captcha (id + base64 PNG)
async function refreshCaptcha(): Promise<void> {
  try {
    const res = (await getCaptcha()) as unknown as CaptchaResp
    if (res.code === 0) {
      captchaId.value = res.captcha_id || ''
      captchaExpr.value = res.captcha_expr || ''
    }
  } catch {
    // 静默，登录时还会重试
  }
}

const form = ref<LoginForm>({ username: '', password: '', yzm: '' })
// I18N: 校验消息包在 computed 里，语言切换后即时生效
const rules = computed(() => ({
  username: [{ required: true, message: t('auth.validation.usernameRequired'), trigger: 'blur' }],
  password: [{ required: true, message: t('auth.validation.passwordRequired'), trigger: 'blur' }],
  yzm: [
    { required: true, message: t('auth.validation.captchaRequired'), trigger: 'blur' },
    // UI改造：算术验证码答案为 1~2 位数字（结果最大 40）
    { pattern: /^\d{1,2}$/, message: t('auth.validation.captchaNumeric'), trigger: 'blur' },
  ],
}))

async function onSubmit(): Promise<void> {
  await formRef.value?.validate()
  // P1-6: 前端锁定检查
  if (lockSeconds.value > 0) {
    ElMessage.warning(t('auth.login.lockedRetry', { s: lockSeconds.value }))
    return
  }
  // P1-5: 验证码校验改为后端，前端只负责传递 captcha_id + captcha_answer
  if (!captchaId.value) {
    ElMessage.error(t('auth.login.captchaNotLoaded'))
    return
  }
  loading.value = true
  try {
    // REVIEW-14-P0-1: 移除 sohu CDN 第三方脚本，不再传 user_gw_ip / user_gw_cs
    //   后端从 X-Real-IP header 拿（vite proxy 已自动注入）
    //   原实现：document.createElement('script') src='https://pv.sohu.com/cityjson'
    //   风险：Sohu CDN 投毒 / MITM / 任意 JS 执行
    const loginData = {
      ...form.value,
      captcha_id: captchaId.value,
      captcha_answer: form.value.yzm,
    }
    const res = (await login(loginData as unknown as Record<string, unknown>)) as unknown as ApiResp
    if (res.code === 0) {
      // 登录成功重置失败计数
      failCount.value = 0
      sessionStorage.removeItem(FAIL_STORAGE_KEY)
      // CRIT-4：后端已通过 Set-Cookie 自动设置 HttpOnly cookie（ogs_token），
      // 前端不再需手动 document.cookie。res.token 保留是供调试/老代码兼容。
      if (res.token) {
        console.debug('[Login] token handled by backend Set-Cookie')
      }
      ElMessage.success(t('auth.login.success'))
      router.push('/dashboard')
    } else {
      // P1-6: 失败计数 + 达到阈值锁 30s
      failCount.value++
      // REV31-H3: 后端锁定响应同步 UI（账号/IP 已被后端锁定时强制进入 lock 状态）
      if (isBackendLockResponse(res) || failCount.value >= MAX_FAILS) {
        startLock()
        ElMessage.error(res.msg || t('auth.login.failLocked', { n: MAX_FAILS, s: LOCK_DURATION }))
      } else {
        ElMessage.error(res.msg || t('auth.login.fail'))
      }
      // P1-5: 验证失败（验证码错/账号错）→ 强制刷新 captcha
      await refreshCaptcha()
      form.value.yzm = ''
      form.value.password = ''
    }
  } catch (e) {
    const err = e as Error & { response?: { status: number } }
    console.error('[Login] error:', err)
    // P1-6: 网络/服务端错误也计失败次数 (避免点重试)
    failCount.value++
    if (failCount.value >= MAX_FAILS) {
      startLock()
    }
    const msg = err.response
      ? t('auth.login.serverError', { status: err.response.status })
      : err.message || t('auth.login.networkError')
    ElMessage.error(t('auth.login.failWithReason', { msg }))
    await refreshCaptcha()
    form.value.yzm = ''
    form.value.password = ''
  } finally {
    loading.value = false
  }
}

// ---------- 忘记密码 ----------
const forgotVisible = ref<boolean>(false)
const forgotSubmitting = ref<boolean>(false)
const sendingCode = ref<boolean>(false)
const sendCooldown = ref<number>(0)
const forgotFormRef = ref<{ validate: () => Promise<boolean> } | null>(null)
const forgotForm = ref<ForgotForm>({ email: '', code: '', new_password: '' })
// I18N: 校验消息包在 computed 里，语言切换后即时生效
const forgotRules = computed(() => ({
  email: [
    { required: true, message: t('auth.validation.emailRequired'), trigger: 'blur' },
    { type: 'email', message: t('auth.validation.emailFormat'), trigger: 'blur' },
  ],
  code: [{ required: true, message: t('auth.validation.captchaRequired'), trigger: 'blur' }],
  new_password: [
    { required: true, message: t('auth.validation.newPasswordRequired'), trigger: 'blur' },
    { min: 6, message: t('auth.validation.newPasswordMin'), trigger: 'blur' },
  ],
}))

function openForgotPwd(): void {
  forgotForm.value = { email: '', code: '', new_password: '' }
  forgotVisible.value = true
}

async function sendForgotCode(): Promise<void> {
  if (!forgotForm.value.email) {
    ElMessage.warning(t('auth.forgot.emailFirst'))
    return
  }
  sendingCode.value = true
  try {
    const res = (await forgotPwdSend({ email: forgotForm.value.email } as unknown as Record<string, unknown>)) as unknown as ApiResp
    if (res.code === 0) {
      ElMessage.success(t('auth.forgot.codeSent'))
      sendCooldown.value = 60
      const timer: ReturnType<typeof setInterval> = setInterval(() => {
        sendCooldown.value--
        if (sendCooldown.value <= 0) clearInterval(timer)
      }, 1000)
    } else {
      // CRIT-5：统一错误码
      ElMessage.error(res.msg || t('auth.forgot.sendFail'))
    }
  } catch { ElMessage.error(t('auth.forgot.sendFail')) }
  finally { sendingCode.value = false }
}

async function submitForgotReset(): Promise<void> {
  await forgotFormRef.value?.validate()
  forgotSubmitting.value = true
  try {
    const res = (await forgotPwdReset({
      email: forgotForm.value.email,
      verification: forgotForm.value.code,
      new_password: forgotForm.value.new_password,
    } as unknown as Record<string, unknown>)) as unknown as ApiResp
    if (res.code === 0) {
      ElMessage.success(t('auth.forgot.resetSuccess'))
      forgotVisible.value = false
    } else {
      // CRIT-5：统一错误码
      ElMessage.error(res.msg || t('auth.forgot.resetFail'))
    }
  } catch { ElMessage.error(t('auth.forgot.resetFail')) }
  finally { forgotSubmitting.value = false }
}

onMounted(async () => {
  // REV31-H3: 恢复上次未到期的锁定状态 (避免 F5 绕过)
  _loadLockState()
  // P1-5: 改为从后端拿 captcha
  await refreshCaptcha()
  // REVIEW-14-P0-1: 移除 sohu CDN 第三方脚本注入
  //   原实现：document.createElement('script') src='https://pv.sohu.com/cityjson'
  //   依赖 window.returnCitySN 拿 IP/城市
  //   风险：Sohu CDN 投毒 / MITM / 任意 JS 执行
  //   修复：完全移除，IP 由后端从 X-Real-IP header 拿（vite proxy 已自动注入）
  try {
    const res = (await checkAuth()) as unknown as ApiResp
    if (res.code === 0) router.replace('/dashboard')
  } catch {
    // 静默
  }
  try {
    const res = (await getOpenSettings()) as unknown as OpenSettingsResp
    registerOpen.value = res.register_status === 'on'
    // I18N: 未登录首访也跟随服务端语言设置（/local/settings/open 返回 language 字段时生效）
    if (res.language) setLocale(res.language)
  } catch {
    // 静默
  }
})

// REV31-H3: 清理 setInterval 避免内存泄漏
onBeforeUnmount(() => {
  if (lockTimer) {
    clearInterval(lockTimer)
    lockTimer = null
  }
})
</script>

<style scoped>
/* REV33-M2: auth-page / auth-brand / brand-* / brand-decor 样式已抽到 AuthShell.vue
 * 此处仅保留表单专属样式：form-eyebrow / form-title / form-subtitle / field-label / captcha-* / submit-btn / form-footer / form-legal
 * 以及品牌特色文案（.brand-title / .brand-desc / .brand-features） ——这些会通过 AuthShell 的 :slotted 透传
 */

/* 左侧品牌特色文案（.brand-title / .brand-desc / .brand-features）样式已移至
 * index.css 全局区（.auth-brand 前缀）——:slotted 在当前构建链失效的修复，见 index.css 注释 */

/* =========================================
 *  表单专属样式
 * ========================================= */
.form-eyebrow {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--ogs-primary);
  margin-bottom: 14px;
}
.form-title {
  font-size: 32px;
  font-weight: 700;
  color: var(--ogs-text);
  letter-spacing: -0.025em;
  line-height: 1.2;
}
.form-subtitle {
  font-size: 14px;
  color: var(--ogs-text-secondary);
  margin-top: 10px;
  margin-bottom: 32px;
  letter-spacing: 0.005em;
}

.field-label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: var(--ogs-text-secondary);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  margin-bottom: 6px;
}

.captcha-row {
  display: flex;
  gap: 10px;
  width: 100%;
  align-items: center;
}
.captcha-expr {
  height: 44px;
  min-width: 128px;
  padding: 0 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--ogs-radius-sm);
  cursor: pointer;
  flex-shrink: 0;
  user-select: none;
  font-family: var(--ogs-mono);
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--ogs-primary);
  background: var(--ogs-primary-soft);
  border: 1px solid var(--ogs-primary-ring);
  transition: all 0.18s;
}
.captcha-expr:hover {
  border-color: var(--ogs-primary);
  box-shadow: 0 0 0 3px var(--ogs-primary-soft);
}

.submit-btn {
  width: 100%;
  height: 44px;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.1em;
  margin-top: 4px;
}

.form-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 16px;
}
.footer-link {
  font-size: 13px;
  color: var(--ogs-primary);
  text-decoration: none;
  transition: opacity 0.15s;
}
.footer-link:hover { opacity: 0.75; }

.form-legal {
  margin-top: 36px;
  text-align: center;
  font-size: 12px;
  color: var(--ogs-text-muted);
  letter-spacing: 0.02em;
}

/* 黑主题 —— 由 AuthShell.vue 提供，Login 不再重复 */
</style>
