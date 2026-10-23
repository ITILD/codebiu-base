<template>
  <div p-4 md:p-6 w-full class="max-w-5xl mx-auto">
    <!-- 水墨页头 -->
    <InkPageHead title="网页搜索" seal="搜">
      <template #sub>
        多引擎网页搜索与连通性验证
      </template>
    </InkPageHead>

    <!-- 搜索参数区 -->
    <div page-card mb-5>
      <div flex flex-col gap-4>
        <!-- 关键词 + 搜索按钮 -->
        <div flex flex-wrap items-center gap-3>
          <el-input
            v-model="query"
            class="flex-1"
            min-w="220px"
            placeholder="输入关键词搜索, 回车直接搜索"
            maxlength="500"
            clearable
            :spellcheck="false"
            @keyup.enter="handleSearch"
          />
          <el-button type="primary" :loading="loading" :disabled="!query.trim() || loading" @click="handleSearch">
            {{ loading ? '搜索中…' : '搜 索' }}
          </el-button>
        </div>

        <!-- 筛选条件 -->
        <div flex flex-wrap items-center gap-3>
          <span text-note-sub text-sm>引擎:</span>
          <el-select v-model="engine" style="width: 200px" :loading="enginesLoading">
            <el-option
              v-for="item in engines"
              :key="item.name"
              :value="item.name"
              :label="item.display_name + (item.available ? (item.is_default ? '（默认）' : '') : '（未配置）')"
              :disabled="!item.available"
            >
              <div flex items-center justify-between gap-3>
                <span>{{ item.display_name }}</span>
                <span v-if="!item.available" text-xs text-note-accent>未配置 Key</span>
                <span v-else-if="item.is_default" text-xs text-note-sub>默认</span>
              </div>
            </el-option>
          </el-select>

          <span text-note-sub text-sm>条数:</span>
          <el-select v-model="limit" style="width: 100px">
            <el-option v-for="n in [5, 10, 15, 20, 30]" :key="n" :value="n" :label="`${n} 条`" />
          </el-select>

          <span text-note-sub text-sm>时间:</span>
          <el-select v-model="dateRange" style="width: 120px">
            <el-option v-for="opt in dateRangeOptions" :key="opt.value" :value="opt.value" :label="opt.label" />
          </el-select>
        </div>

        <!-- 引擎连通性提示 -->
        <div v-if="engines.length" text-xs text-note-sub>
          可用引擎 {{ engines.filter(e => e.available).length }}/{{ engines.length }}：
          <span v-for="(item, i) in engines" :key="item.name">
            {{ item.display_name }}{{ item.available ? '' : '（未配置）' }}{{ i < engines.length - 1 ? ' · ' : '' }}
          </span>
          <span v-if="engines.some(e => !e.available)" text-note-accent ml-2>未配置引擎可在「数据与配置 → 通用配置 → 网页搜索」中补齐 API Key</span>
        </div>
      </div>
    </div>

    <!-- 结果区(搜索过才渲染) -->
    <div v-if="searched" page-card>
      <div flex items-center justify-between mb-4>
        <div font-bold text-note>
          搜索结果
          <span v-if="response" text-sm text-note-sub ml-2>
            共 {{ response.total }} 条 · 引擎 {{ response.engine }}
          </span>
        </div>
        <el-tag v-if="response" size="small" type="info">{{ response.query }}</el-tag>
      </div>

      <div v-loading="loading">
        <div v-if="results.length" flex flex-col gap-4>
          <div
            v-for="(item, i) in results"
            :key="item.url"
            p-4
            border
            border-solid
            border-note
            class="rounded-note-md hover:border-note-green"
            transition-colors
          >
            <div flex items-baseline gap-2 mb-1>
              <span text-note-sub text-sm>{{ i + 1 }}.</span>
              <a
                :href="item.url"
                target="_blank"
                rel="noopener noreferrer"
                font-medium
                text-blue
                hover:underline
                break-all
              >{{ item.title }}</a>
            </div>
            <div v-if="item.description" text-sm text-note-sub mb-2 leading-relaxed>{{ item.description }}</div>
            <div flex flex-wrap items-center gap-3 text-xs text-note-sub>
              <span v-if="item.source">来源: {{ item.source }}</span>
              <span>引擎: {{ item.engine }}</span>
              <span v-if="item.published_date">发布: {{ item.published_date }}</span>
            </div>
          </div>
        </div>

        <el-empty v-else-if="!loading" description="未检索到相关结果, 可尝试更换关键词或引擎" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// 网页搜索测试页(REQ-015): 引擎选择/搜索/结果渲染; 非分页接口, 手写 loading+results 模式
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { DateRange, Engine, EngineInfo, SearchResponse } from '../types/websearch'
import { listEngines, searchWeb } from '../api/websearch'

// 搜索参数
const query = ref('')
const engine = ref<Engine | undefined>(undefined)
const limit = ref(10)
const dateRange = ref<DateRange>('any')

const dateRangeOptions: { value: DateRange; label: string }[] = [
  { value: 'any', label: '不限时间' },
  { value: 'day', label: '一天内' },
  { value: 'week', label: '一周内' },
  { value: 'month', label: '一月内' },
  { value: 'year', label: '一年内' },
]

// 引擎清单(连通性即 available 状态)
const engines = ref<EngineInfo[]>([])
const enginesLoading = ref(false)

// 搜索结果
const loading = ref(false)
const searched = ref(false)
const response = ref<SearchResponse | null>(null)
const results = computed(() => response.value?.results ?? [])

// 加载引擎清单并默认选中默认引擎
const loadEngines = async () => {
  enginesLoading.value = true
  try {
    const data: EngineInfo[] = await listEngines()
    engines.value = data
    const def = data.find(e => e.is_default && e.available) ?? data.find(e => e.available)
    if (def) engine.value = def.name
  } catch (error) {
    console.error('获取引擎清单失败:', error)
    ElMessage.error('获取引擎清单失败: ' + (error instanceof Error ? error.message : '未知错误'))
  } finally {
    enginesLoading.value = false
  }
}

// 执行搜索
const handleSearch = async () => {
  const q = query.value.trim()
  if (!q) return
  loading.value = true
  searched.value = true
  try {
    response.value = await searchWeb({
      query: q,
      engine: engine.value,
      limit: limit.value,
      date_range: dateRange.value,
    })
  } catch (error) {
    // 引擎未配置/参数错误(400)与引擎请求失败(502)的 detail 由 http 层解出
    console.error('搜索失败:', error)
    ElMessage.error('搜索失败: ' + (error instanceof Error ? error.message : '未知错误'))
    response.value = null
  } finally {
    loading.value = false
  }
}

onMounted(loadEngines)
</script>
