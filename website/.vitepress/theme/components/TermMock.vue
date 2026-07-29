<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useData } from 'vitepress'

const { lang } = useData()
const isZh = computed(() => lang.value === 'zh-CN')

const script = computed(() =>
  isZh.value
    ? {
        title: 'OrangeServer · AI 运维 Agent',
        replay: 'session replay',
        user: '看一下 web 组 3 台机器的磁盘使用率',
        thinking: 'Agent 正在规划',
        plan: '已在「web」组找到 3 台授权资产，正在准备批量命令——审批通过前不会执行任何操作。',
        approvalTag: '待审批',
        approvalId: 'BATCH-2741',
        cmd: "df -h | awk 'NR==1 || /\\/$/'",
        scope: '目标：web-01 · web-02 · web-03 ｜ 全程审计',
        approve: '批准执行',
        reject: '拒绝',
        results: [
          { host: 'web-01', pct: '68%', level: 'ok', label: '正常' },
          { host: 'web-02', pct: '91%', level: 'warn', label: '偏高' },
          { host: 'web-03', pct: '54%', level: 'ok', label: '正常' },
        ],
        foot: '所有批量操作均需人工审批 · 每次执行可追溯',
      }
    : {
        title: 'OrangeServer · AI Agent',
        replay: 'session replay',
        user: 'Check disk usage on the 3 hosts in group "web".',
        thinking: 'Agent is planning',
        plan: 'Found 3 authorized assets in group "web". Preparing a batch command — nothing runs until you approve.',
        approvalTag: 'APPROVAL REQUIRED',
        approvalId: 'BATCH-2741',
        cmd: "df -h | awk 'NR==1 || /\\/$/'",
        scope: 'Targets: web-01 · web-02 · web-03 ｜ audit logged',
        approve: 'Approve',
        reject: 'Reject',
        results: [
          { host: 'web-01', pct: '68%', level: 'ok', label: 'ok' },
          { host: 'web-02', pct: '91%', level: 'warn', label: 'high' },
          { host: 'web-03', pct: '54%', level: 'ok', label: 'ok' },
        ],
        foot: 'Every batch action needs human approval · every run is traceable',
      }
)

type Phase = 'idle' | 'typing' | 'thinking' | 'plan' | 'approval' | 'results' | 'done'
const order: Phase[] = ['idle', 'typing', 'thinking', 'plan', 'approval', 'results', 'done']
const phase = ref<Phase>('idle')
const typed = ref('')

const reached = (p: Phase) => order.indexOf(phase.value) >= order.indexOf(p)
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

onMounted(async () => {
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (reduced) {
    typed.value = script.value.user
    phase.value = 'done'
    return
  }
  await sleep(600)
  phase.value = 'typing'
  for (const ch of script.value.user) {
    typed.value += ch
    await sleep(/[一-鿿]/.test(ch) ? 55 : 30)
  }
  await sleep(400)
  phase.value = 'thinking'
  await sleep(1000)
  phase.value = 'plan'
  await sleep(1100)
  phase.value = 'approval'
  await sleep(1400)
  phase.value = 'results'
  await sleep(1200)
  phase.value = 'done'
})
</script>

<template>
  <div class="term-mock" aria-label="AI operations demo">
    <div class="term-bar">
      <span class="win-dot r"></span>
      <span class="win-dot y"></span>
      <span class="win-dot g"></span>
      <span class="term-title">{{ script.title }}</span>
      <span class="term-replay">{{ script.replay }}</span>
    </div>
    <div class="term-body">
      <div class="line user-line">
        <span class="prompt">›</span>
        <span class="user-text">{{ typed }}</span>
        <span v-if="phase === 'idle' || phase === 'typing'" class="cursor"></span>
      </div>

      <div v-if="reached('thinking')" class="line agent-line">
        <template v-if="phase === 'thinking'">
          <span class="thinking-dots"><i></i><i></i><i></i></span>
          <span class="muted">{{ script.thinking }}</span>
        </template>
        <template v-else>
          <span class="agent-mark">✦</span>
          <span class="agent-text">{{ script.plan }}</span>
        </template>
      </div>

      <div v-if="reached('approval')" class="approval-card">
        <div class="appr-head">
          <span class="appr-tag">{{ script.approvalTag }}</span>
          <span class="appr-id">{{ script.approvalId }}</span>
        </div>
        <div class="appr-cmd"><span class="ps">$</span> {{ script.cmd }}</div>
        <div class="appr-scope">{{ script.scope }}</div>
        <div class="appr-actions">
          <span class="btn-approve">{{ script.approve }}</span>
          <span class="btn-reject">{{ script.reject }}</span>
        </div>
      </div>

      <div v-if="reached('results')" class="results">
        <div
          v-for="(r, i) in script.results"
          :key="r.host"
          class="result-line"
          :style="{ animationDelay: `${i * 0.28}s` }"
        >
          <span class="host">{{ r.host }}</span>
          <span class="pct">{{ r.pct }}</span>
          <span class="status-dot" :class="r.level"></span>
          <span class="muted">{{ r.label }}</span>
        </div>
      </div>

      <div v-if="phase === 'done'" class="term-foot">{{ script.foot }}</div>
      <div v-if="phase === 'done'" class="line prompt-line">
        <span class="prompt">›</span>
        <span class="cursor"></span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.term-mock {
  border-radius: 12px;
  background: #16181d;
  border: 1px solid rgba(255, 255, 255, 0.09);
  box-shadow:
    0 32px 72px -20px rgba(20, 16, 10, 0.5),
    0 0 0 1px rgba(0, 0, 0, 0.25);
  overflow: hidden;
  font-family: ui-monospace, 'Cascadia Code', 'JetBrains Mono', Consolas, 'Courier New', monospace;
  text-align: left;
  animation: term-in 0.7s cubic-bezier(0.2, 0.7, 0.2, 1) both;
}
@keyframes term-in {
  from {
    opacity: 0;
    transform: translateY(18px) scale(0.97);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

.term-bar {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 11px 14px;
  background: rgba(255, 255, 255, 0.035);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}
.win-dot {
  width: 11px;
  height: 11px;
  border-radius: 50%;
}
.win-dot.r { background: #ff5f57; }
.win-dot.y { background: #febc2e; }
.win-dot.g { background: #28c840; }
.term-title {
  margin-left: 8px;
  font-size: 12px;
  color: #9aa0ab;
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.term-replay {
  font-size: 10.5px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #5d6470;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  padding: 2px 7px;
  white-space: nowrap;
}

.term-body {
  padding: 18px 18px 16px;
  font-size: 13px;
  line-height: 1.75;
  color: #d4d7de;
  min-height: 25em;
}
.line {
  margin-bottom: 12px;
}
.prompt {
  color: #f76707;
  font-weight: 700;
  margin-right: 8px;
}
.user-text {
  color: #f2f3f5;
  font-weight: 600;
}
.cursor {
  display: inline-block;
  width: 0.55em;
  height: 1.1em;
  background: #f76707;
  vertical-align: text-bottom;
  margin-left: 3px;
  animation: blink 1s steps(1) infinite;
}
@keyframes blink {
  50% {
    opacity: 0;
  }
}

.agent-line {
  animation: line-in 0.45s ease both;
}
.agent-mark {
  color: #f76707;
  margin-right: 8px;
}
.agent-text {
  color: #b9bec8;
}
.muted {
  color: #7d838e;
}
.thinking-dots {
  display: inline-flex;
  gap: 4px;
  margin-right: 10px;
  vertical-align: middle;
}
.thinking-dots i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #8b8f99;
  animation: think 1s ease infinite;
}
.thinking-dots i:nth-child(2) { animation-delay: 0.15s; }
.thinking-dots i:nth-child(3) { animation-delay: 0.3s; }
@keyframes think {
  0%, 100% { opacity: 0.3; transform: translateY(0); }
  50% { opacity: 1; transform: translateY(-3px); }
}

.approval-card {
  border: 1px solid rgba(247, 103, 7, 0.55);
  background: rgba(247, 103, 7, 0.08);
  border-radius: 10px;
  padding: 13px 15px;
  margin: 14px 0;
  animation:
    line-in 0.45s ease both,
    pulse 1.3s ease-out 0.35s 2;
}
@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(247, 103, 7, 0.45); }
  100% { box-shadow: 0 0 0 16px rgba(247, 103, 7, 0); }
}
.appr-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 9px;
}
.appr-tag {
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: #ffa94d;
  border: 1px solid rgba(255, 169, 77, 0.5);
  border-radius: 4px;
  padding: 2px 7px;
  white-space: nowrap;
}
.appr-id {
  font-size: 11px;
  color: #6d727c;
  letter-spacing: 0.05em;
}
.appr-cmd {
  font-size: 12.5px;
  color: #ffe8d6;
  background: rgba(0, 0, 0, 0.35);
  border-radius: 6px;
  padding: 7px 10px;
  margin-bottom: 8px;
  overflow-x: auto;
  white-space: nowrap;
}
.appr-cmd .ps {
  color: #f76707;
  font-weight: 700;
}
.appr-scope {
  font-size: 11.5px;
  color: #9aa0ab;
  margin-bottom: 11px;
}
.appr-actions {
  display: flex;
  gap: 10px;
}
.btn-approve,
.btn-reject {
  font-size: 12px;
  font-weight: 600;
  border-radius: 6px;
  padding: 5px 14px;
}
.btn-approve {
  background: #f76707;
  color: #fff;
  box-shadow: 0 2px 10px rgba(247, 103, 7, 0.45);
}
.btn-reject {
  border: 1px solid rgba(255, 255, 255, 0.18);
  color: #9aa0ab;
}

.results {
  margin-top: 4px;
}
.result-line {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 2px 0;
  animation: line-in 0.4s ease both;
}
.host {
  color: #e8eaee;
  font-weight: 600;
  min-width: 5.5em;
}
.pct {
  color: #b9bec8;
  min-width: 3.5em;
}
.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
.status-dot.ok { background: #40c057; }
.status-dot.warn {
  background: #fab005;
  box-shadow: 0 0 6px rgba(250, 176, 5, 0.8);
}

.term-foot {
  margin-top: 14px;
  padding-top: 11px;
  border-top: 1px dashed rgba(255, 255, 255, 0.12);
  font-size: 11.5px;
  color: #6d727c;
  animation: line-in 0.5s ease both;
}
.prompt-line {
  margin: 8px 0 0;
  animation: line-in 0.4s ease both;
}

@keyframes line-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

@media (max-width: 480px) {
  .term-body {
    font-size: 12px;
    min-height: 27em;
    padding: 14px 13px 12px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .term-mock,
  .agent-line,
  .approval-card,
  .result-line,
  .term-foot,
  .prompt-line {
    animation: none;
  }
  .cursor {
    animation: none;
  }
}
</style>
