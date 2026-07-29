<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <span class="page-eyebrow">SCHEDULER</span>
        <h2>{{ $t('cron.title') }}</h2>
        <i18n-t keypath="cron.headerSummary" tag="p">
          <template #total><strong>{{ total }}</strong></template>
          <template #active><strong class="num" style="color:var(--ogs-log-success)">{{ activeCount }}</strong></template>
          <template #paused><strong class="num" style="color:var(--ogs-warning)">{{ pausedCount }}</strong></template>
        </i18n-t>
      </div>
      <div class="page-actions">
        <el-button @click="loadData"><el-icon><Refresh /></el-icon>{{ $t('common.action.refresh') }}</el-button>
        <el-button type="primary" @click="openAdd"><el-icon><Plus /></el-icon>{{ $t('cron.createJob') }}</el-button>
        <el-dropdown trigger="click" @command="batchAction">
          <el-button :disabled="!selectedRows.length">
            <el-icon><Operation /></el-icon>{{ $t('cron.batchActions') }}<span v-if="selectedRows.length" class="batch-count">{{ selectedRows.length }}</span>
            <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="resume" :disabled="!selectedRows.length">
                <el-icon><VideoPlay /></el-icon>{{ $t('cron.batchResume') }}
              </el-dropdown-item>
              <el-dropdown-item command="pause" :disabled="!selectedRows.length">
                <el-icon><VideoPause /></el-icon>{{ $t('cron.batchPause') }}
              </el-dropdown-item>
              <el-dropdown-item command="del" :disabled="!selectedRows.length" divided>
                <el-icon class="batch-danger-icon"><Delete /></el-icon><span class="batch-danger">{{ $t('cron.batchDelete') }}</span>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>
    <div class="panel">
      <div class="panel-head">
        <span class="panel-icon"><el-icon :size="14"><Timer /></el-icon></span>
        <span class="panel-title">{{ $t('cron.jobList') }}</span>
        <span class="panel-sub">Cron Jobs</span>
      </div>
      <!-- 搜索 + 筛选 -->
      <div class="list-toolbar">
        <el-input v-model="keyword" :placeholder="$t('cron.searchPlaceholder')" clearable class="search-input" :prefix-icon="Search" @input="onSearch" />
        <el-select v-model="statusFilter" :placeholder="$t('cron.filterByStatus')" clearable @change="onFilterChange" style="width:130px">
          <el-option :label="$t('cron.statusActive')" :value="JOB_STATUS_ACTIVE" />
          <el-option :label="$t('cron.statusPaused')" :value="JOB_STATUS_PAUSED" />
        </el-select>
        <div class="stats">
          <i18n-t keypath="cron.totalCount" tag="span" class="num">
            <template #n><strong>{{ total }}</strong></template>
          </i18n-t>
          <span><span class="dot" style="background:var(--ogs-log-success)" />{{ $t('cron.statusActive') }} <strong class="num">{{ activeCount }}</strong></span>
          <span><span class="dot" style="background:var(--ogs-warning)" />{{ $t('cron.statusPaused') }} <strong class="num">{{ pausedCount }}</strong></span>
        </div>
      </div>
      <div class="panel-body" style="padding:0">
        <el-table :data="pagedData" :class="['is-compact']" stripe v-loading="loading" style="width:100%" @selection-change="onSelect">
        <el-table-column type="selection" width="44" />
        <el-table-column prop="id" label="ID" width="62" sortable>
          <template #default="{ row }">
            <span class="num" style="color:var(--ogs-text-muted)">#{{ row.id }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="job_name" :label="$t('cron.col.name')" min-width="150">
          <template #default="{ row }">
            <span style="font-weight:600;color:var(--ogs-text)">{{ row.job_name }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('cron.col.expr')" min-width="170">
          <template #default="{ row }">
            <div class="cron-expr">
              <span class="cron-field" :title="`${$t('cron.field.minute')}: ${row.job_minute}`">{{ row.job_minute }}</span>
              <span class="cron-field" :title="`${$t('cron.field.hour')}: ${row.job_hour}`">{{ row.job_hour }}</span>
              <span class="cron-field" :title="`${$t('cron.field.day')}: ${row.job_day}`">{{ row.job_day }}</span>
              <span class="cron-field" :title="`${$t('cron.field.month')}: ${row.job_month}`">{{ row.job_month }}</span>
              <span class="cron-field" :title="`${$t('cron.field.week')}: ${row.job_week}`">{{ row.job_week }}</span>
            </div>
            <div class="cron-human">{{ cronHuman(row) }}</div>
          </template>
        </el-table-column>
        <el-table-column :label="$t('cron.col.nextRun')" min-width="140">
          <template #default="{ row }">
            <span v-if="isActive(row) && nextRun(row)" class="time-cell">
              <span class="time-rel">{{ nextRunRel(row) }}</span>
              <span class="time-abs">{{ nextRunAbs(row) }}</span>
            </span>
            <span v-else style="color:var(--ogs-text-muted)">—</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('cron.col.targets')" min-width="200">
          <template #default="{ row }">
            <div v-if="parseHostList(row.job_hosts).length" class="cron-target-cell">
              <el-popover
                :width="520"
                placement="bottom-start"
                :show-arrow="false"
                trigger="click"
                :hide-after="0"
                popper-class="cmd-popover ip-popover"
                :offset="6"
              >
                <template #reference>
                  <div class="ip-pill-wrap" :title="parseHostList(row.job_hosts).length > 1 ? $t('cron.viewAllHosts') : ''" @click.stop>
                    <span class="ip-pill">
                      <el-icon :size="10"><Monitor /></el-icon>
                      <span class="ip-pill-text">{{ parseHostList(row.job_hosts)[0] }}</span>
                    </span>
                    <span v-if="parseHostList(row.job_hosts).length > 1" class="ip-pill-more" :title="$t('cron.moreHosts', { n: parseHostList(row.job_hosts).length - 1 })">
                      +{{ parseHostList(row.job_hosts).length - 1 }}
                    </span>
                    <span class="ip-pill-hint" aria-hidden="true">
                      <el-icon :size="10"><ZoomIn /></el-icon>
                    </span>
                  </div>
                </template>
                <div class="cmd-popover-body" @click.stop>
                  <div class="cmd-popover-head">
                    <div class="cmd-popover-title">
                      <el-icon :size="13"><Monitor /></el-icon>
                      <span>{{ $t('cron.execTargets') }}</span>
                      <span class="cmd-popover-badge cmd-popover-badge--ghost">{{ $t('cron.itemsCount', { n: totalTargets(row) }) }}</span>
                    </div>
                    <div class="cmd-popover-meta">
                      <span v-if="row.job_name" class="cmd-popover-chip">
                        <el-icon :size="10"><Document /></el-icon>{{ row.job_name }}
                      </span>
                      <span v-if="row.job_status" class="cmd-popover-chip" :class="{ 'is-active': isActive(row) }">
                        <el-icon :size="10"><Timer /></el-icon>{{ statusLabel(row) }}
                      </span>
                      <span v-if="nextRun(row) && isActive(row)" class="cmd-popover-chip">
                        <el-icon :size="10"><Clock /></el-icon>{{ $t('cron.nextRunAt', { time: nextRunAbs(row) }) }}
                      </span>
                    </div>
                  </div>
                  <div class="cmd-popover-content">
                    <div v-if="parseHostList(row.job_hosts).length" class="cron-target-section">
                      <div class="cron-target-section-head">
                        <el-icon :size="11"><Monitor /></el-icon>
                        <span>{{ $t('cron.hosts') }}</span>
                        <span class="cron-target-section-count">{{ $t('cron.hostCount', { n: parseHostList(row.job_hosts).length }) }}</span>
                      </div>
                      <ul class="ip-popover-list">
                        <li v-for="(h, i) in parseHostList(row.job_hosts)" :key="'h-' + i" class="ip-popover-item">
                          <span class="ip-popover-idx">{{ String(i + 1).padStart(2, '0') }}</span>
                          <el-icon :size="11" class="ip-popover-ico"><Monitor /></el-icon>
                          <span class="ip-popover-name">{{ h }}</span>
                          <span class="ip-popover-copy" :title="$t('cron.copyHost')" @click.stop="copyText(h)">
                            <el-icon :size="10"><CopyDocument /></el-icon>
                          </span>
                        </li>
                      </ul>
                    </div>
                    <div v-if="(row.job_groups || []).length" class="cron-target-section">
                      <div class="cron-target-section-head">
                        <el-icon :size="11"><Collection /></el-icon>
                        <span>{{ $t('common.entity.group') }}</span>
                        <span class="cron-target-section-count">{{ $t('cron.groupCount', { n: row.job_groups.length }) }}</span>
                      </div>
                      <ul class="ip-popover-list">
                        <li v-for="(g, i) in row.job_groups" :key="'g-' + i" class="ip-popover-item">
                          <span class="ip-popover-idx">{{ String(i + 1).padStart(2, '0') }}</span>
                          <el-icon :size="11" class="ip-popover-ico"><Collection /></el-icon>
                          <span class="ip-popover-name">{{ g }}</span>
                          <span class="ip-popover-copy" :title="$t('cron.copyGroup')" @click.stop="copyText(g)">
                            <el-icon :size="10"><CopyDocument /></el-icon>
                          </span>
                        </li>
                      </ul>
                    </div>
                  </div>
                  <div class="cmd-popover-foot">
                    <span class="cmd-popover-tip">
                      <el-icon :size="10"><InfoFilled /></el-icon>
                      {{ $t('cron.popoverCloseTip') }}
                    </span>
                    <el-button size="small" plain type="primary" @click="copyText(allTargetsText(row))">
                      <el-icon :size="12"><CopyDocument /></el-icon>
                      <span>{{ $t('cron.copyAll') }}</span>
                    </el-button>
                  </div>
                </div>
              </el-popover>
              <span v-if="(row.job_groups || []).length" class="cron-target-groups">
                <span v-for="(g, i) in row.job_groups.slice(0, 1)" :key="'gh-' + i" :class="['chip', hostChipClass(g)]">{{ g }}</span>
                <span v-if="row.job_groups.length > 1" class="chip is-more" :title="$t('cron.moreGroups', { n: row.job_groups.length - 1 })">+{{ row.job_groups.length - 1 }}</span>
              </span>
            </div>
            <span v-else-if="(row.job_groups || []).length" class="chip-list">
              <span v-for="(g, i) in row.job_groups.slice(0, 2)" :key="'g2-' + i" :class="['chip', hostChipClass(g)]">{{ g }}</span>
              <span v-if="row.job_groups.length > 2" class="chip is-more">+{{ row.job_groups.length - 2 }}</span>
            </span>
            <span v-else style="color:var(--ogs-text-muted)">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="job_sys_user" :label="$t('cron.col.sysUser')" width="100" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="cron-sys-user">{{ row.job_sys_user || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="job_command" :label="$t('cron.col.command')" min-width="170" :show-overflow-tooltip="false">
          <template #default="{ row }">
            <el-popover
              v-if="row.job_command"
              :width="520"
              placement="bottom-start"
              :show-arrow="false"
              trigger="click"
              :hide-after="0"
              popper-class="cmd-popover"
              :offset="6"
            >
              <template #reference>
                <div
                  :class="['cmd-expandable', { 'is-danger': isDangerCommand(row.job_command) }]"
                  :title="$t('cron.viewFullCommand')"
                  @click.stop
                >
                  <el-icon v-if="isDangerCommand(row.job_command)" :size="11" class="cmd-icon"><Warning /></el-icon>
                  <span class="cmd-text">{{ row.job_command }}</span>
                  <span class="cmd-hint" aria-hidden="true">
                    <el-icon :size="10"><ZoomIn /></el-icon>
                  </span>
                </div>
              </template>
              <div class="cmd-popover-body" @click.stop>
                <div class="cmd-popover-head" :class="{ 'is-danger': isDangerCommand(row.job_command) }">
                  <div class="cmd-popover-title">
                    <el-icon :size="13"><Memo /></el-icon>
                    <span>{{ $t('cron.commandDetail') }}</span>
                    <span v-if="isDangerCommand(row.job_command)" class="cmd-popover-badge">{{ $t('cron.dangerCommand') }}</span>
                  </div>
                  <div class="cmd-popover-meta">
                    <span class="cmd-popover-chip">
                      <el-icon :size="10"><Timer /></el-icon>{{ cronExpr(row) }}
                    </span>
                    <span class="cmd-popover-chip">
                      <el-icon :size="10"><User /></el-icon>{{ row.job_sys_user || '—' }}
                    </span>
                    <span v-if="row.job_name" class="cmd-popover-chip">
                      <el-icon :size="10"><Document /></el-icon>{{ row.job_name }}
                    </span>
                  </div>
                </div>
                <div class="cmd-popover-content" :class="{ 'is-danger': isDangerCommand(row.job_command) }">
                  <pre class="cmd-popover-pre">{{ row.job_command }}</pre>
                </div>
                <div class="cmd-popover-foot">
                  <span class="cmd-popover-tip">
                    <el-icon :size="10"><InfoFilled /></el-icon>
                    {{ $t('cron.popoverCloseTip') }}
                  </span>
                  <el-button size="small" plain type="primary" @click="copyText(row.job_command)">
                    <el-icon :size="12"><CopyDocument /></el-icon>
                    <span>{{ $t('cron.copyCommand') }}</span>
                  </el-button>
                </div>
              </div>
            </el-popover>
            <span v-else style="color:var(--ogs-text-muted)">—</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('cron.col.status')" width="90" align="center">
          <template #default="{ row }">
            <span :class="['log-status', isActive(row)?'is-success':'is-warn']">{{ statusLabel(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('cron.col.remarks')" min-width="100" :show-overflow-tooltip="false">
          <template #default="{ row }">
            <el-popover
              v-if="row.job_remarks"
              :width="420"
              placement="bottom-start"
              :show-arrow="false"
              trigger="click"
              :hide-after="0"
              popper-class="cmd-popover"
              :offset="6"
            >
              <template #reference>
                <div class="cmd-expandable" :title="$t('cron.viewFullRemarks')" @click.stop>
                  <span class="cmd-text">{{ row.job_remarks }}</span>
                  <span class="cmd-hint" aria-hidden="true">
                    <el-icon :size="10"><ZoomIn /></el-icon>
                  </span>
                </div>
              </template>
              <div class="cmd-popover-body" @click.stop>
                <div class="cmd-popover-head">
                  <div class="cmd-popover-title">
                    <el-icon :size="13"><Document /></el-icon>
                    <span>{{ $t('cron.jobRemarks') }}</span>
                  </div>
                  <div v-if="row.job_name" class="cmd-popover-meta">
                    <span class="cmd-popover-chip">
                      <el-icon :size="10"><Timer /></el-icon>{{ row.job_name }}
                    </span>
                  </div>
                </div>
                <div class="cmd-popover-content">
                  <pre class="cmd-popover-pre">{{ row.job_remarks }}</pre>
                </div>
                <div class="cmd-popover-foot">
                  <span class="cmd-popover-tip">
                    <el-icon :size="10"><InfoFilled /></el-icon>
                    {{ $t('cron.popoverCloseTip') }}
                  </span>
                  <el-button size="small" plain type="primary" @click="copyText(row.job_remarks)">
                    <el-icon :size="12"><CopyDocument /></el-icon>
                    <span>{{ $t('cron.copyRemarks') }}</span>
                  </el-button>
                </div>
              </div>
            </el-popover>
            <span v-else style="color:var(--ogs-text-muted)">—</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('cron.col.actions')" width="80" fixed="right" align="right">
          <template #default="scope">
            <el-dropdown trigger="click" @command="(cmd: string) => onRowCommand(cmd, scope.row)" @click.stop>
              <el-button text size="small" class="row-action-trigger">
                {{ $t('cron.col.actions') }}<el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="log">
                    <el-icon><Document /></el-icon><span>{{ $t('cron.viewLog') }}</span>
                  </el-dropdown-item>
                  <el-dropdown-item :command="isActive(scope.row) ? 'pause' : 'resume'">
                    <el-icon><component :is="isActive(scope.row) ? VideoPause : VideoPlay" /></el-icon>
                    <span>{{ isActive(scope.row) ? $t('cron.pauseJob') : $t('cron.resumeJob') }}</span>
                  </el-dropdown-item>
                  <el-dropdown-item command="run">
                    <el-icon><Promotion /></el-icon><span>{{ $t('cron.runOnce') }}</span>
                  </el-dropdown-item>
                  <el-dropdown-item command="edit">
                    <el-icon><Edit /></el-icon><span>{{ $t('common.action.edit') }}</span>
                  </el-dropdown-item>
                  <el-dropdown-item command="del" divided>
                    <el-icon class="batch-danger-icon"><Delete /></el-icon><span class="batch-danger">{{ $t('common.action.delete') }}</span>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
        <template #empty>
          <div class="empty-state">
            <el-icon :size="40" style="color:var(--ogs-text-muted)"><Timer /></el-icon>
            <p>{{ $t('cron.emptyTitle') }}</p>
            <span>{{ $t('cron.emptyHint') }}</span>
          </div>
        </template>
        </el-table>
      </div>
      <div class="list-pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50]"
          :total="filteredData.length"
          layout="total, sizes, prev, pager, next, jumper"
          background
        />
      </div>
    </div>

    <el-dialog v-model="dialogVisible" :title="isEdit ? $t('cron.editJob') : $t('cron.createJob')" width="640px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px" class="cron-form">
        <el-form-item :label="$t('cron.form.name')" prop="job_name"><el-input v-model="form.job_name" :disabled="isEdit" :placeholder="$t('cron.form.namePlaceholder')" /></el-form-item>
        <el-form-item :label="$t('cron.form.frequency')">
          <div class="preset-row">
            <span v-for="p in presets" :key="p.label" :class="['preset-pill', isPresetActive(p)?'is-active':'']" @click="applyPreset(p)">{{ $t(p.label) }}</span>
          </div>
        </el-form-item>
        <el-form-item :label="$t('cron.form.cronFields')">
          <div class="cron-fields">
            <div class="cron-field-block">
              <span class="cron-field-label">{{ $t('cron.field.minute') }}</span>
              <el-input v-model="form.job_minute" placeholder="*" />
            </div>
            <div class="cron-field-block">
              <span class="cron-field-label">{{ $t('cron.field.hour') }}</span>
              <el-input v-model="form.job_hour" placeholder="*" />
            </div>
            <div class="cron-field-block">
              <span class="cron-field-label">{{ $t('cron.field.day') }}</span>
              <el-input v-model="form.job_day" placeholder="*" />
            </div>
            <div class="cron-field-block">
              <span class="cron-field-label">{{ $t('cron.field.month') }}</span>
              <el-input v-model="form.job_month" placeholder="*" />
            </div>
            <div class="cron-field-block">
              <span class="cron-field-label">{{ $t('cron.field.week') }}</span>
              <el-input v-model="form.job_week" placeholder="*" />
            </div>
          </div>
          <div class="cron-preview">
            <el-icon :size="12"><Clock /></el-icon>
            <span class="cron-preview-label">{{ $t('cron.form.preview') }}</span>
            <span class="cron-preview-text">{{ cronFormHuman }}</span>
          </div>
        </el-form-item>
        <el-form-item :label="$t('cron.form.hosts')" prop="job_hosts">
          <el-select v-model="form.job_hosts" multiple :placeholder="$t('cron.form.hostsPlaceholder')" style="width:100%">
            <el-option v-for="h in hosts" :key="h" :label="h" :value="h" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('cron.form.groups')" prop="job_groups">
          <el-select v-model="form.job_groups" multiple :placeholder="$t('cron.form.groupsPlaceholder')" style="width:100%">
            <el-option v-for="g in groups" :key="g" :label="g" :value="g" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('cron.form.sysUser')" prop="job_sys_user">
          <el-select v-model="form.job_sys_user" :placeholder="$t('cron.form.sysUserPlaceholder')" style="width:100%">
            <el-option v-for="u in sysUsers" :key="u" :label="u" :value="u" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('cron.form.command')" prop="job_command"><el-input v-model="form.job_command" type="textarea" :rows="3" :placeholder="$t('cron.form.commandPlaceholder')" /></el-form-item>
        <el-form-item :label="$t('cron.form.remarks')"><el-input v-model="form.job_remarks" :placeholder="$t('cron.form.remarksPlaceholder')" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible=false">{{ $t('common.action.cancel') }}</el-button>
        <el-button v-if="!isEdit" type="success" @click="submitForm(true)" :loading="submitting">{{ $t('cron.saveAndContinue') }}</el-button>
        <el-button type="primary" @click="submitForm(false)" :loading="submitting">{{ $t('common.action.save') }}</el-button>
      </template>
    </el-dialog>
    <!-- 执行日志弹窗 -->
    <el-dialog v-model="logDialogVisible" :title="$t('cron.execResultTitle', { name: logJobName })" width="720px" top="6vh" destroy-on-close>
      <div v-if="runLoading" style="text-align:center;padding:40px 0">
        <el-icon class="is-loading" :size="24" style="margin-right:8px"><Loading /></el-icon>{{ $t('cron.executing') }}
      </div>
      <div v-else-if="runResults.length" class="cron-log-body">
        <div class="log-summary">
          <span v-if="lastResultTime" class="log-time">{{ $t('cron.lastExecuted', { time: lastResultTime }) }}</span>
          <el-tag type="success" size="small">{{ $t('cron.successCount', { n: runResults.filter(r=>!r.error).length }) }}</el-tag>
          <el-tag type="danger" size="small">{{ $t('cron.failCount', { n: runResults.filter(r=>r.error).length }) }}</el-tag>
        </div>
        <el-collapse v-model="expandedLogs" class="log-collapse">
          <el-collapse-item v-for="(r, i) in runResults" :key="i" :name="i">
            <template #title>
              <div class="log-host-title">
                <span class="log-host-dot" :class="r.error?'dot-error':'dot-ok'"/>
                <span>{{ r.host }}</span>
                <el-tag v-if="r.error" type="danger" size="small" style="margin-left:8px">{{ $t('common.status.fail') }}</el-tag>
                <el-tag v-else type="success" size="small" style="margin-left:8px">{{ $t('common.status.success') }}</el-tag>
              </div>
            </template>
            <pre class="log-output" :class="{'is-error':r.error}">{{ r.output || $t('cron.noOutput') }}</pre>
          </el-collapse-item>
        </el-collapse>
      </div>
      <div v-else style="text-align:center;color:var(--ogs-text-secondary);padding:24px 0">{{ $t('cron.noResults') }}</div>
      <template #footer>
        <el-button @click="logDialogVisible=false">{{ $t('common.action.close') }}</el-button>
        <el-button type="primary" @click="doRun({job_name:logJobName})" :loading="runLoading">{{ $t('cron.manualRun') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, VideoPlay, VideoPause, Loading, Clock, Warning, Monitor, ZoomIn, Memo, User, Document, InfoFilled, CopyDocument, Collection, Timer, Refresh, Plus, ArrowDown, Operation, Delete, Edit, Promotion } from '@element-plus/icons-vue'
import { getCronList, deleteCron, pauseCron, resumeCron, batchCron, runCron, getCronLastResult, getHostList, getHostGroupNameList, getSysUserNameList, http } from '@/api'
import { parseHostList } from '@/utils/host'
import { t } from '@/i18n'
// REV34-M7: 增强版 nextRun 计算，支持 */2、1-5、1,3,5 等标准 cron 模式
import { useCronNext } from '@/composables/useCronNext'
// REV35-L4: 危险命令检测抽到 utils/danger
import { isDangerCommand } from '@/utils/danger'
// REV35-L2: 复制抽到 composables/useClipboard
import { useClipboard } from '@/composables/useClipboard'
// REV35-L5: 资产组 chip 颜色统一走 utils/groupClassifier
import { groupTagClass } from '@/utils/groupClassifier'

// ===== 后端协议值：job_status 与后端中文枚举比较，不参与翻译 =====
const JOB_STATUS_ACTIVE = '启动' // i18n-ignore
const JOB_STATUS_PAUSED = '暂停' // i18n-ignore

// ===== 任务行 (后端 cron_list_msg 返回) =====
interface CronRow {
  id?: number | string
  job_name: string
  job_minute: string
  job_hour: string
  job_day: string
  job_month: string
  job_week: string
  job_hosts: string[] | string
  job_groups?: string[]
  job_sys_user: string
  job_command: string
  job_remarks?: string
  job_status: string
  [k: string]: unknown
}

// ===== 表单 =====
interface CronForm {
  job_name: string
  job_minute: string
  job_hour: string
  job_day: string
  job_month: string
  job_week: string
  job_hosts: string[]
  job_groups: string[]
  job_sys_user: string
  job_command: string
  job_remarks: string
}

// ===== cron 预设项（label 为 i18n key，渲染时经 $t 求值）=====
interface CronPreset {
  label: string
  minute: string
  hour: string
  day: string
  month: string
  week: string
}

// ===== 主机项 =====
interface HostItem {
  alias?: string
  host_ip?: string
  [k: string]: unknown
}

// ===== 列表响应 =====
interface CronListResp {
  cron_list_msg?: CronRow[]
  [k: string]: unknown
}

// ===== 主机列表响应 =====
interface HostListResp {
  host_list_msg?: HostItem[]
  [k: string]: unknown
}

// ===== 名列表应 (groups/sysUsers) =====
interface NameListResp {
  code: number
  msg?: string[]
  group_name_list_msg?: string[]
  [k: string]: unknown
}

// ===== 执行结果项 =====
interface RunResult {
  host: string
  output?: string
  error?: string
  [k: string]: unknown
}

// ===== 执行结果响应 =====
interface RunResultResp {
  code: number
  msg?: string
  results?: RunResult[]
  time?: string
  [k: string]: unknown
}

// ===== 批量操作类型 =====
type BatchActionType = 'resume' | 'pause' | 'del'

// ===== 资产名转换辅助 =====
function hostLabel(h: HostItem): string {
  return h.alias || h.host_ip || ''
}

// ===== 数据 =====
const allData = ref<CronRow[]>([])
const loading = ref<boolean>(false)
const selectedRows = ref<CronRow[]>([])
const keyword = ref<string>('')
const statusFilter = ref<string>('')
const currentPage = ref<number>(1)
const pageSize = ref<number>(10)

const total = computed<number>(() => filteredData.value.length)
const activeCount = computed<number>(() => allData.value.filter(isActive).length)
const pausedCount = computed<number>(() => allData.value.filter(r => r.job_status === JOB_STATUS_PAUSED).length)

// ===== 协议状态判断 / 展示文案 =====
function isActive(row: CronRow): boolean {
  return row.job_status === JOB_STATUS_ACTIVE
}
function statusLabel(row: CronRow): string {
  return isActive(row) ? t('cron.statusActive') : t('cron.statusPaused')
}

function onSearch(): void { currentPage.value = 1 }
function onFilterChange(): void { currentPage.value = 1 }

// REV35-L5: hostChipClass 别名（保留模板调用名，原 hostChipClass 函数已删除）
const hostChipClass = groupTagClass

// REV34-M7: 简易 cron 下一次执行时间计算已迁移到 composables/useCronNext.js
// 支持标准 cron 字段语法：*  |  a  |  a-b  |  */n  |  a-b/n  |  a,b,c
const { nextRun, nextRunRel, nextRunAbs } = useCronNext(() => allData.value)

// REV35-L2: 复制抽到 composables/useClipboard
const { copy: copyText } = useClipboard()

// —— 执行目标弹窗辅助 ——
// 统计任务总目标数（主机 + 资产组）
function totalTargets(row: CronRow): number {
  return parseHostList(row.job_hosts).length + (row.job_groups || []).length
}
// 复制全部（主机 + 组，多行拼接）
function allTargetsText(row: CronRow): string {
  const hosts = parseHostList(row.job_hosts)
  const groups = row.job_groups || []
  return [...hosts, ...groups].join('\n')
}
// copyText 已抽到 composables/useClipboard，顶部 useClipboard().copy 引入

const dialogVisible = ref<boolean>(false)
const isEdit = ref<boolean>(false)
const submitting = ref<boolean>(false)
const formRef = ref<{ validate: () => Promise<boolean> } | null>(null)
const hosts = ref<string[]>([])
const groups = ref<string[]>([])
const sysUsers = ref<string[]>([])
const form = ref<CronForm>({
  job_name: '', job_minute: '*', job_hour: '*', job_day: '*', job_month: '*', job_week: '*',
  job_hosts: [], job_groups: [], job_sys_user: '', job_command: '', job_remarks: '',
})
const rules = computed(() => ({
  job_name: [{ required: true, message: t('cron.form.nameRequired'), trigger: 'blur' }],
  job_command: [{ required: true, message: t('cron.form.commandRequired'), trigger: 'blur' }],
}))

// ===== 执行日志 =====
const logDialogVisible = ref<boolean>(false)
const logJobName = ref<string>('')
const runLoading = ref<boolean>(false)
const runResults = ref<RunResult[]>([])
const runJobName = ref<string>('')
const expandedLogs = ref<number[]>([])
const lastResultTime = ref<string>('')

// ===== Cron 预设（label 为 i18n key）=====
const presets: CronPreset[] = [
  { label: 'cron.freq.everyMinute', minute: '*', hour: '*', day: '*', month: '*', week: '*' },
  { label: 'cron.freq.hourly', minute: '0', hour: '*', day: '*', month: '*', week: '*' },
  { label: 'cron.freq.daily', minute: '0', hour: '0', day: '*', month: '*', week: '*' },
  { label: 'cron.freq.weekly', minute: '0', hour: '0', day: '*', month: '*', week: '0' },
  { label: 'cron.freq.monthly', minute: '0', hour: '0', day: '1', month: '*', week: '*' },
]
function isPresetActive(p: CronPreset): boolean {
  return form.value.job_minute === p.minute && form.value.job_hour === p.hour &&
    form.value.job_day === p.day && form.value.job_month === p.month && form.value.job_week === p.week
}
function applyPreset(p: CronPreset): void {
  form.value.job_minute = p.minute
  form.value.job_hour = p.hour
  form.value.job_day = p.day
  form.value.job_month = p.month
  form.value.job_week = p.week
}

// ===== Cron 可读化 =====
function cronExpr(row: CronRow): string {
  return `${row.job_minute} ${row.job_hour} ${row.job_day} ${row.job_month} ${row.job_week}`
}
// 参数化整句生成（英文为自然表达而非逐词替换，key 见 locales/*/cron.ts 的 human.*）
function cronHuman(row: CronRow | CronForm): string {
  const m = row.job_minute, h = row.job_hour, d = row.job_day, mo = row.job_month, w = row.job_week
  const time = `${h}:${String(m).padStart(2, '0')}`
  if (m === '*' && h === '*' && d === '*' && mo === '*' && w === '*') return t('cron.human.everyMinute')
  if (m !== '*' && h === '*' && d === '*' && mo === '*' && w === '*') return t('cron.human.hourlyAt', { m })
  if (h !== '*' && d === '*' && mo === '*' && w === '*') return t('cron.human.dailyAt', { time })
  if (h !== '*' && w !== '*' && d === '*' && mo === '*') return t('cron.human.weeklyAt', { day: weekName(w), time })
  if (h !== '*' && d !== '*' && mo === '*' && w === '*') return t('cron.human.monthlyAt', { d, time })
  if (h !== '*' && d !== '*' && mo !== '*' && w === '*') return t('cron.human.yearlyAt', { mo, d, time })
  return `${m} ${h} ${d} ${mo} ${w}`
}
function weekName(w: string): string {
  const n = String(w) === '7' ? '0' : String(w)
  return /^[0-6]$/.test(n) ? t(`cron.weekday.d${n}`) : String(w)
}
const cronFormHuman = computed<string>(() => cronHuman(form.value))

// ===== 列表过滤 + 分页 =====
const filteredData = computed<CronRow[]>(() => {
  let data: CronRow[] = allData.value
  if (statusFilter.value) {
    data = data.filter(r => r.job_status === statusFilter.value)
  }
  if (keyword.value) {
    const kw = keyword.value.toLowerCase()
    data = data.filter(r =>
      (r.job_name && r.job_name.toLowerCase().includes(kw)) ||
      (r.job_command && r.job_command.toLowerCase().includes(kw))
    )
  }
  return data
})
const pagedData = computed<CronRow[]>(() => {
  const s = (currentPage.value - 1) * pageSize.value
  return filteredData.value.slice(s, s + pageSize.value)
})

// ===== 选择 =====
function onSelect(rows: CronRow[]): void { selectedRows.value = rows }

// ===== 数据加载 =====
async function loadData(): Promise<void> {
  loading.value = true
  try {
    const res = (await getCronList()) as unknown as CronListResp
    if (res.cron_list_msg) {
      allData.value = res.cron_list_msg.sort((a, b) => (a.job_name || '').localeCompare(b.job_name || ''))
    }
  } finally { loading.value = false }
}

async function loadDeps(): Promise<void> {
  try {
    const [hRes, gRes, sRes] = await Promise.all([
      getHostList() as unknown as Promise<HostListResp>,
      getHostGroupNameList() as unknown as Promise<NameListResp>,
      getSysUserNameList() as unknown as Promise<NameListResp>,
    ])
    if (hRes.host_list_msg) {
      hosts.value = hRes.host_list_msg.map(hostLabel).filter(Boolean).sort((a, b) => a.localeCompare(b))
    }
    if (gRes.code === 0) groups.value = (gRes.group_name_list_msg || []).sort((a, b) => a.localeCompare(b))
    if (sRes.code === 0) {
      sysUsers.value = (sRes.msg || []).sort((a, b) => a.localeCompare(b))
      if (sysUsers.value.length) form.value.job_sys_user = sysUsers.value[0]
    }
  } catch {
    // 静默：依赖加载失败仅留空下拉
  }
}

// ===== 新增 / 编辑 =====
function openAdd(): void {
  isEdit.value = false
  form.value = {
    job_name: '', job_minute: '*', job_hour: '*', job_day: '*', job_month: '*', job_week: '*',
    job_hosts: [], job_groups: [], job_sys_user: sysUsers.value[0] || '', job_command: '', job_remarks: '',
  }
  dialogVisible.value = true
}
function openEdit(row: CronRow): void {
  isEdit.value = true
  form.value = {
    job_name: row.job_name,
    job_minute: row.job_minute, job_hour: row.job_hour, job_day: row.job_day,
    job_month: row.job_month, job_week: row.job_week,
    job_hosts: Array.isArray(row.job_hosts) ? row.job_hosts : (row.job_hosts ? String(row.job_hosts).split(',').filter(Boolean) : []),
    job_groups: Array.isArray(row.job_groups) ? row.job_groups : (row.job_groups ? String(row.job_groups).split(',').filter(Boolean) : []),
    job_sys_user: row.job_sys_user,
    job_command: row.job_command,
    job_remarks: row.job_remarks || '',
  }
  dialogVisible.value = true
}

async function submitForm(keepOpen = false): Promise<void> {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  submitting.value = true
  try {
    if (isEdit.value) {
      // REV34-M8: 编辑原子性 — 后端无 update 接口，原"先删后增"在删除成功+新增失败时任务丢失
      //   修复策略：先快照原任务 → 删除 → 新增；新增失败时回滚（用快照重建）
      //   快照已包含全部 job 字段（含 job_name），可 1:1 重建
      const oldSnapshot = allData.value.find(r => r.job_name === form.value.job_name)
      if (!oldSnapshot) {
        ElMessage.error(t('cron.msg.originalMissing'))
        return
      }
      // 1. 删除原任务
      await deleteCron({ job_name: form.value.job_name } as unknown as Record<string, unknown>)
      // 2. 新增修改后任务
      try {
        await http.post('/local/cron/add', form.value as unknown as Record<string, unknown>)
      } catch (addErr) {
        // 3. 新增失败：回滚 — 用快照重建
        try {
          const rollback: CronForm = {
            job_name: oldSnapshot.job_name,
            job_minute: oldSnapshot.job_minute,
            job_hour: oldSnapshot.job_hour,
            job_day: oldSnapshot.job_day,
            job_month: oldSnapshot.job_month,
            job_week: oldSnapshot.job_week,
            job_hosts: Array.isArray(oldSnapshot.job_hosts) ? oldSnapshot.job_hosts : (oldSnapshot.job_hosts ? String(oldSnapshot.job_hosts).split(',').filter(Boolean) : []),
            job_groups: Array.isArray(oldSnapshot.job_groups) ? oldSnapshot.job_groups : (oldSnapshot.job_groups ? String(oldSnapshot.job_groups).split(',').filter(Boolean) : []),
            job_sys_user: oldSnapshot.job_sys_user,
            job_command: oldSnapshot.job_command,
            job_remarks: oldSnapshot.job_remarks || '',
          }
          await http.post('/local/cron/add', rollback as unknown as Record<string, unknown>)
          ElMessage.error(t('cron.msg.updateFailedRestored'))
        } catch (rollbackErr) {
          // 回滚也失败：手动提示用户
          ElMessage.error(t('cron.msg.updateRollbackFailed', { name: oldSnapshot.job_name }))
        }
        return
      }
      ElMessage.success(t('common.crud.updateSuccess'))
      dialogVisible.value = false
    } else {
      await http.post('/local/cron/add', form.value as unknown as Record<string, unknown>)
      ElMessage.success(t('common.crud.createSuccess'))
      if (keepOpen) {
        form.value.job_name = ''; form.value.job_command = ''; form.value.job_remarks = ''
      } else {
        dialogVisible.value = false
      }
    }
    loadData()
  } catch (e) {
    // 表单校验失败 / 删除失败等场景
    if (e && e !== false) ElMessage.error(t('common.crud.operationFail'))
  }
  finally { submitting.value = false }
}

// ===== 暂停 / 恢复 / 删除 =====
async function doPause(row: CronRow): Promise<void> {
  try {
    await pauseCron({ job_name: row.job_name } as unknown as Record<string, unknown>)
    loadData()
    ElMessage.success(t('cron.msg.paused'))
  } catch { ElMessage.error(t('common.crud.operationFail')) }
}
async function doResume(row: CronRow): Promise<void> {
  try {
    await resumeCron({ job_name: row.job_name } as unknown as Record<string, unknown>)
    loadData()
    ElMessage.success(t('cron.msg.resumed'))
  } catch { ElMessage.error(t('common.crud.operationFail')) }
}
async function doDelete(row: CronRow): Promise<void> {
  await ElMessageBox.confirm(t('common.crud.deleteConfirm', { entity: t('common.entity.cron') }), t('common.crud.prompt'), { type: 'warning' })
  try {
    await deleteCron({ job_name: row.job_name } as unknown as Record<string, unknown>)
    loadData()
    ElMessage.success(t('common.crud.deleteSuccess'))
  } catch { ElMessage.error(t('common.crud.deleteFail')) }
}

// ===== 查看最新执行结果 =====
async function openLog(row: CronRow): Promise<void> {
  logJobName.value = row.job_name
  runResults.value = []
  lastResultTime.value = ''
  expandedLogs.value = []
  logDialogVisible.value = true
  try {
    const res = (await getCronLastResult({ job_name: row.job_name } as unknown as Record<string, unknown>)) as unknown as RunResultResp
    if (res.code === 0) {
      runResults.value = res.results || []
      lastResultTime.value = res.time || ''
      expandedLogs.value = runResults.value.map((_, i) => i)
    }
  } catch {
    // 静默：执行结果获取失败仅留空
  }
}

// ===== 手动执行 =====
async function doRun(row: { job_name: string }): Promise<void> {
  logJobName.value = row.job_name
  runJobName.value = row.job_name
  runLoading.value = true
  runResults.value = []
  lastResultTime.value = ''
  expandedLogs.value = []
  logDialogVisible.value = true
  try {
    const res = (await runCron({ job_name: row.job_name } as unknown as Record<string, unknown>)) as unknown as RunResultResp
    if (res.code === 0) {
      runResults.value = res.results || []
      lastResultTime.value = '' // 手动执行不需要时间戳
      expandedLogs.value = runResults.value.map((_, i) => i)
      const failCnt = runResults.value.filter(r => r.error).length
      if (failCnt > 0) {
        ElMessage.warning(t('cron.msg.partialResult', { ok: runResults.value.length - failCnt, fail: failCnt }))
      } else {
        ElMessage.success(t('cron.msg.execDone'))
      }
    } else {
      ElMessage.error(res.msg || t('cron.msg.execFail'))
    }
  } catch { ElMessage.error(t('cron.msg.execFail')) }
  finally { runLoading.value = false; runJobName.value = '' }
}

// ===== 行内操作下拉（统一转发到已有 handler）=====
type RowAction = 'log' | 'edit' | 'run' | 'pause' | 'resume' | 'del'
// 模板调用入口 (避免模板内联做类型断言)
function onRowCommand(cmd: string, row: CronRow): void {
  void rowAction(cmd as RowAction, row)
}
async function rowAction(cmd: RowAction, row: CronRow): Promise<void> {
  if (cmd === 'log') return openLog(row)
  if (cmd === 'edit') return openEdit(row)
  if (cmd === 'run') return doRun(row)
  if (cmd === 'pause') return doPause(row)
  if (cmd === 'resume') return doResume(row)
  if (cmd === 'del') return doDelete(row)
}

// ===== 批量操作 =====
async function batchAction(type: BatchActionType): Promise<void> {
  if (!selectedRows.value.length) return
  if (type === 'del') {
    await ElMessageBox.confirm(t('cron.msg.batchDeleteConfirm'), t('common.crud.prompt'), { type: 'warning' })
  }
  const nameList = selectedRows.value.map(r => r.job_name)
  try {
    await batchCron({ job_name_list: nameList, job_type: type } as unknown as Record<string, unknown>)
    loadData(); ElMessage.success(t('cron.msg.operationSuccess'))
  } catch { ElMessage.error(t('common.crud.operationFail')) }
}

onMounted(() => { loadDeps(); loadData() })
</script>

<style scoped>
/* —— 执行用户名：单行截断 + ellipsis + hover tooltip —— */
.cron-sys-user {
  display: inline-block;
  max-width: 100%;
  font-family: var(--ogs-mono);
  font-size: 12px;
  color: var(--ogs-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
  line-height: 1.2;
}

/* —— 行内「操作」下拉 trigger（紧凑主色调，避免表格行过宽） —— */
.row-action-trigger {
  font-size: 12.5px !important;
  color: var(--ogs-primary-dark) !important;
  padding: 0 6px !important;
  font-weight: 500 !important;
}
.row-action-trigger:hover {
  color: var(--ogs-primary) !important;
  background: var(--ogs-primary-soft) !important;
}
.row-action-trigger .el-icon--right { margin-left: 2px; font-size: 10px; }

/* —— 批量操作下拉按钮上的选中数徽标 —— */
.batch-count {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 18px; height: 18px; padding: 0 5px;
  margin-left: 4px;
  background: var(--ogs-primary);
  color: #fff;
  border-radius: 9px;
  font-size: 11px; font-weight: 600;
  line-height: 1;
  font-family: var(--ogs-mono);
}
.batch-danger { color: var(--ogs-danger); }
.batch-danger-icon { color: var(--ogs-danger); }

/* —— 资产/组 单元格：上下两行（主机弹窗 + 组 chip 行） —— */
.cron-target-cell {
  display: flex;
  flex-direction: column;
  gap: 3px;
  align-items: flex-start;
  max-width: 100%;
}
.cron-target-groups {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  flex-wrap: wrap;
  max-width: 100%;
}

/* —— 弹窗内部的主机/组分段 —— */
.cron-target-section {
  border-bottom: 1px solid var(--ogs-border-subtle);
}
.cron-target-section:last-child { border-bottom: none; }
.cron-target-section-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px 6px;
  font-size: 11px;
  font-weight: 600;
  color: var(--ogs-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  background: var(--ogs-bg-sunken);
  border-bottom: 1px solid var(--ogs-border-subtle);
}
.cron-target-section-head .el-icon { color: var(--ogs-primary); }
.cron-target-section-count {
  margin-left: auto;
  font-family: var(--ogs-mono);
  font-size: 10.5px;
  font-weight: 500;
  color: var(--ogs-text-muted);
  text-transform: none;
  letter-spacing: 0;
}

.cron-log-body { max-height: 60vh; overflow-y: auto; }
.log-summary { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; }
.log-time { color: var(--ogs-text-secondary); font-size: 13px; margin-right: auto; }
.log-collapse { border: none; }
.log-host-title { display: flex; align-items: center; gap: 6px; }
.log-host-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.log-host-dot.dot-ok { background: #67C23A; }
.log-host-dot.dot-error { background: #F56C6C; }
.log-output {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px 16px;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  max-height: 300px;
  overflow-y: auto;
}
.log-output.is-error { color: #f56c6c; }
</style>
