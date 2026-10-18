<template>
  <!-- 图数据库面板: 运行信息键值对展示(数据由本面板拉取, refresh 供页面调度) -->
  <el-card v-if="graphInfo?.type" shadow="never">
    <template #header>
      <div class="card-head">运行信息</div>
    </template>
    <el-descriptions :column="2" border>
      <el-descriptions-item v-for="[gkey, gvalue] in graphEntries" :key="gkey" :label="gkey">
        <template v-if="typeof gvalue === 'boolean'">
          <el-tag :type="gvalue ? 'success' : 'danger'" size="small" effect="plain">
            {{ gvalue ? '已连接' : '未连接' }}
          </el-tag>
        </template>
        <span v-else font-mono text-13px>{{ gvalue }}</span>
      </el-descriptions-item>
    </el-descriptions>
  </el-card>
  <el-card v-else shadow="never">
    <el-empty v-loading="graphLoading" description="未启用图数据库" :image-size="72" />
  </el-card>
</template>

<script setup lang="ts">
// 图数据库面板: 自行拉取图库运行信息(实现自述键值对), expose.refresh 供页面刷新调度
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getGraphInfo, type DbGraphInfo } from '@/modules/main/api/db'

const graphLoading = ref(false)
const graphInfo = ref<DbGraphInfo | null>(null)

/** 图库信息键值对(剔除空值后渲染) */
const graphEntries = computed(() =>
  Object.entries(graphInfo.value ?? {}).filter(([, v]) => v !== null && v !== undefined),
)

/** 刷新图库信息(供页面调度), 返回是否成功 */
const refresh = async (): Promise<boolean> => {
  try {
    graphLoading.value = true
    graphInfo.value = await getGraphInfo()
    return true
  } catch (error) {
    console.error('获取图数据库信息失败:', error)
    ElMessage.error('获取图数据库信息失败')
    return false
  } finally {
    graphLoading.value = false
  }
}

defineExpose({ refresh })
</script>

<style scoped>
/* 卡片头部标题 */
.card-head {
  font-size: 14px;
  font-weight: 600;
}
</style>
