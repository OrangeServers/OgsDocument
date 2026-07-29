<template>
  <div class="setup-page">
    <header class="setup-brand">
      <img src="/juzi11.png" alt="OrangeServer">
      <div>
        <strong>OrangeServer</strong>
        <span>{{ $t('setup.subtitle') }}</span>
      </div>
    </header>

    <main class="setup-card">
      <el-steps :active="step" align-center class="setup-steps">
        <el-step v-for="key in STEP_KEYS" :key="key" :title="$t(`setup.steps.${key}`)" />
      </el-steps>

      <!-- 0 欢迎 / 令牌 -->
      <section v-show="step === 0" class="setup-panel">
        <h2>{{ $t('setup.welcome.title') }}</h2>
        <p class="setup-lead">
          {{ $t('setup.welcome.lead') }}
        </p>
        <el-alert type="info" :closable="false" class="setup-hint">
          <p>{{ $t('setup.welcome.tokenIntro') }}</p>
          <p>{{ $t('setup.welcome.tokenFromLogs') }}</p>
          <p>{{ $t('setup.welcome.tokenFromFile', { path: status?.token_file || '<data dir>/setup_token.txt' }) }}</p>
        </el-alert>
        <el-form label-position="top" class="setup-form">
          <el-form-item :label="$t('setup.welcome.tokenLabel')">
            <el-input
              v-model="form.token"
              :placeholder="$t('setup.welcome.tokenPlaceholder')"
              show-password
              @keydown.enter="verifyToken"
            />
          </el-form-item>
        </el-form>
      </section>

      <!-- 1 MySQL -->
      <section v-show="step === 1" class="setup-panel">
        <h2>{{ $t('setup.mysql.title') }}</h2>
        <p class="setup-lead">{{ $t('setup.mysql.lead') }}</p>
        <el-form label-position="top" class="setup-form setup-grid">
          <el-form-item :label="$t('setup.mysql.host')">
            <el-input v-model="form.mysql.host" :disabled="locked('OGS_MYSQL_HOST')" :placeholder="$t('setup.mysql.hostPlaceholder')" />
          </el-form-item>
          <el-form-item :label="$t('setup.mysql.port')">
            <el-input-number v-model="form.mysql.port" :min="1" :max="65535" :disabled="locked('OGS_MYSQL_PORT')" controls-position="right" />
          </el-form-item>
          <el-form-item :label="$t('setup.mysql.dbname')">
            <el-input v-model="form.mysql.dbname" :disabled="locked('OGS_MYSQL_DBNAME')" />
          </el-form-item>
          <el-form-item :label="$t('setup.mysql.user')">
            <el-input v-model="form.mysql.user" :disabled="locked('OGS_MYSQL_USER')" />
          </el-form-item>
          <el-form-item :label="$t('setup.mysql.password')" class="setup-span2">
            <el-input
              v-model="form.mysql.password"
              type="password"
              show-password
              :disabled="locked('OGS_MYSQL_PASSWORD')"
              :placeholder="locked('OGS_MYSQL_PASSWORD') ? $t('setup.lockedSecret') : ''"
            />
          </el-form-item>
        </el-form>
        <div class="setup-test">
          <el-button :loading="testing.mysql" @click="runMysqlTest">{{ $t('setup.mysql.testButton') }}</el-button>
          <span v-if="results.mysql" :class="results.mysql.ok ? 'is-ok' : 'is-bad'">
            {{ results.mysql.msg }}
            <template v-if="results.mysql.ok && results.mysql.db_exists">
              {{ $t('setup.mysql.dbExists') }}{{ results.mysql.has_tables ? $t('setup.mysql.dbExistsWithTables') : $t('setup.mysql.dbEmpty') }}
            </template>
          </span>
        </div>
      </section>

      <!-- 2 Redis -->
      <section v-show="step === 2" class="setup-panel">
        <h2>{{ $t('setup.redis.title') }}</h2>
        <p class="setup-lead">{{ $t('setup.redis.lead') }}</p>
        <el-form label-position="top" class="setup-form setup-grid">
          <el-form-item :label="$t('setup.redis.host')">
            <el-input v-model="form.redis.host" :disabled="locked('OGS_REDIS_HOST')" :placeholder="$t('setup.redis.hostPlaceholder')" />
          </el-form-item>
          <el-form-item :label="$t('setup.redis.port')">
            <el-input-number v-model="form.redis.port" :min="1" :max="65535" :disabled="locked('OGS_REDIS_PORT')" controls-position="right" />
          </el-form-item>
          <el-form-item :label="$t('setup.redis.password')">
            <el-input
              v-model="form.redis.password"
              type="password"
              show-password
              :disabled="locked('OGS_REDIS_PASSWORD')"
              :placeholder="locked('OGS_REDIS_PASSWORD') ? $t('setup.lockedSecret') : ''"
            />
          </el-form-item>
          <el-form-item :label="$t('setup.redis.db')">
            <el-input-number v-model="form.redis.db" :min="0" :max="15" :disabled="locked('OGS_REDIS_DB')" controls-position="right" />
          </el-form-item>
        </el-form>
        <div class="setup-test">
          <el-button :loading="testing.redis" @click="runRedisTest">{{ $t('setup.mysql.testButton') }}</el-button>
          <span v-if="results.redis" :class="results.redis.ok ? 'is-ok' : 'is-bad'">{{ results.redis.msg }}</span>
        </div>
      </section>

      <!-- 3 安全密钥 -->
      <section v-show="step === 3" class="setup-panel">
        <h2>{{ $t('setup.secrets.title') }}</h2>
        <p class="setup-lead">
          {{ $t('setup.secrets.lead') }}
        </p>
        <el-collapse class="setup-advanced">
          <el-collapse-item :title="$t('setup.secrets.advanced')" name="adv">
            <el-form label-position="top" class="setup-form">
              <el-form-item :label="$t('setup.secrets.secretKeyLabel')">
                <el-input v-model="form.secrets.secret_key" type="password" show-password />
              </el-form-item>
              <el-form-item :label="$t('setup.secrets.fernetKeyLabel')">
                <el-input v-model="form.secrets.fernet_key" type="password" show-password />
              </el-form-item>
            </el-form>
          </el-collapse-item>
        </el-collapse>
      </section>

      <!-- 4 管理员 -->
      <section v-show="step === 4" class="setup-panel">
        <h2>{{ $t('setup.admin.title') }}</h2>
        <p class="setup-lead">
          {{ $t('setup.admin.lead') }}
        </p>
        <el-form label-position="top" class="setup-form setup-grid">
          <el-form-item :label="$t('setup.admin.username')">
            <el-input v-model="form.admin.username" :placeholder="$t('setup.admin.usernamePlaceholder')" />
          </el-form-item>
          <el-form-item :label="$t('setup.admin.email')">
            <el-input v-model="form.admin.email" :placeholder="$t('setup.admin.emailPlaceholder')" />
          </el-form-item>
          <el-form-item :label="$t('setup.admin.password')">
            <el-input v-model="form.admin.password" type="password" show-password />
          </el-form-item>
          <el-form-item :label="$t('setup.admin.confirm')">
            <el-input v-model="form.admin.confirm" type="password" show-password />
          </el-form-item>
        </el-form>
      </section>

      <!-- 5 可选设置 -->
      <section v-show="step === 5" class="setup-panel">
        <h2>{{ $t('setup.mail.title') }}</h2>
        <p class="setup-lead">{{ $t('setup.mail.lead') }}</p>
        <el-form label-position="top" class="setup-form">
          <el-form-item :label="$t('setup.mail.configure')">
            <el-switch v-model="form.mail.enabled" :active-text="$t('setup.mail.configureOn')" :inactive-text="$t('setup.mail.configureOff')" />
          </el-form-item>
          <template v-if="form.mail.enabled">
            <el-form-item :label="$t('setup.mail.preset')">
              <el-radio-group v-model="form.mail.preset" @change="applyMailPreset">
                <el-radio-button value="126">126</el-radio-button>
                <el-radio-button value="163">163</el-radio-button>
                <el-radio-button value="qq">QQ</el-radio-button>
                <el-radio-button value="custom">{{ $t('setup.mail.custom') }}</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <div class="setup-grid">
              <el-form-item :label="$t('setup.mail.host')">
                <el-input v-model="form.mail.smtp_host" :disabled="form.mail.preset !== 'custom'" placeholder="smtp.example.com" />
              </el-form-item>
              <el-form-item :label="$t('setup.mail.port')">
                <el-input-number v-model="form.mail.smtp_port" :min="1" :max="65535" :disabled="form.mail.preset !== 'custom'" controls-position="right" />
              </el-form-item>
              <el-form-item :label="$t('setup.mail.security')">
                <el-select v-model="form.mail.security" :disabled="form.mail.preset !== 'custom'">
                  <el-option value="ssl" :label="$t('setup.mail.ssl')" />
                  <el-option value="starttls" :label="$t('setup.mail.starttls')" />
                  <el-option value="none" :label="$t('setup.mail.none')" />
                </el-select>
              </el-form-item>
              <el-form-item :label="$t('setup.mail.fromEmail')">
                <el-input v-model="form.mail.from_email" placeholder="name@example.com" />
              </el-form-item>
              <el-form-item :label="$t('setup.mail.password')">
                <el-input v-model="form.mail.password" type="password" show-password :placeholder="$t('setup.mail.passwordPlaceholder')" />
              </el-form-item>
              <el-form-item :label="$t('setup.mail.testRecipient')">
                <el-input v-model="form.mail.send_to" placeholder="test@example.com" />
              </el-form-item>
            </div>
            <div class="setup-test">
              <el-button :loading="testing.smtp" @click="runSmtpTest">{{ $t('setup.mail.testButton') }}</el-button>
              <span v-if="results.smtp" :class="results.smtp.ok ? 'is-ok' : 'is-bad'">{{ results.smtp.msg }}</span>
            </div>
          </template>
        </el-form>
      </section>

      <!-- 6 可选设置 -->
      <section v-show="step === 6" class="setup-panel">
        <h2>{{ $t('setup.optional.title') }}</h2>
        <p class="setup-lead">{{ $t('setup.optional.lead') }}</p>
        <el-form label-position="top" class="setup-form">
          <el-form-item :label="$t('setup.optional.systemName')">
            <el-input v-model="form.settings.system_name" placeholder="OrangeServer" />
          </el-form-item>
          <el-form-item :label="$t('setup.optional.registerOpen')">
            <el-switch v-model="registerOpen" :active-text="$t('setup.optional.registerOpenText')" />
          </el-form-item>
          <el-form-item :label="$t('setup.optional.loginNotice')">
            <el-input v-model="form.settings.login_notice" type="textarea" :rows="2" :placeholder="$t('setup.optional.loginNoticePlaceholder')" />
          </el-form-item>
        </el-form>
      </section>

      <!-- 7 确认与应用 -->
      <section v-show="step === 7" class="setup-panel">
        <template v-if="phase === 'review'">
          <h2>{{ $t('setup.review.title') }}</h2>
          <dl class="setup-summary">
            <div><dt>{{ $t('setup.review.mysql') }}</dt><dd>{{ form.mysql.user }}@{{ form.mysql.host }}:{{ form.mysql.port }}/{{ form.mysql.dbname }}</dd></div>
            <div><dt>{{ $t('setup.review.redis') }}</dt><dd>{{ form.redis.host }}:{{ form.redis.port }} · db{{ form.redis.db }}</dd></div>
            <div><dt>{{ $t('setup.review.secrets') }}</dt><dd>{{ form.secrets.secret_key || form.secrets.fernet_key ? $t('setup.review.secretsCustom') : $t('setup.review.secretsAuto') }}</dd></div>
            <div><dt>{{ $t('setup.review.admin') }}</dt><dd>{{ form.admin.username }}{{ form.admin.email ? ' · ' + form.admin.email : '' }}</dd></div>
            <div><dt>{{ $t('setup.review.smtp') }}</dt><dd>{{ form.mail.enabled ? form.mail.from_email + ' · ' + form.mail.smtp_host + ':' + form.mail.smtp_port : $t('setup.review.smtpSkipped') }}</dd></div>
            <div><dt>{{ $t('setup.review.systemName') }}</dt><dd>{{ form.settings.system_name || 'OrangeServer' }}</dd></div>
            <div><dt>{{ $t('setup.review.registerOpen') }}</dt><dd>{{ registerOpen ? $t('common.yes') : $t('common.no') }}</dd></div>
          </dl>
          <el-alert type="warning" :closable="false" class="setup-hint">
            {{ $t('setup.review.warning') }}
          </el-alert>
        </template>

        <template v-else>
          <h2>{{ phase === 'restarting' ? $t('setup.progress.applying') : phase === 'done' ? $t('setup.progress.done') : $t('setup.progress.failed') }}</h2>
          <ul v-if="applySteps.length" class="setup-steps-log">
            <li v-for="item in applySteps" :key="item.name" :class="item.ok ? 'is-ok' : 'is-bad'">
              <el-icon v-if="item.ok"><CircleCheckFilled /></el-icon>
              <el-icon v-else><WarningFilled /></el-icon>
              <span>{{ item.msg || item.name }}</span>
            </li>
          </ul>
          <div v-if="phase === 'restarting'" class="setup-restart">
            <el-icon class="is-loading"><Loading /></el-icon>
            {{ $t('setup.progress.restarting', { n: restartSeconds }) }}
          </div>
          <el-alert v-if="phase === 'done'" type="success" :closable="false" class="setup-hint">
            {{ $t('setup.progress.doneHint') }}
          </el-alert>
          <el-alert v-if="phase === 'failed'" type="error" :closable="false" class="setup-hint">
            <p>{{ failMessage }}</p>
            <p v-if="restartTimedOut">{{ $t('setup.progress.troubleshoot') }}</p>
          </el-alert>
        </template>
      </section>

      <footer class="setup-actions">
        <el-button v-if="step > 0 && phase === 'review'" @click="step -= 1">{{ $t('common.action.prev') }}</el-button>
        <span class="setup-actions-spacer" />
        <el-button
          v-if="phase === 'review' && step < 7"
          type="primary"
          :loading="verifying"
          @click="next"
        >{{ step === 0 ? $t('setup.welcome.startButton') : $t('common.action.next') }}</el-button>
        <el-button
          v-if="phase === 'review' && step === 7"
          type="primary"
          :loading="applying"
          @click="apply"
        >{{ $t('setup.review.applyButton') }}</el-button>
        <el-button v-if="phase === 'failed' && !restartTimedOut" @click="phase = 'review'">{{ $t('setup.progress.backButton') }}</el-button>
      </footer>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { CircleCheckFilled, Loading, WarningFilled } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { t } from '@/i18n'
import {
  applySetup,
  getSetupPrefill,
  getSetupStatus,
  setSetupToken,
  testMysql,
  testRedis,
  testSmtp,
  verifySetupToken,
  type SetupCheckResult,
  type SetupStatus,
  type SetupStep,
} from '@/api/setup'

const STEP_KEYS = ['welcome', 'mysql', 'redis', 'secrets', 'admin', 'mail', 'optional', 'apply'] as const
const MAIL_PRESETS = {
  '126': { smtp_host: 'smtp.126.com', smtp_port: 465, security: 'ssl' },
  '163': { smtp_host: 'smtp.163.com', smtp_port: 465, security: 'ssl' },
  qq: { smtp_host: 'smtp.qq.com', smtp_port: 465, security: 'ssl' },
} as const

const router = useRouter()
const step = ref(0)
const phase = ref<'review' | 'restarting' | 'done' | 'failed'>('review')
const status = ref<SetupStatus | null>(null)
const verifying = ref(false)
const applying = ref(false)
const testing = reactive({ mysql: false, redis: false, smtp: false })
const results = reactive<{ mysql: SetupCheckResult | null; redis: SetupCheckResult | null; smtp: SetupCheckResult | null }>({
  mysql: null,
  redis: null,
  smtp: null,
})
const applySteps = ref<SetupStep[]>([])
const failMessage = ref('')
const restartSeconds = ref(0)
const restartTimedOut = ref(false)
let restartTimer: ReturnType<typeof setInterval> | null = null

const form = reactive({
  token: '',
  mysql: { host: '', port: 3306, dbname: 'orange', user: '', password: '' },
  redis: { host: '', port: 6379, password: '', db: 0 },
  secrets: { secret_key: '', fernet_key: '' },
  admin: { username: '', password: '', confirm: '', email: '' },
  mail: { enabled: false, preset: '126' as keyof typeof MAIL_PRESETS | 'custom', smtp_host: 'smtp.126.com', smtp_port: 465, security: 'ssl' as 'ssl' | 'starttls' | 'none', from_email: '', password: '', send_to: '' },
  settings: { system_name: '', register_status: 'off', login_notice: '' },
})
const registerOpen = computed({
  get: () => form.settings.register_status === 'on',
  set: value => { form.settings.register_status = value ? 'on' : 'off' },
})

function locked(key: string): boolean {
  return Boolean(status.value?.env_locked?.includes(key))
}

async function loadStatus(): Promise<void> {
  try {
    status.value = await getSetupStatus()
    if (status.value.mode === 'normal') {
      // 已配置系统不展示向导，只此一跳
      void router.replace('/login')
    }
  } catch {
    // 后端未就绪：留在向导页，用户可稍后重试第一步
  }
}

async function verifyToken(): Promise<void> {
  const token = form.token.trim()
  if (!token) {
    ElMessage.warning(t('setup.welcome.tokenRequired'))
    return
  }
  verifying.value = true
  try {
    const ok = await verifySetupToken(token)
    if (!ok) {
      ElMessage.error(t('setup.welcome.tokenInvalid'))
      return
    }
    setSetupToken(token)
    const prefill = await getSetupPrefill()
    Object.assign(form.mysql, {
      host: prefill.mysql.host,
      port: prefill.mysql.port,
      dbname: prefill.mysql.dbname,
      user: prefill.mysql.user,
    })
    Object.assign(form.redis, {
      host: prefill.redis.host,
      port: prefill.redis.port,
      db: prefill.redis.db,
    })
    step.value = 1
  } finally {
    verifying.value = false
  }
}

async function runMysqlTest(): Promise<void> {
  testing.mysql = true
  try {
    results.mysql = await testMysql({ ...form.mysql })
  } finally {
    testing.mysql = false
  }
}

async function runRedisTest(): Promise<void> {
  testing.redis = true
  try {
    results.redis = await testRedis({ ...form.redis })
  } finally {
    testing.redis = false
  }
}

function applyMailPreset(): void {
  if (form.mail.preset === 'custom') return
  Object.assign(form.mail, MAIL_PRESETS[form.mail.preset])
  results.smtp = null
}

watch(
  () => [
    form.mail.smtp_host,
    form.mail.smtp_port,
    form.mail.security,
    form.mail.from_email,
    form.mail.password,
    form.mail.send_to,
  ],
  () => { results.smtp = null },
)

function mailPayload(includeRecipient = false): { smtp_host: string; smtp_port: number; security: 'ssl' | 'starttls' | 'none'; from_email: string; password: string; send_to?: string } {
  return {
    smtp_host: form.mail.smtp_host.trim(), smtp_port: form.mail.smtp_port, security: form.mail.security,
    from_email: form.mail.from_email.trim(), password: form.mail.password,
    ...(includeRecipient && form.mail.send_to.trim() ? { send_to: form.mail.send_to.trim() } : {}),
  }
}

async function runSmtpTest(): Promise<void> {
  testing.smtp = true
  try {
    results.smtp = await testSmtp(mailPayload(true))
  } finally {
    testing.smtp = false
  }
}

async function next(): Promise<void> {
  if (step.value === 0) {
    await verifyToken()
    return
  }
  if (step.value === 1) {
    if (!results.mysql?.ok) {
      await runMysqlTest()
      if (!results.mysql?.ok) {
        ElMessage.warning(t('setup.mysql.testFirst'))
        return
      }
    }
  }
  if (step.value === 2) {
    if (!results.redis?.ok) {
      await runRedisTest()
      if (!results.redis?.ok) {
        ElMessage.warning(t('setup.redis.testFirst'))
        return
      }
    }
  }
  if (step.value === 4) {
    if (!form.admin.username.trim() || form.admin.username.trim() === 'system') {
      ElMessage.warning(t('setup.admin.usernameInvalid'))
      return
    }
    if (form.admin.password.length < 8) {
      ElMessage.warning(t('setup.admin.passwordTooShort'))
      return
    }
    if (form.admin.password !== form.admin.confirm) {
      ElMessage.warning(t('setup.admin.passwordMismatch'))
      return
    }
  }
  if (step.value === 5 && form.mail.enabled) {
    if (!results.smtp?.ok) {
      await runSmtpTest()
      if (!results.smtp?.ok) {
        ElMessage.warning(t('setup.mail.testFirst'))
        return
      }
    }
  }
  step.value += 1
}

async function apply(): Promise<void> {
  applying.value = true
  applySteps.value = []
  try {
    const result = await applySetup({
      mysql: { ...form.mysql },
      redis: { ...form.redis },
      admin: {
        username: form.admin.username.trim(),
        password: form.admin.password,
        email: form.admin.email.trim(),
      },
      secrets: {
        secret_key: form.secrets.secret_key || undefined,
        fernet_key: form.secrets.fernet_key || undefined,
      },
      settings: {
        system_name: form.settings.system_name.trim() || undefined,
        register_status: form.settings.register_status,
        login_notice: form.settings.login_notice.trim() || undefined,
      },
      ...(form.mail.enabled ? { mail: mailPayload() } : {}),
    })
    applySteps.value = result.steps || []
    if (!result.ok) {
      phase.value = 'failed'
      failMessage.value = result.msg || t('setup.progress.failedFallback')
      return
    }
    phase.value = 'restarting'
    startRestartPolling()
  } finally {
    applying.value = false
  }
}

function startRestartPolling(): void {
  restartSeconds.value = 0
  restartTimedOut.value = false
  restartTimer = setInterval(async () => {
    restartSeconds.value += 2
    try {
      const current = await getSetupStatus()
      if (current.mode === 'normal') {
        stopRestartPolling()
        phase.value = 'done'
        setTimeout(() => { void router.replace('/login') }, 3000)
        return
      }
      if (current.mode === 'maintenance') {
        stopRestartPolling()
        phase.value = 'failed'
        restartTimedOut.value = true
        failMessage.value = t('setup.progress.maintenanceError', { error: current.error || t('setup.progress.unknownError') })
        return
      }
      if (current.mode === 'setup' && restartSeconds.value >= 20) {
        stopRestartPolling()
        phase.value = 'failed'
        restartTimedOut.value = true
        failMessage.value = t('setup.progress.stillSetup')
        return
      }
    } catch {
      // 网络错误/502/504 视为重启中，继续轮询
    }
    if (restartSeconds.value >= 90) {
      stopRestartPolling()
      phase.value = 'failed'
      restartTimedOut.value = true
      failMessage.value = t('setup.progress.timeout')
    }
  }, 2000)
}

function stopRestartPolling(): void {
  if (restartTimer) {
    clearInterval(restartTimer)
    restartTimer = null
  }
}

onMounted(loadStatus)
onBeforeUnmount(stopRestartPolling)
</script>

<style scoped>
.setup-page {
  min-height: 100vh;
  padding: 32px 16px 48px;
  background: var(--ogs-bg);
  box-sizing: border-box;
}
.setup-brand {
  max-width: 860px;
  margin: 0 auto 20px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.setup-brand img { width: 40px; height: 40px; object-fit: contain; }
.setup-brand strong { display: block; color: var(--ogs-text); font-size: 18px; }
.setup-brand span { display: block; color: var(--ogs-text-muted); font-size: 12px; }
.setup-card {
  max-width: 860px;
  margin: 0 auto;
  padding: 26px 30px 22px;
  border: 1px solid var(--ogs-border);
  border-radius: var(--ogs-radius);
  background: var(--ogs-surface);
  box-shadow: var(--ogs-shadow);
}
.setup-steps { margin-bottom: 26px; }
.setup-panel h2 { color: var(--ogs-text); font-size: 18px; }
.setup-lead {
  margin: 8px 0 18px;
  color: var(--ogs-text-secondary);
  font-size: 13px;
  line-height: 1.7;
}
.setup-hint { margin-bottom: 16px; line-height: 1.7; }
.setup-hint code { font-family: var(--ogs-mono); font-size: 12px; }
.setup-form { max-width: 640px; }
.setup-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 18px;
}
.setup-span2 { grid-column: 1 / -1; }
.setup-test {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
}
.setup-test .is-ok { color: var(--ogs-success); }
.setup-test .is-bad { color: var(--ogs-danger); }
.setup-advanced { max-width: 640px; }
.setup-summary {
  margin: 0 0 16px;
  border: 1px solid var(--ogs-border);
  border-radius: var(--ogs-radius-sm);
  overflow: hidden;
}
.setup-summary > div {
  display: grid;
  grid-template-columns: 120px 1fr;
  padding: 10px 14px;
  border-bottom: 1px solid var(--ogs-border-subtle);
  font-size: 13px;
}
.setup-summary > div:last-child { border-bottom: 0; }
.setup-summary dt { color: var(--ogs-text-muted); }
.setup-summary dd { margin: 0; color: var(--ogs-text); font-family: var(--ogs-mono); overflow-wrap: anywhere; }
.setup-steps-log {
  margin: 0 0 16px;
  padding: 0;
  list-style: none;
}
.setup-steps-log li {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
  color: var(--ogs-text-secondary);
}
.setup-steps-log li .el-icon { margin-top: 2px; }
.setup-steps-log .is-ok .el-icon { color: var(--ogs-success); }
.setup-steps-log .is-bad { color: var(--ogs-danger); }
.setup-restart {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  color: var(--ogs-text-secondary);
  font-size: 13px;
}
.setup-actions {
  display: flex;
  align-items: center;
  margin-top: 22px;
  padding-top: 16px;
  border-top: 1px solid var(--ogs-border-subtle);
}
.setup-actions-spacer { flex: 1; }

@media (max-width: 720px) {
  .setup-card { padding: 18px 14px; }
  .setup-grid { grid-template-columns: 1fr; }
  .setup-steps :deep(.el-step__title) { font-size: 11px; }
}
</style>
