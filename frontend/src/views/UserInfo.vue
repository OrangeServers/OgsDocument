<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <span class="page-eyebrow">PROFILE</span>
        <h2>{{ $t('settings.profile.title') }}</h2>
        <p>{{ $t('settings.profile.subtitle') }} · <span class="num">{{ $t('settings.profile.subtitleNote') }}</span></p>
      </div>
    </div>

    <div class="panel" style="max-width:720px">
      <div class="panel-head">
        <span class="panel-icon"><el-icon :size="14"><User /></el-icon></span>
        <span class="panel-title">{{ $t('settings.profile.panelTitle') }}</span>
        <span class="panel-sub">Account Profile</span>
      </div>
      <div class="panel-body">
        <!-- 头像身份卡 -->
        <div class="profile-card">
          <el-avatar :size="68" :src="store.user.avatar" class="profile-avatar" />
          <div class="profile-meta">
            <div class="profile-name">{{ store.user.alias || store.user.username }}</div>
            <div class="profile-handle">@{{ store.user.username }}</div>
            <div class="profile-tags">
              <span :class="['role-tag', roleClass(store.user.role || 'user')]">{{ roleLabel(store.user.role || 'user') }}</span>
              <span v-if="store.user.group" :class="['group-tag', groupTagClass(store.user.group)]">{{ store.user.group }}</span>
            </div>
          </div>
          <el-upload
            :show-file-list="false"
            :before-upload="beforeAvatarUpload"
            :http-request="uploadAvatarHandler"
            accept=".jpg,.jpeg,.png"
          >
            <el-button size="small" type="primary" plain>
              <el-icon :size="13"><Upload /></el-icon>{{ $t('settings.profile.changeAvatar') }}
            </el-button>
          </el-upload>
        </div>

        <el-form ref="formRef" :model="form" :rules="rules" label-width="100px" label-position="right" class="profile-form">
          <div class="form-section">
            <div class="form-section-title">{{ $t('settings.profile.sectionBasic') }}</div>
            <el-form-item label="ID">
              <el-input v-model="form.id" disabled />
            </el-form-item>
            <el-form-item :label="$t('settings.profile.alias')" prop="alias">
              <el-input v-model="form.alias" :placeholder="$t('settings.profile.aliasPlaceholder')" />
            </el-form-item>
            <el-form-item :label="$t('settings.profile.username')">
              <el-input v-model="form.name" disabled />
            </el-form-item>
            <el-form-item :label="$t('settings.profile.mail')" prop="mail">
              <el-input v-model="form.mail" :placeholder="$t('settings.profile.mailPlaceholder')" />
            </el-form-item>
          </div>

          <div class="form-section">
            <div class="form-section-title">{{ $t('settings.profile.sectionRole') }}</div>
            <el-form-item :label="$t('settings.profile.role')">
              <span :class="['role-tag', roleClass(form.usrole || 'user')]">{{ roleLabel(form.usrole || 'user') }}</span>
            </el-form-item>
            <el-form-item :label="$t('settings.profile.group')">
              <el-select v-model="form.group" :placeholder="$t('settings.profile.groupPlaceholder')" style="width:100%">
                <el-option v-for="g in groups" :key="g" :label="g" :value="g" />
              </el-select>
            </el-form-item>
          </div>

          <div class="form-section">
            <div class="form-section-title">{{ $t('settings.profile.sectionSecurity') }}</div>
            <el-form-item :label="$t('settings.profile.newPassword')" prop="password">
              <el-input v-model="form.password" type="password" show-password :placeholder="$t('settings.profile.passwordPlaceholder')" />
            </el-form-item>
            <el-form-item :label="$t('settings.profile.remarks')">
              <el-input v-model="form.remarks" :placeholder="$t('settings.profile.remarksPlaceholder')" />
            </el-form-item>
          </div>

          <el-form-item class="form-actions">
            <el-button type="primary" @click="save" :loading="saving">{{ $t('settings.profile.submit') }}</el-button>
            <el-button @click="loadForm">{{ $t('common.action.reset') }}</el-button>
          </el-form-item>
        </el-form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import { t } from '@/i18n'
import { getUserAlias, getUserInfo, updateUserInfo, getGroupNameList, uploadAvatar } from '@/api'
import { store, loadUserInfo } from '@/store'
import { groupTagClass } from '@/utils/groupClassifier'
import type { UploadRawFile, UploadRequestOptions } from 'element-plus'

/** 用户资料表单 */
interface UserInfoForm {
  id: string
  alias: string
  name: string
  password: string
  mail: string
  usrole: string
  group: string
  remarks: string
}

/** getUserInfo 响应 */
interface UserInfoResponse {
  code: number
  id?: string
  alias?: string
  name?: string
  mail?: string
  usrole?: string
  group?: string
  remarks?: string
  [k: string]: unknown
}

const saving = ref(false)
const formRef = ref<{ validate: () => Promise<boolean> } | null>(null)
const groups = ref<string[]>([])
const form = ref<UserInfoForm>({ id: '', alias: '', name: '', password: '', mail: '', usrole: '', group: '', remarks: '' })
// computed：校验提示随语言切换即时更新
const rules = computed(() => ({
  alias: [{ required: true, message: t('settings.profile.rules.aliasRequired'), trigger: 'blur' }],
  mail: [{ required: true, message: t('settings.profile.rules.mailRequired'), trigger: 'blur' }],
}))

function roleClass(role: string): string {
  if (role === 'admin') return 'is-admin'
  if (role === 'audit') return 'is-audit'
  if (role === 'user') return 'is-user'
  return 'is-default'
}
function roleLabel(role: string): string {
  if (role === 'admin') return t('settings.profile.roles.admin')
  if (role === 'audit') return t('settings.profile.roles.audit')
  if (role === 'user') return t('settings.profile.roles.user')
  return t('settings.profile.roles.unknown')
}
// REV35-L5: groupTagClass 已抽到 utils/groupClassifier.js

async function loadForm(): Promise<void> {
  try {
    // 获取当前用户名
    const aliasRes = (await getUserAlias()) as unknown as { username: string }
    const username = aliasRes.username
    // 旧代码: POST /account/user/list, {user_type:'user_info', name:username}
    const res = (await getUserInfo({ user_type: 'user_info', name: username })) as unknown as UserInfoResponse
    // CRIT-5：判断成功的标准变为 code === 0（原 code !== 201）
    // UI修复：后端 user_info 直接返回用户行 dict（无 code 字段），单凭 res.code === 0
    //   会判失败导致整个表单不填充（权限标签误显示"普通用户"、各字段为空）。
    //   兼容以用户 id 存在作为成功判据。
    if (res.code === 0 || res.id != null) {
      form.value = {
        id: res.id || '',
        alias: res.alias || '',
        name: res.name || '',
        password: '',
        mail: res.mail || '',
        usrole: res.usrole || '',
        group: res.group || '',
        remarks: res.remarks || '',
      }
      // 加载用户组列表
      try {
        const gRes = (await getGroupNameList()) as unknown as { code: number; group_name_list_msg?: string[] }
        if (gRes.code === 0) groups.value = gRes.group_name_list_msg || []
      } catch (_) { /* 静默 */ }
    }
  } catch (_) { /* 静默 */ }
}

async function save(): Promise<void> {
  await formRef.value?.validate()
  saving.value = true
  try {
    // 旧代码: POST /account/user/update, 表单序列化
    await updateUserInfo(form.value as unknown as Record<string, unknown>)
    ElMessage.success(t('settings.profile.msg.saveSuccess'))
    await loadUserInfo()
  } catch (_) { ElMessage.error(t('settings.profile.msg.saveFail')) }
  finally { saving.value = false }
}

// REV34-M10: 头像大小限制 2MB（前端 UX 拦截）
//   后端 Basics._MAX_UPLOAD_IMG_SIZE 限 5MB，前后端双层防御
const _MAX_AVATAR_SIZE = 2 * 1024 * 1024  // 2MB
function beforeAvatarUpload(file: UploadRawFile): boolean {
  const isImage = ['image/jpeg', 'image/png'].includes(file.type)
  if (!isImage) {
    ElMessage.error(t('settings.profile.msg.avatarType'))
    return false
  }
  if (file.size > _MAX_AVATAR_SIZE) {
    const sizeMB = (file.size / 1024 / 1024).toFixed(1)
    ElMessage.error(t('settings.profile.msg.avatarSize', { size: sizeMB }))
    return false
  }
  return true
}

async function uploadAvatarHandler(opts: UploadRequestOptions): Promise<void> {
  const file = opts.file as UploadRawFile
  const fd = new FormData()
  fd.append('file', file)
  fd.append('user', store.user.username)
  try {
    await uploadAvatar(fd)
    ElMessage.success(t('settings.profile.msg.avatarSuccess'))
  } catch (_) {
    ElMessage.error(t('settings.profile.msg.avatarFail'))
  }
}

onMounted(loadForm)
</script>
