<template>
  <!-- 向量数据库面板: 概览统计 + 向量表清单(数据由本面板拉取, refresh 供页面调度) -->
  <template v-if="vectorInfo?.type">
    <!-- 概览统计 -->
    <div class="stat-row" mb-4>
      <div class="stat-card">
        <div class="stat-icon icon-blue">
          <el-icon :size="22"><Collection /></el-icon>
        </div>
        <div class="stat-meta">
          <div class="stat-value">{{ vectorTables.length }}</div>
          <div class="stat-label">向量表</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon icon-green">
          <el-icon :size="22"><Tickets /></el-icon>
        </div>
        <div class="stat-meta">
          <div class="stat-value">{{ totalVectors.toLocaleString() }}</div>
          <div class="stat-label">总数据量</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon icon-orange">
          <el-icon :size="22"><Cpu /></el-icon>
        </div>
        <div class="stat-meta">
          <div class="stat-value">{{ vectorInfo.type }}</div>
          <div class="stat-label">实现类型</div>
        </div>
      </div>
    </div>

    <el-card shadow="never">
      <el-table :data="vectorTables" v-loading="vectorLoading" stripe w-full>
        <el-table-column type="index" label="#" width="60" />
        <el-table-column prop="name" label="表名" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <span font-mono text-13px>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="field_count" label="字段数" width="100" align="center">
          <template #default="{ row }">
            <span v-if="row.field_count != null" font-mono>{{ row.field_count }}</span>
            <span v-else text-subtle>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="vector_dims" label="向量维度" width="110" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.vector_dims" size="small" effect="plain" font-mono>
              {{ row.vector_dims }}
            </el-tag>
            <span v-else text-subtle>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="row_count" label="数据条数" width="140" align="right" sortable>
          <template #default="{ row }">
            <span v-if="row.row_count != null" font-mono>{{ row.row_count.toLocaleString() }}</span>
            <span v-else text-subtle>-</span>
          </template>
        </el-table-column>
      </el-table>

      <el-empty
        v-if="!vectorLoading && vectorTables.length === 0"
        description="暂无向量表"
        :image-size="72"
      />
    </el-card>
  </template>
  <el-card v-else shadow="never">
    <el-empty v-loading="vectorLoading" description="未启用向量数据库" :image-size="72" />
  </el-card>
</template>

<script setup lang="ts">
// 向量数据库面板: 自行拉取向量库信息, expose.refresh 供页面刷新调度
import { computed, ref } from 'vue'
import { Collection, Cpu, Tickets } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { listVectorTables, type DbVectorInfo } from '@/modules/main/api/db'

const vectorLoading = ref(false)
const vectorInfo = ref<DbVectorInfo | null>(null)

// 向量表清单与总量统计
const vectorTables = computed(() => vectorInfo.value?.tables ?? [])
const totalVectors = computed(() =>
  vectorTables.value.reduce((sum, t) => sum + (t.row_count || 0), 0),
)

/** 刷新向量库信息(供页面调度), 返回是否成功 */
const refresh = async (): Promise<boolean> => {
  try {
    vectorLoading.value = true
    vectorInfo.value = await listVectorTables()
    return true
  } catch (error) {
    console.error('获取向量库信息失败:', error)
    ElMessage.error('获取向量库信息失败')
    return false
  } finally {
    vectorLoading.value = false
  }
}

defineExpose({ refresh })
</script>

<style scoped>
/* 概览统计卡片 */
.stat-row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.stat-card {
  flex: 1;
  min-width: 180px;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 20px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  transition: box-shadow 0.2s;
}

.stat-card:hover {
  box-shadow: var(--el-box-shadow-light);
}

.stat-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 8px;
  flex-shrink: 0;
}

.icon-blue {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.icon-green {
  color: var(--el-color-success);
  background: var(--el-color-success-light-9);
}

.icon-orange {
  color: var(--el-color-warning);
  background: var(--el-color-warning-light-9);
}

.stat-value {
  font-size: 20px;
  font-weight: 600;
  line-height: 1.3;
  font-variant-numeric: tabular-nums;
}

.stat-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

/* 文本色工具类 */
.text-subtle {
  color: var(--el-text-color-placeholder);
}
</style>
