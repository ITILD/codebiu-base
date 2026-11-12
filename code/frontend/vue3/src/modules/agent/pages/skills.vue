<!-- 技能中心(能力中心, REQ-018): 技能清单(Manifest 视图/调试) / 自定义 Skill / 外部能力(Skill Hub+MCP) / 调用记录 / job 编排 / 用量统计 -->
<template>
  <div p-3 md:p-4 w-full flex flex-col gap-3>
    <!-- 水墨页头 -->
    <InkPageHead title="技能中心" sub="技能清单、调试台与调用观测" seal="技" />

    <el-tabs v-model="activeTab">
      <!-- ============================== 技能清单 ============================== -->
      <el-tab-pane label="技能清单" name="skills">
        <div mb-3 flex flex-wrap items-center gap-2>
          <el-input
            v-model="skillKeyword" clearable class="w-full sm:w-56"
            placeholder="按名称/键/描述搜索" :prefix-icon="Search"
          />
          <el-select v-model="skillCategoryFilter" clearable class="w-32" placeholder="业务分类">
            <el-option v-for="(label, value) in categoryOptions" :key="value" :label="label" :value="value" />
          </el-select>
          <el-select v-model="skillNatureFilter" clearable class="w-32" placeholder="能力来源">
            <el-option v-for="(label, value) in natureOptions" :key="value" :label="label" :value="value" />
          </el-select>
          <span text-xs text-note-sub>共 {{ filteredSkills.length }} 项</span>
        </div>

        <el-table :data="filteredSkills" v-loading="skillsLoading" stripe w-full>
          <el-table-column label="名称" min-width="180">
            <template #default="{ row }">
              <div flex flex-col>
                <span flex items-center gap-1.5>
                  {{ row.name }}
                  <el-tag size="small" effect="plain" :type="sourceTagType(row.key)">
                    {{ sourceLabel(row.key) }}
                  </el-tag>
                </span>
                <span text-xs text-note-sub>{{ row.key }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="能力描述" min-width="220" show-overflow-tooltip />
          <el-table-column label="分类" width="80" align="center">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ categoryLabel(row.category) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="实现类型" width="96" align="center">
            <template #default="{ row }">
              <el-tag :type="skillTypeTagType(row.skill_type)" size="small">
                {{ skillTypeLabel(row.skill_type) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="能力来源" width="86" align="center">
            <template #default="{ row }">
              <el-tag :type="natureTagType(row.nature)" size="small">
                {{ natureLabel(row.nature) }}
              </el-tag>
            </template>
          </el-table-column>
          <!-- 能力需求徽标: required 红(缺失即失败) / optional 黄(缺失降级) / 能力组(组间任一可满足) -->
          <el-table-column label="能力需求" min-width="200">
            <template #default="{ row }">
              <div flex flex-wrap gap-1>
                <el-tag
                  v-for="cap in row.capabilities.required" :key="`r-${cap}`"
                  type="danger" size="small" effect="light"
                >
                  {{ cap }}
                </el-tag>
                <el-tag
                  v-for="cap in row.capabilities.optional" :key="`o-${cap}`"
                  type="warning" size="small" effect="light"
                >
                  {{ cap }}(可选)
                </el-tag>
                <el-tooltip
                  v-for="(group, gi) in row.capabilities.alternatives" :key="`a-${gi}`"
                  content="能力组: 组间任一组全部可满足即可运行, 落到降级组时结果标记降级"
                  placement="top"
                >
                  <el-tag type="info" size="small" effect="light">{{ group.join(' / ') }}</el-tag>
                </el-tooltip>
                <span
                  v-if="!row.capabilities.required.length && !row.capabilities.optional.length
                    && !row.capabilities.alternatives.length"
                  text-xs text-note-sub
                >无</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="智能体可调用" width="110" align="center">
            <template #default="{ row }">
              <el-tag :type="row.agent_callable ? 'success' : 'info'" size="small" effect="light">
                {{ row.agent_callable ? '可调用' : '仅人工' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="version" label="版本" width="64" align="center" />
          <el-table-column label="执行形态" min-width="120">
            <template #default="{ row }">
              <span text-xs>{{ row.execution.modes.join(' / ') }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" align="center">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="debugDrawerRef?.open(row.key)">
                调试
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ============================== 自定义 Skill ============================== -->
      <el-tab-pane label="自定义 Skill" name="custom">
        <div mb-3 flex items-center gap-2>
          <span text-xs text-note-sub>
            prompt 型自定义技能, 草稿发布后方可在技能清单与智能体对话中调用
          </span>
          <div flex-1 />
          <el-button v-if="canManageSkill" type="primary" @click="customDialogRef?.open()">
            <el-icon mr-1><Plus /></el-icon>新建自定义 Skill
          </el-button>
        </div>
        <el-table :data="customSkills" v-loading="customLoading" stripe w-full>
          <el-table-column label="技能" min-width="180">
            <template #default="{ row }">
              <div flex flex-col>
                <span>{{ row.name }}</span>
                <span text-xs text-note-sub>{{ row.key }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="描述" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">{{ row.description || '-' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="publishStatusTagType(row.status)" size="small">
                {{ publishStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="current_version" label="版本" width="64" align="center" />
          <el-table-column label="智能体可调用" width="110" align="center">
            <template #default="{ row }">
              <el-tag :type="row.agent_callable ? 'success' : 'info'" size="small" effect="light">
                {{ row.agent_callable ? '可调用' : '仅人工' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="owner_user_id" label="创建者" min-width="120" show-overflow-tooltip />
          <el-table-column label="操作" min-width="150" align="center">
            <template #default="{ row }">
              <template v-if="canManageSkill">
                <el-button
                  link type="primary" size="small" :disabled="row.status === 'deprecated'"
                  @click="customDialogRef?.open(row)"
                >
                  编辑
                </el-button>
                <el-button
                  link type="success" size="small" :disabled="row.status === 'deprecated'"
                  @click="handlePublish(row)"
                >
                  发布
                </el-button>
                <el-button
                  link type="danger" size="small" :disabled="row.status === 'deprecated'"
                  @click="handleDeprecate(row)"
                >
                  下线
                </el-button>
              </template>
              <span v-else text-xs text-note-sub>仅查看</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ============================== 外部能力(Skill Hub + MCP, REQ-018 批次 3) ============================== -->
      <el-tab-pane label="外部能力" name="external" lazy>
        <ExternalSkillsPanel @changed="loadSkills" />
      </el-tab-pane>

      <!-- ============================== 调用记录 ============================== -->
      <el-tab-pane label="调用记录" name="invocations">
        <div mb-3 flex flex-wrap items-center gap-2>
          <el-input
            :model-value="queryParams.skill_key as string" clearable class="w-full sm:w-64"
            placeholder="按技能全局键过滤(如 sys.doc_parse)"
            @update:model-value="(v: string) => (queryParams.skill_key = v)"
            @keyup.enter="handleSearch"
          />
          <el-select
            :model-value="queryParams.status_filter as string" clearable class="w-32"
            placeholder="状态"
            @update:model-value="(v: string) => (queryParams.status_filter = v)"
            @change="handleSearch"
          >
            <el-option v-for="s in statusOptions" :key="s" :label="statusLabel(s)" :value="s" />
          </el-select>
          <el-button type="primary" plain @click="handleSearch">查询</el-button>
          <span flex-1 />
          <span text-xs text-note-sub>本人调用记录(三入口全量可追溯)</span>
        </div>
        <el-table
          :data="tableData" v-loading="loading" stripe w-full
          @row-click="(row: InvocationItem) => invocationDialogRef?.open(row.invocation_id)"
        >
          <el-table-column prop="skill_key" label="技能键" min-width="160" show-overflow-tooltip />
          <el-table-column prop="mode" label="形态" width="80" align="center" />
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="降级" width="70" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.degraded" type="warning" size="small">降级</el-tag>
              <span v-else text-note-sub>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="entry" label="入口" width="80" align="center" />
          <el-table-column label="错误类型" min-width="130" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.error_class" class="text-[var(--el-color-danger)]">{{ row.error_class }}</span>
              <span v-else text-note-sub>-</span>
            </template>
          </el-table-column>
          <el-table-column label="耗时" width="90" align="center">
            <template #default="{ row }">
              {{ row.duration_ms != null ? `${row.duration_ms} ms` : '-' }}
            </template>
          </el-table-column>
          <el-table-column label="时间" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>
        <div mt-3 flex flex-wrap justify-center sm:justify-end>
          <el-pagination v-model:current-page="pagination.page" v-model:page-size="pagination.size"
            :total="total" layout="total, prev, pager, next"
            @size-change="fetchData" @current-change="fetchData" />
        </div>
      </el-tab-pane>

      <!-- ============================== 编排 Job ============================== -->
      <el-tab-pane label="编排 Job" name="jobs">
        <!-- 运行历史(REQ-018 批次 2): 分页 + agent_key/状态过滤, 行点击查详情 -->
        <div mb-3 flex flex-wrap items-center gap-2>
          <el-input
            :model-value="jobRunQueryParams.agent_key as string" clearable class="w-full sm:w-64"
            placeholder="按 job 键过滤(如 sys.ingest_documents)"
            @update:model-value="(v: string) => (jobRunQueryParams.agent_key = v)"
            @keyup.enter="handleJobRunSearch"
          />
          <el-select
            :model-value="jobRunQueryParams.status_filter as string" clearable class="w-32"
            placeholder="状态"
            @update:model-value="(v: string) => (jobRunQueryParams.status_filter = v)"
            @change="handleJobRunSearch"
          >
            <el-option v-for="s in statusOptions" :key="s" :label="statusLabel(s)" :value="s" />
          </el-select>
          <el-button type="primary" plain @click="handleJobRunSearch">查询</el-button>
          <span flex-1 />
          <span text-xs text-note-sub>本人提交的 job 运行; 失败/取消支持断点续跑</span>
        </div>
        <el-table
          :data="jobRunData" v-loading="jobRunLoading" stripe w-full
          @row-click="(row: JobRunListItem) => jobRunDialogRef?.open(row.job_run_id)"
        >
          <el-table-column prop="job_run_id" label="运行ID" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="font-mono text-xs">{{ row.job_run_id }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="agent_key" label="job 键" min-width="160" show-overflow-tooltip />
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="进度" min-width="110" align="center">
            <template #default="{ row }">
              {{ Math.round(row.progress?.percent ?? 0) }}%
              ({{ row.progress?.processed ?? 0 }}/{{ row.progress?.total ?? 0 }})
            </template>
          </el-table-column>
          <el-table-column label="错误" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.error" class="text-[var(--el-color-danger)]">{{ row.error }}</span>
              <span v-else text-note-sub>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="entry" label="入口" width="80" align="center" />
          <el-table-column label="创建时间" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="130" align="center">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click.stop="jobRunDialogRef?.open(row.job_run_id)">
                详情
              </el-button>
              <el-button
                v-if="canResumeRun(row)" link type="warning" size="small" :loading="resumingRunId === row.job_run_id"
                @click.stop="handleResumeRun(row)"
              >
                断点续跑
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <div mt-3 flex flex-wrap justify-center sm:justify-end>
          <el-pagination v-model:current-page="jobRunPagination.page" v-model:page-size="jobRunPagination.size"
            :total="jobRunTotal" layout="total, prev, pager, next"
            @size-change="fetchJobRuns" @current-change="fetchJobRuns" />
        </div>

        <!-- 内置 job Agent 清单(static_agent Manifest) -->
        <div mt-2 mb-2 flex items-center gap-2>
          <span text-sm font-medium>内置 job 定义</span>
          <span text-xs text-note-sub>展开查看步骤声明</span>
        </div>
        <el-table :data="jobs" v-loading="jobsLoading" stripe w-full>
          <el-table-column type="expand">
            <template #default="{ row }">
              <div px-4 py-2>
                <div mb-2 text-xs text-note-sub>
                  步骤声明(when 步骤级准入 / skip_if 展开项过滤 / on_error 失败策略)
                </div>
                <el-table :data="row.steps" border size="small">
                  <el-table-column prop="id" label="步骤ID" min-width="110" show-overflow-tooltip />
                  <el-table-column prop="skill" label="技能键" min-width="150" show-overflow-tooltip />
                  <el-table-column label="展开字段" min-width="110" show-overflow-tooltip>
                    <template #default="{ row: step }">
                      {{ step.fan_out ? `${step.fan_out} (键: ${step.item_key})` : '单项' }}
                    </template>
                  </el-table-column>
                  <el-table-column prop="when" label="when" min-width="140" show-overflow-tooltip>
                    <template #default="{ row: step }">{{ step.when ?? '-' }}</template>
                  </el-table-column>
                  <el-table-column prop="skip_if" label="skip_if" min-width="140" show-overflow-tooltip>
                    <template #default="{ row: step }">{{ step.skip_if ?? '-' }}</template>
                  </el-table-column>
                  <el-table-column prop="on_error" label="失败策略" width="90" align="center" />
                </el-table>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="Job" min-width="200">
            <template #default="{ row }">
              <div flex flex-col>
                <span>{{ row.name }}</span>
                <span text-xs text-note-sub>{{ row.agent_key }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="描述" min-width="240" show-overflow-tooltip />
          <el-table-column label="步骤数" width="80" align="center">
            <template #default="{ row }">{{ row.steps.length }}</template>
          </el-table-column>
          <el-table-column label="运行策略" min-width="150">
            <template #default="{ row }">
              <div flex flex-wrap gap-1>
                <el-tag size="small" effect="plain">优先级 {{ String(row.runtime_policy.priority_class ?? '-') }}</el-tag>
                <el-tag size="small" effect="plain">并发 {{ String(row.runtime_policy.max_parallel ?? '-') }}</el-tag>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ============================== 用量统计(REQ-018 批次 3) ============================== -->
      <el-tab-pane label="用量统计" name="usage" lazy>
        <UsageSummaryPanel />
      </el-tab-pane>
    </el-tabs>

    <!-- 技能调试抽屉(403 优雅处理) -->
    <SkillDebugDrawer ref="debugDrawerRef" :skills="skills" />
    <!-- 自定义 Skill 编辑对话框 -->
    <CustomSkillEditDialog ref="customDialogRef" @saved="loadCustomSkills" />
    <!-- 调用记录详情 -->
    <InvocationDetailDialog ref="invocationDialogRef" />
    <!-- job 运行详情(断点续跑) -->
    <JobRunDetailDialog ref="jobRunDialogRef" />
  </div>
</template>

<script setup lang="ts">
import { Plus, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listSkills, listInvocations, listAgentJobs, listJobRuns, resumeJobRun, listCustomSkills,
  publishCustomSkill, deprecateCustomSkill,
} from '../api/agent'
import type {
  InvocationItem, InvocationListParams, CustomSkillInfo, SkillInfo, AgentJobInfo,
  JobRunListItem, JobRunListParams,
} from '../types'
import {
  statusLabel, statusTagType, natureLabel, natureTagType,
  categoryLabel, publishStatusLabel, publishStatusTagType,
  skillTypeLabel, skillTypeTagType,
} from '../types/labels'
import { useTableQuery } from '@/common/composables/useTableQuery'
import { usePermission } from '@/common/composables/usePermission'
import SkillDebugDrawer from '../components/SkillDebugDrawer.vue'
import CustomSkillEditDialog from '../components/CustomSkillEditDialog.vue'
import InvocationDetailDialog from '../components/InvocationDetailDialog.vue'
import JobRunDetailDialog from '../components/JobRunDetailDialog.vue'
import ExternalSkillsPanel from '../components/ExternalSkillsPanel.vue'
import UsageSummaryPanel from '../components/UsageSummaryPanel.vue'

const route = useRoute()
const { hasPerm } = usePermission()
/** 自定义 Skill 管理(创建/编辑/发布/下线)按钮权限 */
const canManageSkill = computed(() => hasPerm('agent:skill:update'))

// ============================== 技能清单 ==============================
const skillsLoading = ref(false)
const skills = ref<SkillInfo[]>([])
const skillKeyword = ref('')
const skillCategoryFilter = ref('')
const skillNatureFilter = ref('')

const categoryOptions: Record<string, string> = {
  ingest: '入库', retrieval: '检索', generation: '生成', governance: '治理', action: '动作',
}
const natureOptions: Record<string, string> = { static: '静态', ai: '模型', hybrid: '混合' }

/** 技能来源徽标(按全局键命名空间: usr.自定义 / pack.社区包 / mcp.MCP / 其余内置) */
const sourceLabel = (key: string): string =>
  key.startsWith('usr.') ? '自定义' : key.startsWith('pack.') ? '社区包' : key.startsWith('mcp.') ? 'MCP' : '内置'
const sourceTagType = (key: string): 'warning' | 'info' | 'success' =>
  key.startsWith('usr.') || key.startsWith('pack.') || key.startsWith('mcp.') ? 'warning' : 'info'

/** 关键词/分类/能力来源本地过滤 */
const filteredSkills = computed(() => {
  const kw = skillKeyword.value.trim().toLowerCase()
  return skills.value.filter(s =>
    (!kw || s.name.toLowerCase().includes(kw)
      || s.key.toLowerCase().includes(kw)
      || s.description.toLowerCase().includes(kw))
    && (!skillCategoryFilter.value || s.category === skillCategoryFilter.value)
    && (!skillNatureFilter.value || s.nature === skillNatureFilter.value),
  )
})

const loadSkills = async () => {
  try {
    skillsLoading.value = true
    skills.value = await listSkills()
  } catch (error) {
    console.error('获取技能清单失败:', error)
    ElMessage.error('获取技能清单失败')
  } finally {
    skillsLoading.value = false
  }
}

// ============================== 自定义 Skill ==============================
const customLoading = ref(false)
const customSkills = ref<CustomSkillInfo[]>([])
const customLoaded = ref(false)

const loadCustomSkills = async () => {
  try {
    customLoading.value = true
    customSkills.value = await listCustomSkills()
    customLoaded.value = true
  } catch (error) {
    console.error('获取自定义 Skill 列表失败:', error)
  } finally {
    customLoading.value = false
  }
}

/** 发布(注册表登记后方可调用) */
const handlePublish = async (row: CustomSkillInfo) => {
  try {
    await ElMessageBox.confirm(
      `确定发布「${row.name}」吗？发布后即可在技能清单与智能体对话中调用`,
      '发布自定义 Skill',
      { type: 'info', confirmButtonText: '发布', cancelButtonText: '取消' },
    )
    await publishCustomSkill(row.skill_id)
    ElMessage.success('已发布')
    await loadCustomSkills()
    await loadSkills()
  } catch (error) {
    if (error !== 'cancel') console.error('发布失败:', error)
  }
}

/** 下线(注册表反注册, 历史调用记录保留) */
const handleDeprecate = async (row: CustomSkillInfo) => {
  try {
    await ElMessageBox.confirm(
      `确定下线「${row.name}」吗？新调用将被拒绝, 历史调用记录保留可追溯`,
      '下线自定义 Skill',
      { type: 'warning', confirmButtonText: '下线', cancelButtonText: '取消' },
    )
    await deprecateCustomSkill(row.skill_id)
    ElMessage.success('已下线')
    await loadCustomSkills()
    await loadSkills()
  } catch (error) {
    if (error !== 'cancel') console.error('下线失败:', error)
  }
}

// ============================== 调用记录 ==============================
const statusOptions = ['pending', 'running', 'succeeded', 'failed', 'cancelled']
const {
  pagination, queryParams, tableData, total, loading, fetchData, handleSearch,
} = useTableQuery<InvocationItem>(
  params => listInvocations(params as InvocationListParams),
  { defaultQuery: { skill_key: '', status_filter: undefined }, immediate: false },
)
const invocationsLoaded = ref(false)

const formatTime = (iso: string) => {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}

// ============================== 编排 Job ==============================
const jobsLoading = ref(false)
const jobs = ref<AgentJobInfo[]>([])
const jobsLoaded = ref(false)

const loadJobs = async () => {
  try {
    jobsLoading.value = true
    jobs.value = await listAgentJobs()
    jobsLoaded.value = true
  } catch (error) {
    console.error('获取 job 清单失败:', error)
  } finally {
    jobsLoading.value = false
  }
}

// 运行历史(REQ-018 批次 2): 分页查询本人提交的 job 运行
const {
  pagination: jobRunPagination, queryParams: jobRunQueryParams, tableData: jobRunData,
  total: jobRunTotal, loading: jobRunLoading, fetchData: fetchJobRuns,
  handleSearch: handleJobRunSearch,
} = useTableQuery<JobRunListItem>(
  params => listJobRuns(params as JobRunListParams),
  { defaultQuery: { agent_key: '', status_filter: undefined }, immediate: false },
)
const jobRunsLoaded = ref(false)

/** 续跑按钮可见: 失败/取消态且具备 skill:invoke 权限(与后端 resume 端点权限一致) */
const canResumeRun = (row: JobRunListItem) =>
  (row.status === 'failed' || row.status === 'cancelled') && hasPerm('agent:skill:invoke')

/** 正在续跑的运行ID(行内按钮 loading 态) */
const resumingRunId = ref('')

/** 断点续跑(已成功项直接复用, 从失败/取消位置继续), 成功后刷新列表 */
const handleResumeRun = async (row: JobRunListItem) => {
  try {
    resumingRunId.value = row.job_run_id
    await resumeJobRun(row.job_run_id)
    ElMessage.success('已发起断点续跑')
    await fetchJobRuns()
  } catch (error) {
    console.error('断点续跑失败:', error)
    ElMessage.error(error instanceof Error ? error.message : '断点续跑失败')
  } finally {
    resumingRunId.value = ''
  }
}

// ============================== 页签懒加载与外部跳转 ==============================
const activeTab = ref('skills')
const debugDrawerRef = ref<InstanceType<typeof SkillDebugDrawer>>()
const customDialogRef = ref<InstanceType<typeof CustomSkillEditDialog>>()
const invocationDialogRef = ref<InstanceType<typeof InvocationDetailDialog>>()
const jobRunDialogRef = ref<InstanceType<typeof JobRunDetailDialog>>()

// 首次切入各页签时拉取数据(技能清单在挂载即拉, 供调试抽屉与自定义编辑回填共用)
// external/usage 页签为 lazy 渲染, 面板组件挂载(=切入)即自加载, 无需此处处理
watch(activeTab, (tab) => {
  if (tab === 'custom' && !customLoaded.value) loadCustomSkills()
  if (tab === 'invocations' && !invocationsLoaded.value) {
    invocationsLoaded.value = true
    fetchData()
  }
  if (tab === 'jobs' && !jobsLoaded.value) {
    loadJobs()
    jobRunsLoaded.value = true
    fetchJobRuns()
  }
})

onMounted(async () => {
  loadSkills()
  // 外部跳转支持: /agent/skills?tab=jobs&run={job_run_id}(如知识库入库编排入口)
  const tab = String(route.query.tab ?? '')
  if (['skills', 'custom', 'external', 'invocations', 'jobs', 'usage'].includes(tab)) {
    activeTab.value = tab
    if (tab === 'jobs') {
      loadJobs()
      jobRunsLoaded.value = true
      fetchJobRuns()
      const runId = String(route.query.run ?? '')
      if (runId) jobRunDialogRef.value?.open(runId)
    }
  }
})
</script>
