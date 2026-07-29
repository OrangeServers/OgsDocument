// I18N: 让全局 $t / useI18n().t 的 key 获得编译期检查（schema 源 = zh-CN）
import type { MessageSchema } from './index'

declare module 'vue-i18n' {
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type
  export interface DefineLocaleMessage extends MessageSchema {}
}
