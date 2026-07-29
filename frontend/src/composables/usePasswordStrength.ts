// =====================================================================
// REV33-M2: 密码强度计算 composable
// ti3-TS: 加类型注解
// =====================================================================
// 抽离 Register.vue 中的 calcStrength 逻辑。
// 评级规则（0-5 分 → 0-4 等级）：
//   - 长度 ≥ 8        +1
//   - 长度 ≥ 12       +1
//   - 大小写混合       +1
//   - 含数字          +1
//   - 含特殊字符      +1
// 阈值：minLevel = 2（Register 要求 ≥ 2 才能注册）
// =====================================================================
import { t } from '@/i18n'
import { ref, watchEffect, toValue, type Ref, type MaybeRefOrGetter } from 'vue'

/** 密码强度评估结果 */
export interface PasswordStrength {
  level: number
  label: string
  percent: number
}

/**
 * 计算密码强度
 * @param pwd 密码字符串
 */
export function calcPasswordStrength(pwd: string | null | undefined): PasswordStrength {
  if (!pwd) return { level: 0, label: t('common.password.empty'), percent: 0 }
  let score = 0
  if (pwd.length >= 8) score++
  if (pwd.length >= 12) score++
  if (/[a-z]/.test(pwd) && /[A-Z]/.test(pwd)) score++
  if (/\d/.test(pwd)) score++
  if (/[^A-Za-z0-9]/.test(pwd)) score++
  const level = Math.min(4, Math.max(0, score - 1))
  const map: PasswordStrength[] = [
    { level: 0, label: t('common.password.weak'), percent: 18 },
    { level: 1, label: t('common.password.fair'), percent: 38 },
    { level: 2, label: t('common.password.medium'), percent: 60 },
    { level: 3, label: t('common.password.good'), percent: 82 },
    { level: 4, label: t('common.password.strong'), percent: 100 },
  ]
  return map[level] || map[0]!
}

/** usePasswordStrength 返回值 */
export interface UsePasswordStrengthReturn {
  strength: Ref<PasswordStrength>
}

/**
 * 密码强度 composable（接受 getter，兼容 ref / computed / form.value.path）
 * @param getter - 返回当前密码字符串的 ref/getter/值
 */
export function usePasswordStrength(getter: MaybeRefOrGetter<string>): UsePasswordStrengthReturn {
  const strength: Ref<PasswordStrength> = ref(calcPasswordStrength(toValue(getter) || ''))
  watchEffect(() => {
    const v: string = toValue(getter) || ''
    strength.value = calcPasswordStrength(v)
  })
  return {
    strength,
  }
}
