// =====================================================================
// REV35-L2: useClipboard composable — 5+ view 共用复制功能
// ti3-TS: 加类型注解
// =====================================================================
// 抽离 copyText 模式：navigator.clipboard 优先 + textarea fallback 兜底
//
// 用法:
//   import { useClipboard } from '@/composables/useClipboard'
//   const { copy } = useClipboard()
//   copy('some text', msg)  // 第二参数可选，默认 t('common.copySuccess')
//
// 注：useLogTable.js 与 Cron.vue 原内联 copyText 已被替换为本 composable
// =====================================================================
import { ElMessage } from 'element-plus'
import { t } from '@/i18n'

/**
 * 写入剪贴板（带 fallback）
 * @param text 要复制的文本
 * @param successMsg 成功提示文案，默认 '已复制'
 */
function _copyImpl(text: string, successMsg: string = ''): void {
  if (!successMsg) successMsg = t('common.copySuccess')
  if (!text) return
  const fallback = (): void => {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.cssText = 'position:fixed;opacity:0'
    document.body.appendChild(ta)
    ta.select()
    try { document.execCommand('copy'); ElMessage.success(successMsg) }
    catch { ElMessage.warning(t('common.copyFail')) }
    finally { document.body.removeChild(ta) }
  }
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(() => ElMessage.success(successMsg), fallback)
  } else {
    fallback()
  }
}

/** useClipboard 返回值 */
export interface UseClipboardReturn {
  copy: (text: string, successMsg?: string) => void
}

/**
 * 复制 composable
 */
export function useClipboard(): UseClipboardReturn {
  return {
    copy: _copyImpl,
  }
}
