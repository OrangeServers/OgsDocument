<template>
  <!-- REV33-M2: 复用 AuthShell 包装（Login / Register 共用双栏布局） -->
  <AuthShell meta-text="v2.0 · Ready to start">
    <template #brand>
      <h1 class="brand-title">
        {{ $t('auth.register.brandTitleLead') }}<br />
        <span class="brand-title-accent">{{ $t('auth.register.brandTitleAccent') }}</span>
      </h1>
      <p class="brand-desc">
        {{ $t('auth.register.brandDescLine1') }}<br />
        {{ $t('auth.register.brandDescLine2') }}
      </p>

      <!-- 注册流程步骤（注册场景特有） -->
      <div class="brand-steps">
        <div class="step-item">
          <span class="step-num">01</span>
          <div class="step-body">
            <div class="step-name">{{ $t('auth.register.step1Name') }}</div>
            <div class="step-desc">{{ $t('auth.register.step1Desc') }}</div>
          </div>
        </div>
        <div class="step-item">
          <span class="step-num">02</span>
          <div class="step-body">
            <div class="step-name">{{ $t('auth.register.step2Name') }}</div>
            <div class="step-desc">{{ $t('auth.register.step2Desc') }}</div>
          </div>
        </div>
        <div class="step-item">
          <span class="step-num">03</span>
          <div class="step-body">
            <div class="step-name">{{ $t('auth.register.step3Name') }}</div>
            <div class="step-desc">{{ $t('auth.register.step3Desc') }}</div>
          </div>
        </div>
      </div>
    </template>

    <!-- 右侧注册表单 -->
    <div class="form-eyebrow">Get started</div>
    <h2 class="form-title">{{ $t('auth.register.title') }}</h2>
    <p class="form-subtitle">{{ $t('auth.register.subtitle') }}</p>

        <el-form ref="formRef" :model="form" :rules="rules" @submit.prevent="onSubmit">
          <!-- 用户名 + 检查 -->
          <el-form-item prop="username">
            <label class="field-label">{{ $t('auth.field.username') }}</label>
            <div class="input-row">
              <el-input
                v-model="form.username"
                :placeholder="$t('auth.placeholder.username')"
                :prefix-icon="User"
                size="large"
                style="flex:1"
              />
              <el-button size="large" :loading="checking" @click="checkName" plain class="row-btn">
                {{ $t('auth.register.check') }}
              </el-button>
            </div>
          </el-form-item>

          <!-- 邮箱 + 验证码 -->
          <el-form-item prop="email">
            <label class="field-label">{{ $t('auth.field.email') }}</label>
            <el-input
              v-model="form.email"
              :placeholder="$t('auth.register.emailPlaceholder')"
              :prefix-icon="Message"
              size="large"
            />
          </el-form-item>

          <el-form-item prop="yzm">
            <label class="field-label">{{ $t('auth.field.emailCode') }}</label>
            <div class="input-row">
              <el-input
                v-model="form.yzm"
                :placeholder="$t('auth.register.codePlaceholder')"
                :prefix-icon="Key"
                size="large"
                maxlength="6"
                style="flex:1"
              />
              <el-button
                size="large"
                type="primary"
                plain
                @click="sendCode"
                :disabled="cooldown > 0"
                :loading="sending"
                class="row-btn"
              >
                {{ cooldown > 0 ? $t('auth.register.resendIn', { s: cooldown }) : $t('auth.register.getCode') }}
              </el-button>
            </div>
          </el-form-item>

          <!-- 密码 + 强度计 -->
          <el-form-item prop="password1">
            <label class="field-label">{{ $t('auth.field.setPassword') }}</label>
            <el-input
              v-model="form.password1"
              type="password"
              :placeholder="$t('auth.register.passwordPlaceholder')"
              :prefix-icon="Lock"
              size="large"
              show-password
            />
            <div class="pwd-strength">
              <div class="strength-track">
                <div
                  class="strength-bar"
                  :class="`lv-${strength.level}`"
                  :style="{ width: strength.percent + '%' }"
                ></div>
              </div>
              <div class="strength-text" :class="`lv-${strength.level}`">
                {{ $t('auth.register.strengthLabel') }}<span>{{ strength.label }}</span>
              </div>
            </div>
          </el-form-item>

          <!-- 确认密码 -->
          <el-form-item prop="password">
            <label class="field-label">{{ $t('auth.field.confirmPassword') }}</label>
            <el-input
              v-model="form.password"
              type="password"
              :placeholder="$t('auth.register.confirmPlaceholder')"
              :prefix-icon="Lock"
              size="large"
              show-password
            >
              <template #suffix>
                <el-icon v-if="form.password" :size="16" :color="pwMatch ? '#10B981' : '#F43F5E'">
                  <component :is="pwMatch ? 'CircleCheckFilled' : 'CircleCloseFilled'" />
                </el-icon>
              </template>
            </el-input>
            <div v-if="form.password && !pwMatch" class="match-hint">{{ $t('auth.register.pwMismatch') }}</div>
          </el-form-item>

          <el-form-item style="margin-bottom: 8px">
            <el-checkbox v-model="agreed" class="agree-check">
              <!-- REV33-M3: 服务条款 / 隐私政策 —— 真链接 + 弹窗预览（避免虚假 javascript: 伪链） -->
              <span class="agree-text">
                {{ $t('auth.register.agreePrefix') }}
                <a href="#" @click.prevent="openLegal('terms')">{{ $t('auth.register.terms') }}</a>
                {{ $t('auth.register.agreeAnd') }}
                <a href="#" @click.prevent="openLegal('privacy')">{{ $t('auth.register.privacy') }}</a>
              </span>
            </el-checkbox>
          </el-form-item>

          <el-form-item style="margin-bottom: 8px">
            <el-button
              type="primary"
              size="large"
              class="submit-btn"
              :loading="loading"
              :disabled="!agreed"
              native-type="submit"
            >
              {{ $t('auth.register.submit') }}
            </el-button>
          </el-form-item>
        </el-form>

        <div class="form-footer">
          <span class="footer-text">{{ $t('auth.register.haveAccount') }}</span>
          <router-link to="/login" class="footer-link">{{ $t('auth.register.loginNow') }}</router-link>
        </div>

        <div class="form-legal">
          Copyright &copy; 2021-2026 by Xuzhiwei
        </div>

        <!-- REV33-M3: 服务条款 / 隐私政策 弹窗 -->
        <el-dialog
          v-model="legalDialogVisible"
          :title="legalDialogTitle"
          width="560px"
          :close-on-click-modal="true"
        >
          <pre class="legal-content">{{ legalDialogContent }}</pre>
          <template #footer>
            <el-button type="primary" @click="legalDialogVisible = false">{{ $t('auth.register.acknowledged') }}</el-button>
          </template>
        </el-dialog>
  </AuthShell>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter, type Router } from 'vue-router'
import { User, Message, Key, Lock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { checkUsername, register as doRegister, sendMail, getSettings } from '@/api'
import { t } from '@/i18n'
import AuthShell from '@/components/AuthShell.vue'
import { usePasswordStrength } from '@/composables/usePasswordStrength'

/** 注册表单 */
interface RegisterForm {
  username: string
  email: string
  yzm: string
  password1: string
  password: string
}

/** 通用 API 响应 */
interface ApiResp {
  code: number
  msg?: string
  [k: string]: unknown
}

/** 系统设置响应 */
interface SettingsResp extends ApiResp {
  register_status?: string
}

const router: Router = useRouter()
const formRef = ref<{ validate: () => Promise<boolean> } | null>(null)
const loading = ref<boolean>(false)
const checking = ref<boolean>(false)
const sending = ref<boolean>(false)
const cooldown = ref<number>(0)
const agreed = ref<boolean>(false)
let timer: ReturnType<typeof setInterval> | null = null

const form = ref<RegisterForm>({
  username: '', email: '', yzm: '', password1: '', password: '',
})
const pwMatch = computed<boolean>(
  () => Boolean(form.value.password) && form.value.password === form.value.password1
)

// I18N: 校验消息包在 computed 里，语言切换后即时生效
const rules = computed(() => ({
  username: [{ required: true, message: t('auth.validation.usernameRequired'), trigger: 'blur' }],
  email: [
    { required: true, message: t('auth.validation.emailRequired'), trigger: 'blur' },
    { type: 'email', message: t('auth.validation.emailFormat'), trigger: 'blur' },
  ],
  yzm: [{ required: true, message: t('auth.validation.captchaRequired'), trigger: 'blur' }],
  password1: [
    { required: true, message: t('auth.validation.passwordRequired'), trigger: 'blur' },
    { min: 8, message: t('auth.validation.passwordMin8'), trigger: 'blur' },
  ],
  password: [{ required: true, message: t('auth.validation.confirmPasswordRequired'), trigger: 'blur' }],
}))

// ====== 密码强度计算（REV33-M2: 抽离到 composables/usePasswordStrength.js） ======
const { strength } = usePasswordStrength(() => form.value.password1)

// ====== REV33-M3: 服务条款 / 隐私政策 弹窗 ======
// I18N: 示例条款文本移入 locales auth.register.termsContent / privacyContent
const legalDialogVisible = ref<boolean>(false)
const legalDialogTitle = ref<string>('')
const legalDialogContent = ref<string>('')
function openLegal(type: 'terms' | 'privacy'): void {
  if (type === 'terms') {
    legalDialogTitle.value = t('auth.register.terms')
    legalDialogContent.value = t('auth.register.termsContent')
  } else if (type === 'privacy') {
    legalDialogTitle.value = t('auth.register.privacy')
    legalDialogContent.value = t('auth.register.privacyContent')
  }
  legalDialogVisible.value = true
}

async function checkName(): Promise<void> {
  if (!form.value.username) {
    ElMessage.warning(t('auth.register.usernameFirst'))
    return
  }
  checking.value = true
  try {
    const res = (await checkUsername({ username: form.value.username } as unknown as Record<string, unknown>)) as unknown as ApiResp
    ElMessage({
      message: res.code === 0 ? t('auth.register.usernameAvailable') : t('auth.register.usernameTaken'),
      type: res.code === 0 ? 'success' : 'error',
    })
  } finally {
    checking.value = false
  }
}

async function sendCode(): Promise<void> {
  if (!form.value.email) {
    ElMessage.warning(t('auth.register.emailFirst'))
    return
  }
  sending.value = true
  try {
    const res = (await sendMail({ email: form.value.email } as unknown as Record<string, unknown>)) as unknown as ApiResp
    if (res.code === 0) {
      ElMessage.success(t('auth.register.codeSent'))
      cooldown.value = 60
      // REV35-L14: 重复发送时先清理上轮的 timer，避免多个 setInterval 同时递减
      if (timer) clearInterval(timer)
      timer = setInterval(() => {
        cooldown.value--
        if (cooldown.value <= 0 && timer) {
          clearInterval(timer)
          timer = null
        }
      }, 1000)
    } else {
      // CRIT-5：错误码统一为 100，具体原因由 res.msg 传递
      ElMessage.error(res.msg || t('auth.register.sendFail'))
    }
  } catch {
    ElMessage.error(t('auth.register.sendFail'))
  } finally {
    sending.value = false
  }
}

// REV35-L14: 组件卸载时清理倒计时 timer，防内存泄漏 + 后台递增
onBeforeUnmount(() => {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
})

async function onSubmit(): Promise<void> {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  if (!pwMatch.value) {
    ElMessage.error(t('auth.register.pwMismatch'))
    return
  }
  if (strength.value.level < 2) {
    ElMessage.warning(t('auth.register.pwTooWeak'))
    return
  }
  loading.value = true
  try {
    const res = (await doRegister(form.value as unknown as Record<string, unknown>)) as unknown as ApiResp
    if (res.code === 0) {
      ElMessage.success(t('auth.register.success'))
      router.push('/login')
    } else {
      // CRIT-5：所有错误统一 code=100，具体看 res.msg
      ElMessage.error(res.msg || t('auth.register.fail'))
    }
  } catch {
    ElMessage.error(t('auth.register.requestFail'))
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    const res = (await getSettings({ name: 'admin' } as unknown as Record<string, unknown>)) as unknown as SettingsResp
    if (res.register_status === 'off') router.replace('/login')
  } catch {
    // 静默：获取设置失败不影响注册主流程
  }
})
</script>

<style scoped>
/* REV33-M2: auth-page / auth-brand / brand-mark / brand-hero / brand-meta / brand-decor / auth-form-wrap 样式已抽到 AuthShell.vue
 * 本组件仅保留：表单专属样式 + brand 透传样式 + 注册场景特有样式（brand-steps / pwd-strength / agree-check）
 */

/* brand 透传样式（title/accent/desc）与注册流程步骤（brand-steps/step-*）已移至
 * index.css 全局区（.auth-brand 前缀）——:slotted 在当前构建链失效的修复，见 index.css 注释 */

/* =========================================
 *  右侧注册表单（表单专属样式）
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
  margin-bottom: 28px;
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

/* 表单输入行（输入框 + 按钮） */
.input-row {
  display: flex;
  gap: 10px;
  width: 100%;
  align-items: center;
}
.row-btn {
  flex-shrink: 0;
  min-width: 100px;
  font-weight: 500;
  letter-spacing: 0.04em;
}

/* ====== 密码强度计（注册场景特有） ====== */
.pwd-strength {
  margin-top: 10px;
}
.strength-track {
  width: 100%;
  height: 4px;
  background: var(--ogs-border-subtle);
  border-radius: 2px;
  overflow: hidden;
}
.strength-bar {
  height: 100%;
  border-radius: 2px;
  transition: width 0.25s ease, background 0.25s ease;
}
.strength-bar.lv-0 { background: #F43F5E; }
.strength-bar.lv-1 { background: #F97316; }
.strength-bar.lv-2 { background: #F59E0B; }
.strength-bar.lv-3 { background: #06B6D4; }
.strength-bar.lv-4 { background: linear-gradient(90deg, #10B981, #059669); }
.strength-text {
  margin-top: 6px;
  font-size: 11px;
  color: var(--ogs-text-muted);
  letter-spacing: 0.04em;
  font-weight: 500;
}
.strength-text span {
  font-weight: 600;
  margin-left: 2px;
}
.strength-text.lv-0 span { color: #F43F5E; }
.strength-text.lv-1 span { color: #F97316; }
.strength-text.lv-2 span { color: #F59E0B; }
.strength-text.lv-3 span { color: #06B6D4; }
.strength-text.lv-4 span { color: #10B981; }

/* 密码不一致提示 */
.match-hint {
  font-size: 11px;
  color: #F43F5E;
  margin-top: 6px;
  letter-spacing: 0.02em;
}

/* 服务条款 */
.agree-check {
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 4px;
}
.agree-text {
  font-size: 12px;
  color: var(--ogs-text-secondary);
  line-height: 1.6;
  letter-spacing: 0.01em;
}
.agree-text a {
  color: var(--ogs-primary);
  text-decoration: none;
  font-weight: 500;
}
.agree-text a:hover { text-decoration: underline; }

.submit-btn {
  width: 100%;
  height: 44px;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.1em;
  margin-top: 8px;
}

.form-footer {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 6px;
  margin-top: 20px;
}
.footer-text {
  font-size: 13px;
  color: var(--ogs-text-secondary);
}
.footer-link {
  font-size: 13px;
  color: var(--ogs-primary);
  text-decoration: none;
  font-weight: 600;
  transition: opacity 0.15s;
}
.footer-link:hover { opacity: 0.75; }

.form-legal {
  margin-top: 28px;
  text-align: center;
  font-size: 12px;
  color: var(--ogs-text-muted);
  letter-spacing: 0.02em;
}

/* 黑主题 —— 由 AuthShell.vue 提供 */

/* REV33-M3: 服务条款 / 隐私政策弹窗内容 */
.legal-content {
  margin: 0;
  font-family: var(--ogs-mono, 'JetBrains Mono', 'Consolas', monospace);
  font-size: 12.5px;
  line-height: 1.8;
  color: var(--ogs-text);
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--ogs-bg-sunken, #f8f9fb);
  padding: 16px 18px;
  border-radius: 8px;
  max-height: 50vh;
  overflow-y: auto;
}
[data-theme="black"] .legal-content {
  background: #1a1a1a;
}

/* 注册表单字段间隔紧凑一点（字段多） */
.auth-form :deep(.el-form-item) { margin-bottom: 18px; }
</style>