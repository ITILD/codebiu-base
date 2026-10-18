<!-- 数据监测页: 关系库/向量库/缓存/图库运行信息面板(四子面板) -->
<template>
  <div p-4 md:p-6>
    <InkPageHead title="数据监测" sub="各类数据库的数据量与运行状态" seal="测">
      <template #actions>
        <el-input
          v-if="activeTab === 'rel'"
          v-model="keyword"
          placeholder="按表名/注释搜索"
          clearable
          w-56
          @clear="fetchActive"
          @keyup.enter="fetchActive"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-button :icon="Refresh" plain @click="fetchActive">刷新</el-button>
      </template>
    </InkPageHead>

    <!-- Tab 壳: 各面板组件自行拉数, 页面只负责刷新调度(懒加载/刷新按钮/关键字搜索) -->
    <el-tabs v-model="activeTab" @tab-change="handleTabChange">
      <el-tab-pane label="关系数据库" name="rel">
        <DbRelPanel ref="relPanelRef" :keyword="keyword" />
      </el-tab-pane>
      <el-tab-pane label="向量数据库" name="vector">
        <DbVectorPanel ref="vectorPanelRef" />
      </el-tab-pane>
      <el-tab-pane label="Redis 缓存" name="cache">
        <DbCachePanel ref="cachePanelRef" />
      </el-tab-pane>
      <el-tab-pane label="图数据库" name="graph">
        <DbGraphPanel ref="graphPanelRef" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
// 数据监测页(编排层): el-tabs 壳 + 刷新调度; 各 tab 的数据拉取与展示内聚于对应面板组件
import { nextTick, onMounted, ref } from 'vue'
import { Search, Refresh } from '@element-plus/icons-vue'
import DbRelPanel from '../components/DbRelPanel.vue'
import DbVectorPanel from '../components/DbVectorPanel.vue'
import DbCachePanel from '../components/DbCachePanel.vue'
import DbGraphPanel from '../components/DbGraphPanel.vue'

// ==================== Tab 状态 ====================
type DbTab = 'rel' | 'vector' | 'cache' | 'graph'
const activeTab = ref<DbTab>('rel')
/** 已加载过的 tab(懒加载, 切换时首次拉取) */
const loadedTabs = new Set<DbTab>()

// 关系库搜索关键字(仅关系库 tab 展示, 回车/清空时触发当前面板刷新)
const keyword = ref('')

// ==================== 刷新调度 ====================
// 面板实例(统一 expose.refresh 供页面调度; 关系库面板另有 resize 供图表自适应)
const relPanelRef = ref<InstanceType<typeof DbRelPanel>>()
const vectorPanelRef = ref<InstanceType<typeof DbVectorPanel>>()
const cachePanelRef = ref<InstanceType<typeof DbCachePanel>>()
const graphPanelRef = ref<InstanceType<typeof DbGraphPanel>>()

/** 当前激活 tab 对应的面板实例 */
const currentPanel = () => {
  switch (activeTab.value) {
    case 'rel': return relPanelRef.value
    case 'vector': return vectorPanelRef.value
    case 'cache': return cachePanelRef.value
    case 'graph': return graphPanelRef.value
  }
}

/** 刷新当前 tab(顶栏刷新按钮/关键字搜索/首屏加载共用), 成功后记录已加载 */
const fetchActive = async () => {
  const ok = await currentPanel()?.refresh()
  if (ok) loadedTabs.add(activeTab.value)
}

/** 切换 tab: 首次进入懒加载, 回到关系库时重绘图表适配宽度 */
const handleTabChange = () => {
  if (!loadedTabs.has(activeTab.value)) {
    fetchActive()
  }
  nextTick(() => relPanelRef.value?.resize())
}

onMounted(fetchActive)
</script>
