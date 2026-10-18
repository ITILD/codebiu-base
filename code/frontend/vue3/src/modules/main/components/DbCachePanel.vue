<template>
  <!-- Redis 缓存面板: 概览统计 + 运行信息(数据由本面板拉取, refresh 供页面调度) -->
  <template v-if="cacheInfo?.type">
    <!-- 概览统计 -->
    <div class="stat-row" mb-4>
      <div class="stat-card">
        <div class="stat-icon icon-blue">
          <el-icon :size="22"><Key /></el-icon>
        </div>
        <div class="stat-meta">
          <div class="stat-value">{{ (cacheInfo.dbsize ?? 0).toLocaleString() }}</div>
          <div class="stat-label">键数量</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon icon-green">
          <el-icon :size="22"><Coin /></el-icon>
        </div>
        <div class="stat-meta">
          <div class="stat-value">{{ cacheInfo.used_memory_human || '-' }}</div>
          <div class="stat-label">内存占用</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon icon-orange">
          <el-icon :size="22"><Odometer /></el-icon>
        </div>
        <div class="stat-meta">
          <div class="stat-value">
            {{ cacheInfo.hit_rate != null ? `${cacheInfo.hit_rate}%` : '-' }}
          </div>
          <div class="stat-label">缓存命中率</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon icon-purple">
          <el-icon :size="22"><Timer /></el-icon>
        </div>
        <div class="stat-meta">
          <div class="stat-value">{{ cacheInfo.uptime_in_days ?? '-' }}</div>
          <div class="stat-label">运行天数</div>
        </div>
      </div>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="card-head">运行信息{{ cacheInfo.redis_version ? `（Redis ${cacheInfo.redis_version}）` : '' }}</div>
      </template>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="实现类型">{{ cacheInfo.type }}</el-descriptions-item>
        <el-descriptions-item label="键数量">{{ (cacheInfo.dbsize ?? 0).toLocaleString() }}</el-descriptions-item>
        <el-descriptions-item label="内存占用">{{ cacheInfo.used_memory_human || '-' }}</el-descriptions-item>
        <el-descriptions-item label="最大内存">{{ cacheInfo.maxmemory_human || '不限制' }}</el-descriptions-item>
        <el-descriptions-item label="连接客户端">{{ cacheInfo.connected_clients ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="运行天数">{{ cacheInfo.uptime_in_days ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="键空间命中">{{ (cacheInfo.keyspace_hits ?? 0).toLocaleString() }}</el-descriptions-item>
        <el-descriptions-item label="键空间未命中">{{ (cacheInfo.keyspace_misses ?? 0).toLocaleString() }}</el-descriptions-item>
      </el-descriptions>
    </el-card>
  </template>
  <el-card v-else shadow="never">
    <el-empty v-loading="cacheLoading" description="未启用缓存数据库" :image-size="72" />
  </el-card>
</template>

<script setup lang="ts">
// Redis 缓存面板: 自行拉取缓存运行信息, expose.refresh 供页面刷新调度
import { ref } from 'vue'
import { Key, Coin, Odometer, Timer } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getCacheInfo, type DbCacheInfo } from '@/modules/main/api/db'

const cacheLoading = ref(false)
const cacheInfo = ref<DbCacheInfo | null>(null)

/** 刷新缓存信息(供页面调度), 返回是否成功 */
const refresh = async (): Promise<boolean> => {
  try {
    cacheLoading.value = true
    cacheInfo.value = await getCacheInfo()
    return true
  } catch (error) {
    console.error('获取缓存信息失败:', error)
    ElMessage.error('获取缓存信息失败')
    return false
  } finally {
    cacheLoading.value = false
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

.icon-purple {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
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

/* 卡片头部标题 */
.card-head {
  font-size: 14px;
  font-weight: 600;
}
</style>
