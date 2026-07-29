<template>
  <!-- I18N: el-config-provider 让 Element Plus 内建文案随语言切换；
       App.vue 是唯一同时覆盖 Layout 与 noLayout 路由（登录/注册/远程会话/setup）的挂点 -->
  <el-config-provider :locale="epLocale">
    <router-view />
  </el-config-provider>
</template>

<script setup lang="ts">
import { appInit } from '@/api'
import { epLocale } from '@/i18n'

// /local/status 是登录态接口；匿名首访不应制造预期内的 401 控制台错误。
// 登录态整页刷新时 csrf_token 可见，再执行状态探测。
const hasSessionCookie = document.cookie
  .split('; ')
  .some((item) => item.startsWith('csrf_token='))
if (hasSessionCookie) appInit().catch(() => { /* 状态探测失败不阻断页面 */ })
</script>
