<script setup lang="ts">
import DefaultTheme from 'vitepress/theme'
import { useData } from 'vitepress'
import { computed } from 'vue'
import TermMock from './components/TermMock.vue'
import HeroExtras from './components/HeroExtras.vue'
import FeaturesGrid from './components/FeaturesGrid.vue'
import AiSection from './components/AiSection.vue'
import ScreensGallery from './components/ScreensGallery.vue'
import HomeCta from './components/HomeCta.vue'

const { Layout } = DefaultTheme
const { lang } = useData()
const isZh = computed(() => lang.value === 'zh-CN')
</script>

<template>
  <Layout>
    <template #home-hero-info-before>
      <p class="hero-eyebrow">
        {{ isZh ? '自托管 · 开源 · Apache-2.0' : 'Self-hosted · Open source · Apache-2.0' }}
      </p>
    </template>
    <template #home-hero-image>
      <TermMock />
    </template>
    <template #home-hero-actions-after>
      <HeroExtras />
    </template>
    <template #home-features-before>
      <FeaturesGrid />
    </template>
    <template #home-features-after>
      <AiSection />
      <ScreensGallery />
      <HomeCta />
    </template>
  </Layout>
</template>
