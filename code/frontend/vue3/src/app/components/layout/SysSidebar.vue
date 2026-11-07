<template>
  <!-- 桌面端: 吸顶侧边栏(随页面滚动钉在导航下方, 超高时内部滚动) -->
  <el-aside
    v-if="isMd"
    :width="isCollapse ? '56px' : '208px'"
    class="sidebar-note bg-note-soft"
    :class="{ 'is-collapsed': isCollapse, 'is-collapsing': isCollapse && !menuCollapsed }"
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
      <!-- 折叠按钮(点击切换 抽屉式收窄/展开)
           按钮用绝对定位 + transform 过渡: 展开贴右、收起居中, 与菜单胶囊左缘对齐,
           不用 justify-center/justify-end 切换(避免瞬间跳位) -->
      <div class="sidebar-collapse relative shrink-0">
        <el-tooltip :content="isCollapse ? '展开菜单' : '收起菜单'" placement="right">
          <el-button
            class="sidebar-collapse-btn"
            circle
            size="small"
            text
            bg-note-tint
            :aria-label="isCollapse ? '展开菜单' : '收起菜单'"
            @click="setCollapse(!isCollapse)"
          >
            <el-icon :size="15" class="collapse-icon" :class="{ 'is-collapsed': isCollapse }">
              <Fold />
            </el-icon>
          </el-button>
        </el-tooltip>
      </div>

      <!-- 模块菜单(超出视口高度时内部滚动; min-h-0 允许 flex 子项收缩, 否则菜单撑开后无法滚动) -->
      <el-scrollbar flex-1 min-h-0>
        <el-menu
          :default-active="routerStore.routerPath.now"
          :router="true"
          :collapse="menuCollapsed"
          border-0
          bg-transparent
          class="sidebar-menu"
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

      <!-- 底部品牌小注(紧凑单行; 收起时淡出而非瞬间消失, 避免底部跳一下) -->
      <div
        class="sidebar-brand note-edge-t text-[11px]"
        :class="{ 'is-hidden': isCollapse }"
        px-3
        py-2
        text-note-sub
        shrink-0
      >
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
import { onBeforeUnmount, ref, watch } from 'vue'
import { Fold } from '@element-plus/icons-vue'
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

/** 收起动画时长: 略大于侧栏宽度过渡(280ms)与子菜单收起过渡(300ms) */
const COLLAPSE_MS = 320
// 菜单 collapse 状态滞后于宽度动画:
// 收起时先收掉展开的子菜单并让侧栏宽度收窄, 动画结束再切到图标模式;
// 展开时立即切回完整模式, 文字随宽度增长逐渐露出 —— 图标位置全程不变, 不跳变
const menuCollapsed = ref(isCollapse.value)
let collapseTimer: ReturnType<typeof setTimeout> | null = null

/** 切换折叠(统一入口, 避免模板里直接改状态导致菜单提前切换) */
function setCollapse(next: boolean) {
  // 收起前先关掉已展开的子菜单: 子项高度与宽度同时收拢,
  // 避免侧栏变窄时子项文字被裁成碎片, 也避免收完后整列图标突然上移
  if (next) {
    document
      .querySelectorAll<HTMLElement>('.sidebar-note .el-sub-menu.is-opened > .el-sub-menu__title')
      .forEach((title) => title.click())
  }
  isCollapse.value = next
}

watch(isCollapse, (collapsed) => {
  if (collapseTimer) {
    clearTimeout(collapseTimer)
    collapseTimer = null
  }
  if (collapsed) {
    collapseTimer = setTimeout(() => {
      menuCollapsed.value = true
      collapseTimer = null
    }, COLLAPSE_MS)
  } else {
    menuCollapsed.value = false
  }
})

// 跨断点(旋转/拉伸窗口)时重置为该档默认值
watch(
  () => isLg.value,
  (v) => {
    isCollapse.value = !v
  }
)

onBeforeUnmount(() => {
  if (collapseTimer) clearTimeout(collapseTimer)
})

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
  /* 收起/展开: 只动宽度, 用统一缓动; 内容裁切而非重排 */
  transition: width 0.28s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
  will-change: width;
  /* 菜单层级缩进统一: 一级 10px; 子级文字与父级标题同一左缘(6 + 10 + 24 + 5 ≈ 45px) */
  --el-menu-base-level-padding: 10px;
  --el-menu-level-padding: 29px;
}

/* 暗色下侧栏加一层纵向微光, 与页面底拉开层次(避免整块死黑) */
html.dark .sidebar-note {
  background-image: linear-gradient(180deg, rgba(255, 255, 255, 0.028), transparent 46%);
}

/* 折叠按钮行: 固定高度, 内部按钮用 transform 平滑换位 */
.sidebar-collapse {
  height: 44px;
}

.sidebar-collapse-btn {
  position: absolute;
  top: 6px;
  left: 6px;
  width: 32px;
  height: 32px;
  padding: 0;
  border-radius: 8px;
  transform: translateX(164px);
  transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1), background-color 0.18s ease;
}

.sidebar-note.is-collapsed .sidebar-collapse-btn {
  transform: translateX(6px);
}

/* 收起/展开图标只做旋转, 不切换成另一个图标(消除图标替换闪烁) */
.collapse-icon {
  transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1);
}

.collapse-icon.is-collapsed {
  transform: rotate(180deg);
}

/* 收起时菜单宽度跟随侧栏(EP 默认写死 64px, 会比 56px 侧栏多出 8px 造成偏移) */
.sidebar-note :deep(.el-menu--collapse) {
  width: 100%;
}

/* 菜单项: 紧凑高度 + 统一圆角, SaaS 后台密度
   左右各留 6px 外边距: 激活胶囊与折叠按钮同一左缘, 视觉更整齐 */
.sidebar-note :deep(.el-menu-item),
.sidebar-note :deep(.el-sub-menu__title) {
  height: 36px;
  line-height: 36px;
  margin: 1px 6px;
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
  background-color: var(--note-menu-hover);
}

/* 选中: 淡品牌底 + 左侧 3px 指示条, 一眼定位当前页 */
.sidebar-note :deep(.el-menu-item.is-active) {
  background-color: var(--note-menu-active);
  color: var(--note-accent);
  font-weight: 500;
  box-shadow: inset 3px 0 0 var(--note-green);
}

/* 收缩态: 去掉水平内边距并居中图标。
   与展开态保持同一图标中心(6 + 10 + 12 = 6 + 22 = 28px), 折叠过程零位移 */
.sidebar-note :deep(.el-menu--collapse .el-menu-item),
.sidebar-note :deep(.el-menu--collapse .el-sub-menu__title) {
  padding-inline: 0;
  justify-content: center;
}

.sidebar-note :deep(.el-menu--collapse .el-menu-item.is-active),
.sidebar-note :deep(.el-menu--collapse .el-sub-menu.is-active > .el-sub-menu__title) {
  background-color: var(--note-menu-active);
  box-shadow: inset 2px 0 0 var(--note-green);
}

/* 收起过程中: 菜单文字/箭头快速淡出, 只留图标随宽度收拢,
   避免文字被侧栏边缘裁成一条条碎片 */
.sidebar-note.is-collapsing :deep(.el-menu-item > span),
.sidebar-note.is-collapsing :deep(.el-sub-menu__title > span),
.sidebar-note.is-collapsing :deep(.el-sub-menu__icon-arrow) {
  opacity: 0;
  transition: opacity 0.12s ease-out;
}

.sidebar-note.is-collapsing :deep(.el-menu--inline) {
  opacity: 0;
  transition: opacity 0.12s ease-out;
  pointer-events: none;
}

/* 底部品牌注: 收起时淡出, 不与宽度动画抢视觉 */
.sidebar-brand {
  white-space: nowrap;
  overflow: hidden;
  transition: opacity 0.16s ease, transform 0.24s ease;
}

.sidebar-brand.is-hidden {
  opacity: 0;
  transform: translateX(-6px);
  pointer-events: none;
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
