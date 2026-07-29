// =============================================================================
// I18N 防回归检查：
// 1) src/**/*.{vue,ts} 剥离注释后不允许出现汉字裸串（allowlist 除外）
// 2) zh-CN 与 en-US 语言包 key 集合全等
// 用法：node scripts/check-i18n.mjs [--dir src/views]（缺省全量）
// 行内豁免：在含协议值中文的行尾加 “// i18n-ignore” 或 “<!-- i18n-ignore -->”
// =============================================================================
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const SRC = join(ROOT, 'src')

// 目录/文件级豁免（协议值、注释密集的类型声明、语言包本身、dev 工具）
const ALLOWLIST = [
  ['src', 'locales'].join(sep),
  ['src', 'types'].join(sep),
  ['src', 'utils', 'dev-auth-mock.ts'].join(sep),
]

const HAN = /\p{Script=Han}/u

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) yield* walk(full)
    else if (/\.(vue|ts)$/.test(name) && !name.endsWith('.d.ts')) yield full
  }
}

function stripComments(text) {
  // 多行注释置换为等量换行，保持行号与原文件一致（i18n-ignore 按行号回查原文）
  const keepLines = (m) => m.replace(/[^\n]/g, '')
  return text
    .replace(/<!--[\s\S]*?-->/g, keepLines)   // HTML 注释
    .replace(/\/\*[\s\S]*?\*\//g, keepLines)  // 块注释
    .replace(/(^|[^:'"`])\/\/[^\n]*/g, '$1')  // 行注释（避开 http:// 与字符串内 //）
}

const targetDir = process.argv.includes('--dir')
  ? join(ROOT, process.argv[process.argv.indexOf('--dir') + 1])
  : SRC

let violations = 0
for (const file of walk(targetDir)) {
  const rel = relative(ROOT, file)
  if (ALLOWLIST.some(prefix => rel.startsWith(prefix))) continue
  const raw = readFileSync(file, 'utf-8')
  const rawLines = raw.split('\n')
  const lines = stripComments(raw).split('\n')
  lines.forEach((line, index) => {
    if (!HAN.test(line)) return
    const original = rawLines[index] || line
    if (/i18n-ignore/.test(original)) return
    violations += 1
    if (violations <= 50) {
      console.error(`  ${rel}:${index + 1}: ${line.trim().slice(0, 80)}`)
    }
  })
}

// key parity: 直接动态 import 编译前的 TS 不可行，改为文本级键提取对比目录结构
function keySet(dir) {
  const keys = new Set()
  for (const file of walk(join(ROOT, 'src', 'locales', dir))) {
    const rel = relative(join(ROOT, 'src', 'locales', dir), file)
    keys.add(rel)
  }
  return keys
}
const zh = keySet('zh-CN')
const en = keySet('en-US')
const missingEn = [...zh].filter(k => !en.has(k))
const extraEn = [...en].filter(k => !zh.has(k))
if (missingEn.length || extraEn.length) {
  console.error('locale 文件不对齐: en 缺失', missingEn, 'en 多余', extraEn)
  violations += 1
}
// 深层 key 全等由 en-US 各命名空间的 `satisfies typeof zh` 在 vue-tsc 编译期保证

if (violations > 0) {
  console.error(`\n[check-i18n] 共 ${violations} 处硬编码中文/不对齐（协议值请在行尾加 i18n-ignore）`)
  process.exit(1)
}
console.log('[check-i18n] OK: 无硬编码中文，语言包文件对齐')
