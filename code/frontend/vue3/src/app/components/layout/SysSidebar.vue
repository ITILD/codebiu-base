<template>
  <!-- 桌面端: 吸顶侧边栏(随页面滚动钉在导航下方, 超高时内部滚动) -->
  <el-aside
    v-if="isMd"
    :width="isCollapse ? '56px' : '208px'"
    class="sidebar-note bg-note-soft transition-[width] duration-300"
    self-start
    sticky
    top-16
    z-10
    shrink-0
  >
    <!-- 注意: 必须用确定高度 h-app 而非 max-h-app —— 仅 max-height 的容器高度
         对百分比解析是 indefinite, el-scrollbar 内部 wrap 的 height:100% 会
         解析失败被内容撑开, 导致内部滚动条永远不出现 -->
    <div flex flex-col h-app>
      <!-- 折叠按钮(点击切换 抽屉式收窄/展开) -->
      <div flex p-1.5 shrink-0 :class="isCollapse ? 'justify-center' : 'justify-end'">
        <el-tooltip :content="isCollapse ? '展开菜单' : '收起菜单'" placement="right">
          <el-button
            :icon="isCollapse ? Expand : Fold"
            circle
            size="small"
            text
            bg-note-tint
            @click="isCollapse = !isCollapse"
          />
        </el-tooltip>
      </div>

      <!-- 模块菜单(超出视口高度时内部滚动; min-h-0 允许 flex 子项收缩, 否则菜单撑开后无法滚动) -->
      <el-scrollbar flex-1 min-h-0>
        <el-menu
          :default-active="routerStore.routerPath.now"
          :router="true"
          :collapse="isCollapse"
          border-0
          bg-transparent
          :class="isCollapse ? 'px-0' : 'px-2'"
        >
          <template v-for="item in visibleMenuItems" :key="item.index">
            <el-menu-item v-if="!item.children" :index="item.index" :title="item.title">
              <el-icon><component :is="item.icon" /></el-icon>
              <template #title>
                <span class="menu-label">
                  <span class="menu-label-text">{{ item.title }}</span>
                  <span v-if="item.system" class="menu-sys">系统</span>
                </span>
              </template>
            </el-menu-item>

            <el-sub-menu v-else :index="item.index" :title="item.title">
              <template #title>
                <el-icon><component :is="item.icon" /></el-icon>
                <span class="menu-label">
                  <span class="menu-label-text">{{ item.title }}</span>
                  <span v-if="item.system" class="menu-sys">系统</span>
                </span>
              </template>
              <el-menu-item
                v-for="child in item.children"
                :key="child.index"
                :index="child.index"
                :title="child.title"
              >
                <template #title>
                  <span class="menu-label">
                    <span class="menu-label-text">{{ child.title }}</span>
                    <span v-if="child.system" class="menu-sys">系统</span>
                  </span>
                </template>
              </el-menu-item>
            </el-sub-menu>
          </template>
        </el-menu>
      </el-scrollbar>

      <!-- 底部品牌小注(紧凑单行, 不额外占位) -->
      <div v-if="!isCollapse" class="note-edge-t text-[11px]" px-3 py-2 text-note-sub shrink-0>
        记录每一份数据
      </div>
    </div>
  </el-aside>

  <!-- 移动端: 抽屉式侧边栏(宽度随屏宽收缩, 窄屏不顶满; 底部留出刘海屏安全区) -->
  <el-drawer
    v-model="sysSettingStore.sysStyle.isSidebarDrawerOpen"
    :title="TITLE"
    direction="ltr"
    size="min(86vw, 280px)"
    class="sidebar-drawer-note"
  >
    <el-menu
      :default-active="routerStore.routerPath.now"
      :router="true"
      border-0
      bg-transparent
      @select="sysSettingStore.sysStyle.isSidebarDrawerOpen = false"
    >
      <template v-for="item in visibleMenuItems" :key="item.index">
        <el-menu-item v-if="!item.children" :index="item.index" :title="item.title">
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>
            <span class="menu-label">
              <span class="menu-label-text">{{ item.title }}</span>
              <span v-if="item.system" class="menu-sys">系统</span>
            </span>
          </template>
        </el-menu-item>

        <el-sub-menu v-else :index="item.index" :title="item.title">
          <template #title>
            <el-icon><component :is="item.icon" /></el-icon>
            <span class="menu-label">
              <span class="menu-label-text">{{ item.title }}</span>
              <span v-if="item.system" class="menu-sys">系统</span>
            </span>
          </template>
          <el-menu-item v-for="child in item.children" :key="child.index" :index="child.index" :title="child.title">
            <template #title>
              <span class="menu-label">
                <span class="menu-label-text">{{ child.title }}</span>
                <span v-if="child.system" class="menu-sys">系统</span>
              </span>
            </template>
          </el-menu-item>
        </el-sub-menu>
      </template>
    </el-menu>
  </el-drawer>
</template>

<script lang="ts" setup>
import { ref, watch } from 'vue'
import { Expand, Fold } from '@element-plus/icons-vue'
import { RouterStore } from '@/common/stores/router'
import { SysSettingStore } from '@/common/stores/sys'
import { useResponsive } from '@/common/composables/useResponsive'
import { useVisibleMenu } from '@/app/composables/useMenu'

const routerStore = RouterStore()
const sysSettingStore = SysSettingStore()
// 响应式断点: 常驻侧边栏仅平板及以上显示, 折叠态跟随桌面档
const { isMd, isLg } = useResponsive()
const TITLE = import.meta.env.VITE_GLOB_APP_TITLE
// 菜单数据与权限过滤统一来自应用外壳层(app/config/menu.ts + app/composables/useMenu)
const { visibleMenuItems } = useVisibleMenu()

// 三档响应式折叠: 手机(<768)抽屉 / 平板(768-1023)默认折叠图标栏 / 桌面(>=1024)默认展开
const isCollapse = ref(!isLg.value)
// 跨断点(旋转/拉伸窗口)时重置为该档默认值
watch(
  () => isLg.value,
  (v) => {
    isCollapse.value = !v
  }
)

// 升到平板及以上时关闭移动抽屉(已由常驻侧边栏接管)
watch(
  () => isMd.value,
  (md) => {
    if (md) sysSettingStore.sysStyle.isSidebarDrawerOpen = false
  }
)
</script>
<style scoped>
/* 侧边栏: 冷灰纸底 + 极淡接缝, 与主区仅靠一档色差分隔 */
.sidebar-note {
  box-shadow:
    inset -1px 0 0 var(--note-edge-soft);
}

/* 菜单项: 紧凑高度 + 统一圆角, SaaS 后台密度 */
.sidebar-note :deep(.el-menu-item),
.sidebar-note :deep(.el-sub-menu__title) {
  height: 36px;
  line-height: 36px;
  margin: 1px 0;
  font-size: 13px;
  border-radius: 6px;
  transition: background-color 0.18s ease, color 0.18s ease;
}

/* 长菜单名(多语言切换后可能超宽): 单行省略, 全文由 title 属性提示 */
.sidebar-note :deep(.el-menu-item > span),
.sidebar-note :deep(.el-sub-menu__title > span),
.sidebar-drawer-note :deep(.el-menu-item > span),
.sidebar-drawer-note :deep(.el-sub-menu__title > span) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 菜单标题行: 标题自适应省略 + 系统标记靠右, 不挤压分组箭头 */
.menu-label {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  min-width: 0;
}

.menu-label-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 系统级配置标记: 朱砂小标(花蕊/印章色系), 与业务菜单一眼区分 */
.menu-sys {
  flex-shrink: 0;
  padding: 0 4px;
  border-radius: 4px;
  font-size: 10px;
  line-height: 16px;
  font-weight: 400;
  letter-spacing: 0.02em;
  color: rgb(var(--note-seal-rgb));
  background: rgb(var(--note-seal-rgb) / 10%);
  box-shadow: inset 0 0 0 1px rgb(var(--note-seal-rgb) / 24%);
}

/* 悬停: 极淡品牌底 */
.sidebar-note :deep(.el-menu-item:hover),
.sidebar-note :deep(.el-sub-menu__title:hover) {
  background-color: rgb(var(--note-green-rgb) / 8%);
}

/* 选中: 淡品牌底 + 左侧 3px 指示条, 一眼定位当前页 */
.sidebar-note :deep(.el-menu-item.is-active) {
  background-color: rgb(var(--note-green-rgb) / 11%);
  color: var(--note-accent);
  font-weight: 500;
  box-shadow: inset 3px 0 0 var(--note-green);
}

/* 收缩态: 去掉水平内边距并居中图标, 修复折叠后图标偏移不齐 */
.sidebar-note :deep(.el-menu--collapse .el-menu-item),
.sidebar-note :deep(.el-menu--collapse .el-sub-menu__title) {
  padding-inline: 0;
  justify-content: center;
}

.sidebar-note :deep(.el-menu--collapse .el-menu-item.is-active) {
  box-shadow: inset 2px 0 0 var(--note-green);
}

/* 移动抽屉: 触控目标放大到 44px, 并预留刘海屏底部安全区(--note-safe-b) */
.sidebar-drawer-note :deep(.el-drawer__body) {
  padding: 8px 10px calc(12px + var(--note-safe-b));
}

.sidebar-drawer-note :deep(.el-menu-item),
.sidebar-drawer-note :deep(.el-sub-menu__title) {
  height: 44px;
  line-height: 44px;
  margin: 1px 0;
  border-radius: 8px;
  font-size: 14px;
}

.sidebar-drawer-note :deep(.el-menu-item.is-active) {
  background-color: rgb(var(--note-green-rgb) / 11%);
  color: var(--note-accent);
  font-weight: 500;
}
</style>
