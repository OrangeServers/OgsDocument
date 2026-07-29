<!--
  REV33-M2: AuthShell 鉴权页壳
  ----------------------------------------------------------------
  抽离 Login / Register 共用的双栏布局：
    - 左：品牌展示（带 slot [brand] 注入品牌特色内容：features/steps 等）
    - 右：表单容器（带 slot default 注入表单/弹窗）

  设计目标：
    1. Login/Register 各自只关心「左侧特色区」与「右侧表单」内容
    2. 共用样式（双栏、响应式、品牌色、装饰背景）一处维护
    3. 黑主题适配（[data-theme="black"]）自动生效
-->
<template>
  <div class="auth-page">
    <!-- 左侧品牌展示（slot 注入 Login.features / Register.steps 等） -->
    <div class="auth-brand">
      <div class="brand-mark">
        <img src="/juzi11.png" alt="OrangeServer" />
        <div class="brand-text">
          <span class="brand-name">OrangeServer</span>
          <span class="brand-sub">{{ $t('auth.brand.slogan') }}</span>
        </div>
      </div>

      <div class="brand-hero">
        <slot name="brand" />
      </div>

      <slot name="meta">
        <div class="brand-meta">
          <span class="meta-dot"></span>
          <span class="meta-text num">{{ metaText }}</span>
        </div>
      </slot>

      <!-- 装饰背景（CSS-only：grid + glow blur） -->
      <div class="brand-decor">
        <div class="grid"></div>
        <div class="glow g1"></div>
        <div class="glow g2"></div>
      </div>
    </div>

    <!-- 右侧表单容器 -->
    <div class="auth-form-wrap">
      <div class="auth-form">
        <slot />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  metaText?: string
}>(), {
  metaText: 'v2.0 · All systems operational',
})
</script>

<style scoped>
/* =========================================
 *  Layout: 双栏
 * ========================================= */
.auth-page {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 1.1fr 1fr;
  background: var(--ogs-bg);
  overflow: hidden;
}
@media (max-width: 880px) {
  .auth-page { grid-template-columns: 1fr; }
  .auth-brand { display: none; }
}

/* =========================================
 *  左侧品牌展示
 * ========================================= */
.auth-brand {
  position: relative;
  background: var(--ogs-sidebar-bg);
  color: var(--ogs-sidebar-text-strong);
  padding: 56px 64px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  overflow: hidden;
  isolation: isolate;
}
.brand-mark {
  display: flex;
  align-items: center;
  gap: 14px;
  position: relative;
  z-index: 2;
}
.brand-mark img {
  width: 40px; height: 40px;
  border-radius: 10px;
  box-shadow: 0 0 0 1px rgba(255,255,255,0.08), 0 6px 20px rgba(249, 115, 22, 0.3);
}
.brand-mark .brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}
.brand-mark .brand-name {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.005em;
}
.brand-mark .brand-sub {
  font-size: 11px;
  color: rgba(255,255,255,0.5);
  letter-spacing: 0.16em;
  text-transform: uppercase;
  margin-top: 3px;
  font-weight: 500;
}

.brand-hero {
  position: relative;
  z-index: 2;
  margin: 64px 0;
}

.brand-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  position: relative;
  z-index: 2;
}
.brand-meta .meta-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: #10B981;
  box-shadow: 0 0 8px rgba(16, 185, 129, 0.6);
}
.brand-meta .meta-text {
  font-size: 12px;
  color: rgba(255,255,255,0.5);
  letter-spacing: 0.04em;
}

/* 装饰 */
.brand-decor {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 1;
}
.brand-decor .grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(to right, rgba(255,255,255,0.025) 1px, transparent 1px),
    linear-gradient(to bottom, rgba(255,255,255,0.025) 1px, transparent 1px);
  background-size: 32px 32px;
  mask-image: radial-gradient(ellipse at center, black 0%, transparent 70%);
  -webkit-mask-image: radial-gradient(ellipse at center, black 0%, transparent 70%);
}
.brand-decor .glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
}
.brand-decor .g1 {
  width: 380px; height: 380px;
  top: -10%; right: -10%;
  background: rgba(249, 115, 22, 0.12);
}
.brand-decor .g2 {
  width: 500px; height: 500px;
  bottom: -20%; left: -10%;
  background: rgba(249, 115, 22, 0.06);
}

/* =========================================
 *  右侧表单容器
 * ========================================= */
.auth-form-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 32px;
}
.auth-form {
  width: 100%;
  max-width: 380px;
}

/* 黑主题 */
[data-theme="black"] .auth-form-wrap { background: var(--ogs-bg); }
[data-theme="black"] .auth-page { background: var(--ogs-bg); }
</style>