<!-- 动态配置管理页: 按 sys_config 分组 schema 渲染通用配置表单 -->
<template>
  <div p-4 md:p-6>
    <InkPageHead
      title="通用配置"
      sub="平台运行参数的集中配置"
      seal="配"
    >
      <template #actions>
        <el-button :icon="Refresh" plain @click="load">刷新</el-button>
      </template>
    </InkPageHead>

    <!-- 双栏自适应: 桌面(lg+)左右布局, 手机/平板纵向堆叠(分组菜单变顶部横滚条) -->
    <div class="flex flex-col lg:flex-row gap-4 lg:h-full">
      <!-- 桌面: 左侧配置组菜单(固定窄栏) -->
      <el-aside
        v-if="isLg"
        width="220px"
        class="bg-note-card border border-note rounded-xl shadow-note overflow-hidden"
      >
        <el-menu :default-active="activeGroup" class="border-r-0" @select="(i: string) => (activeGroup = i)">
          <el-menu-item v-for="g in groups" :key="g.group" :index="g.group">
            <span>{{ g.name }}</span>
            <el-tag v-if="g.restart_required" size="small" type="warning" class="ml-auto">重启</el-tag>
          </el-menu-item>
        </el-menu>
      </el-aside>

      <!-- 手机/平板: 顶部横向滚动分组条(与设置页导航同风格, 避免窄栏挤压表单) -->
      <nav
        v-else
        aria-label="配置分组"
        class="flex gap-1 overflow-x-auto bg-note-card border border-note rounded-xl shadow-note p-2 shrink-0 scrollbar-hide"
      >
        <button
          v-for="g in groups"
          :key="g.group"
          type="button"
          class="flex items-center gap-1 rounded px-3 py-2 text-sm whitespace-nowrap transition-colors cursor-pointer"
          :class="activeGroup === g.group
            ? 'bg-note-green/10 text-note-green font-medium'
            : 'text-note-sub hover:bg-note-tint'"
          :aria-pressed="activeGroup === g.group"
          @click="activeGroup = g.group"
        >
          {{ g.name }}
          <el-tag v-if="g.restart_required" size="small" type="warning">重启</el-tag>
        </button>
      </nav>

      <!-- 右侧: 组表单(由后端字段元数据驱动, 新增配置组前端零改动) -->
      <el-main class="bg-note-card border border-note rounded-xl shadow-note overflow-auto">
        <template v-if="current">
          <div class="mb-4">
            <h2 class="text-lg font-bold text-note">{{ current.name }}</h2>
            <p class="text-sm text-note-sub mt-1">{{ current.description }}</p>
            <el-alert
              v-if="current.restart_required"
              type="warning" :closable="false" show-icon class="mt-2"
              title="保存后需重启后端服务生效"
            />
            <p v-if="current.updated_at" class="text-xs text-note-sub mt-2">
              最近更新: {{ current.updated_at.replace('T', ' ').slice(0, 19) }}
              <template v-if="current.updated_by"> · {{ current.updated_by }}</template>
            </p>
          </div>
          <!-- 标签位置随断点: 手机/平板置顶标签(窄屏左置 180px 标签会挤压控件), 桌面恢复左置 -->
          <el-form :label-position="isLg ? 'left' : 'top'" :label-width="isLg ? '180px' : undefined">
            <el-form-item v-for="f in current.fields" :key="f.key" :label="f.title">
              <div class="w-full">
                <!-- 密钥: 留空保持不变; 输入空格+保存=清除 -->
                <el-input
                  v-if="f.type === 'secret'" v-model="form[f.key]" type="password" show-password
                  :placeholder="f.has_value ? '已配置 · 留空不变' : '未配置'"
                />
                <!-- 布尔 -->
                <el-switch v-else-if="f.type === 'bool'" v-model="form[f.key]" />
                <!-- 数字 -->
                <el-input-number
                  v-else-if="f.type === 'int' || f.type === 'float'"
                  v-model="form[f.key]" :step="f.type === 'float' ? 0.5 : 1"
                  class="!w-52"
                />
                <!-- 枚举 -->
                <el-select v-else-if="f.type === 'enum'" v-model="form[f.key]" class="!w-72">
                  <el-option v-for="o in f.options" :key="o" :label="o" :value="o" />
                </el-select>
                <!-- 列表(tags 输入) -->
                <el-select
                  v-else-if="f.type === 'list'" v-model="form[f.key]" multiple filterable allow-create
                  default-first-option class="!w-full" placeholder="输入后回车添加"
                />
                <!-- 文本 -->
                <el-input v-else v-model="form[f.key]" />
                <div v-if="fieldHint(f)" class="text-xs text-note-sub mt-1">{{ fieldHint(f) }}</div>
              </div>
            </el-form-item>
          </el-form>
          <div class="flex justify-end gap-2 mt-2">
            <el-button @click="resetForm">放弃修改</el-button>
            <el-button type="primary" :loading="saving" @click="save">保存配置</el-button>
          </div>
        </template>
      </el-main>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 系统通用配置页(管理员): 表单由后端字段元数据驱动, 新增配置组前端零改动
 * 左侧组列表 + 右侧表单; 密钥字段留空提交=保持不变
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { listSysConfigs, updateSysConfig } from '../api/sys_config';
import type { ConfigGroup } from '../api/sys_config';
// 响应式断点: 分组菜单双形态(桌面侧栏/窄屏横滚条)与表单标签位置切换
import { useResponsive } from '@/common/composables/useResponsive';

const { isLg } = useResponsive();

const groups = ref<ConfigGroup[]>([])
const activeGroup = ref('')
const saving = ref(false)
// 动态配置表单(字段类型由后端元数据驱动, 值类型不固定故用 any 承接)
const form = reactive<Record<string, any>>({})

const current = computed(() => groups.value.find(g => g.group === activeGroup.value))

/** 字段下方小字说明: 优先后端描述, 密钥字段无描述时提示清除方式(placeholder 保持简短) */
function fieldHint(f: { description?: string; type: string }): string {
  return f.description || (f.type === 'secret' ? '输入空格并保存，可清除已存密钥' : '')
}

/** 字段值载入表单(密钥字段留空, 不回显明文) */
function resetForm() {
  if (!current.value) return
  for (const f of current.value.fields) {
    form[f.key] = f.type === 'secret' ? '' : (f.value as unknown)
  }
}

/** 表单打平的 key("tavily.api_key") → 嵌套结构提交 */
function buildPayload(): Record<string, unknown> {
  const payload: Record<string, unknown> = {}
  for (const f of current.value?.fields ?? []) {
    const v = form[f.key]
    if (f.type === 'secret' && v === '') continue // 密钥留空=保持不变
    const parts = f.key.split('.')
    let cur = payload
    for (let i = 0; i < parts.length - 1; i++) {
      cur[parts[i]] = (cur[parts[i]] as Record<string, unknown>) ?? {}
      cur = cur[parts[i]] as Record<string, unknown>
    }
    cur[parts[parts.length - 1]] = v
  }
  return payload
}

/** 拉取全部配置组(保存/刷新共用) */
async function load() {
  const { groups: gs } = await listSysConfigs()
  groups.value = gs
  if (!activeGroup.value) activeGroup.value = gs[0]?.group ?? ''
  resetForm()
}

async function save() {
  if (!current.value) return
  saving.value = true
  try {
    await updateSysConfig(current.value.group, buildPayload())
    ElMessage.success(`${current.value.name} 已保存${current.value.restart_required ? '(重启后生效)' : ''}`)
    await load()
  } finally {
    saving.value = false
  }
}

onMounted(load)
// 切组时重载表单
watch(activeGroup, resetForm)
</script>

<style scoped>
/* 桌面侧栏不随表单内容压缩(仅 lg 渲染, 窄屏由横滚分组条接管) */
:deep(.el-aside) { flex-shrink: 0; }
</style>
