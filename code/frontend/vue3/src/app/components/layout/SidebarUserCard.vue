<script setup lang="ts">
// 侧边栏底部用户卡: 企业控制台式"触发卡 + 管理面板下拉"
// - 触发卡: 头像(在线状态点) + 姓名 + 副标题(邮箱→用户名兜底), 悬停抬底/展开品牌描边
// - 下拉面板: 用户信息卡(角色标签/认证标识) + 账户设置/版本信息/后台管理(权限) + 退出登录(危险色独立行)
// - 收起态(prop collapsed): 仅保留居中头像
// 桌面常驻侧栏与移动抽屉共用; 退出逻辑与顶栏 UserControl 保持一致(先吊销令牌再清本地态)
import { computed, markRaw, ref } from 'vue'
import { ArrowDown, ArrowRight, CircleCheck, Document, Monitor, Setting, SwitchButton } from '@element-plus/icons-vue'
import { useAuthStore } from '@/common/stores/auth'
import { logoutUser } from '@/modules/authorization/api/auth'
import { useVisibleMenu } from '@/app/composables/useMenu'

interface Props {
  /** 侧栏收起态: 仅显示居中头像, 悬浮提示姓名 */
  collapsed?: boolean
  /** 下拉弹出方向: 桌面侧栏向上弹, 移动抽屉向下弹 */
  placement?: 'top-start' | 'bottom-start'
}

const props = withDefaults(defineProps<Props>(), {
  collapsed: false,
  placement: 'top-start',
})

const router = useRouter()
const authStore = useAuthStore()
const authState = authStore.authState
const initAuthState = authStore.initAuthState
// 后台入口权限门禁: 与顶栏 UserControl 同规则(至少持有一个声明权限的后台分组)
const { visibleMenuItems } = useVisibleMenu()
const canEnterAdmin = computed(() => visibleMenuItems.value.some(g => Boolean(g.perm)))

// 展示信息: 昵称→用户名; 副标题邮箱→用户名兜底(空行会让用户框塌缩)
const userDisplayName = computed(() => authState.user.nickname || authState.user.username || '?')
const userSubtitle = computed(() => authState.user.email || authState.user.username || '')
// 头像兜底: 取昵称/用户名前两字, 避免空头像与企业管理语境冲突
const userInitials = computed(() => userDisplayName.value.trim().slice(0, 2).toUpperCase())
// 角色标签: 有后台权限显示"管理", 否则"成员"(与菜单可见性同源, 不额外请求)
const roleTag = computed(() => (canEnterAdmin.value ? '管理' : '成员'))

interface MenuItem {
  command: string
  label: string
  icon: unknown
  action?: () => void
}

const menuItems = computed<MenuItem[]>(() => [
  ...(canEnterAdmin.value
    ? [{
        command: 'admin',
        label: '后台管理',
        icon: markRaw(Monitor),
        action: () => router.push('/admin'),
      }]
    : []),
  {
    command: 'version',
    label: '版本信息',
    icon: markRaw(Document),
    action: () => router.push('/version'),
  },
  {
    command: 'settings',
    label: '账户设置',
    icon: markRaw(Setting),
    action: () => router.push('/setting'),
  },
])

/** 退出登录: 先通知后端吊销令牌(失败不阻断本地清理), 再回首页 */
const handleLogout = async () => {
  try {
    await logoutUser({
      token_access: authState.tokens.access.token,
      token_refresh: authState.tokens.refresh.token,
      token_refresh_id: authState.tokens.refresh.token_id ?? '',
    })
  } catch (error) {
    console.error('后端登出失败:', error)
  }
  initAuthState()
  router.push('/')
}

const menuOpen = ref(false)
const handleCommand = (command: string) => {
  if (command === 'logout') {
    handleLogout()
    return
  }
  menuItems.value.find(i => i.command === command)?.action?.()
}
</script>

<template>
  <el-dropdown
    class="sys-user-dropdown w-full"
    trigger="click"
    :placement="placement"
    popper-class="sys-user-popper"
    @command="handleCommand"
    @visible-change="menuOpen = $event"
  >
    <!-- 触发卡: 收起态仅头像(悬浮提示姓名), 展开态头像+信息+箭头 -->
    <div :class="['sys-user', { 'is-collapsed': collapsed, 'is-open': menuOpen }]">
      <div class="sys-user-avatar">
        <img v-if="authState.user.avatar" :src="authState.user.avatar" alt="用户头像" class="sys-user-avatar-image">
        <span v-else class="sys-user-avatar-initials">{{ userInitials }}</span>
        <span class="sys-user-presence" title="在线" />
      </div>
      <div class="sys-user-meta">
        <div class="sys-user-name" :title="userDisplayName">{{ userDisplayName }}</div>
        <div class="sys-user-sub" :title="userSubtitle">{{ userSubtitle }}</div>
      </div>
      <ArrowDown :class="['sys-user-arrow', { 'is-open': menuOpen }]" />
    </div>
    <template #dropdown>
      <el-dropdown-menu class="sys-user-panel">
        <!-- 用户信息卡: 头像 + 姓名/角色标签 + 副标题 + 认证标识 -->
        <div class="sys-user-profile">
          <div class="sys-user-avatar sys-user-avatar-sm">
            <img v-if="authState.user.avatar" :src="authState.user.avatar" alt="" class="sys-user-avatar-image">
            <span v-else class="sys-user-avatar-initials">{{ userInitials }}</span>
            <span class="sys-user-presence" title="在线" />
          </div>
          <div class="sys-user-profile-meta">
            <div class="sys-user-profile-name">
              <span class="sys-user-profile-name-text" :title="userDisplayName">{{ userDisplayName }}</span>
              <span class="sys-user-role-tag">{{ roleTag }}</span>
            </div>
            <div class="sys-user-profile-sub" :title="userSubtitle">{{ userSubtitle }}</div>
          </div>
          <el-icon class="sys-user-verified" title="已通过安全认证">
            <CircleCheck />
          </el-icon>
        </div>

        <!-- 常规菜单: 图标 + 文案 + 尾部箭头 -->
        <el-dropdown-item
          v-for="item in menuItems" :key="item.command" :command="item.command"
          class="sys-user-menu-item"
        >
          <span class="sys-user-menu-icon"><el-icon><component :is="item.icon" /></el-icon></span>
          <span class="sys-user-menu-label">{{ item.label }}</span>
          <el-icon class="sys-user-menu-trailing"><ArrowRight /></el-icon>
        </el-dropdown-item>

        <div class="sys-user-divider" />

        <!-- 退出登录: 危险色独立成行 -->
        <el-dropdown-item command="logout" class="sys-user-menu-item is-danger">
          <span class="sys-user-menu-icon"><el-icon><SwitchButton /></el-icon></span>
          <span class="sys-user-menu-label">退出登录</span>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<style scoped>
/* 触发卡: 软底描边圆角条, 悬停抬底; 信息区在收起态宽度收拢淡出(不瞬移) */
.sys-user {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  padding: 8px;
  border-radius: 10px;
  background: var(--note-menu-hover);
  box-shadow: inset 0 0 0 1px var(--note-edge-soft);
  cursor: pointer;
  transition:
    background-color 0.18s ease,
    box-shadow 0.18s ease;
}

.sys-user:hover {
  background: rgb(var(--note-green-rgb) / 8%);
}

.sys-user.is-open {
  background: var(--note-menu-active);
  box-shadow: inset 0 0 0 1px rgb(var(--note-green-rgb) / 38%);
}

/* 收起态: 仅居中头像, 文字/箭头隐藏 */
.sys-user.is-collapsed {
  justify-content: center;
  gap: 0;
  padding: 6px 0;
}

.sys-user.is-collapsed .sys-user-meta,
.sys-user.is-collapsed .sys-user-arrow {
  display: none;
}

/* 头像: 品牌绿底白字兜底 + 右下角在线状态点 */
.sys-user-avatar {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  overflow: visible;
  flex-shrink: 0;
  background: var(--note-green);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}

.sys-user-avatar-image {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
  border-radius: 50%;
}

.sys-user-avatar-initials {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  line-height: 1;
  user-select: none;
}

.sys-user-presence {
  position: absolute;
  right: -1px;
  bottom: -1px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--el-color-success);
  box-shadow: 0 0 0 2px var(--note-menu-hover);
  pointer-events: none;
}

.sys-user-meta {
  flex: 1;
  min-width: 0;
}

.sys-user-name,
.sys-user-sub {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sys-user-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--note-deep, var(--el-text-color-primary));
  line-height: 1.4;
}

.sys-user-sub {
  margin-top: 1px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}

.sys-user-arrow {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  transition: transform 0.18s ease, color 0.18s ease;
}

.sys-user-arrow.is-open {
  transform: rotate(180deg);
  color: var(--note-accent);
}

/* 信息卡(下拉面板顶部) */
.sys-user-profile {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 8px;
  padding: 12px 10px;
  border-radius: 12px;
  background: var(--note-menu-hover);
  box-shadow: inset 0 0 0 1px var(--note-edge-soft);
}

.sys-user-avatar-sm {
  width: 36px;
  height: 36px;
  font-size: 13px;
}

.sys-user-profile-meta {
  flex: 1;
  min-width: 0;
}

.sys-user-profile-name {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.sys-user-profile-name-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 600;
  color: var(--note-deep, var(--el-text-color-primary));
}

.sys-user-role-tag {
  flex-shrink: 0;
  padding: 0 6px;
  border-radius: 4px;
  background: rgb(var(--note-green-rgb) / 12%);
  font-size: 10px;
  font-weight: 500;
  line-height: 16px;
  color: var(--note-accent);
}

.sys-user-profile-sub {
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.sys-user-verified {
  flex-shrink: 0;
  margin-top: 2px;
  font-size: 16px;
  color: var(--el-color-success);
}

.sys-user-divider {
  height: 1px;
  margin: 6px 4px;
  background: var(--note-edge-soft);
}
</style>

<style>
/* 下拉面板: teleport 到 body, 需全局样式(毛玻璃浮层 + 菜单行: 图标+文案+尾部箭头) */
.el-dropdown__popper.sys-user-popper {
  max-width: calc(100vw - 24px);
  padding: 0 !important;
  border: 1px solid var(--note-edge-soft) !important;
  border-radius: 14px !important;
  background: rgb(255 255 255 / 96%) !important;
  backdrop-filter: blur(12px);
  box-shadow: 0 12px 32px rgb(23 41 33 / 14%) !important;
  overflow: hidden;
}

html.dark .el-dropdown__popper.sys-user-popper {
  background: rgb(20 28 25 / 96%) !important;
}

.el-dropdown__popper.sys-user-popper .el-popper__arrow {
  display: none;
}

.sys-user-panel {
  width: min(232px, calc(100vw - 40px));
  padding: 8px;
  border: 0;
  background: transparent;
}

.sys-user-panel .el-dropdown-menu__item.sys-user-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  line-height: 1.5;
  color: var(--el-text-color-regular);
  white-space: normal;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.sys-user-panel .el-dropdown-menu__item.sys-user-menu-item:hover,
.sys-user-panel .el-dropdown-menu__item.sys-user-menu-item:focus {
  background: var(--note-menu-hover) !important;
  color: var(--el-text-color-primary) !important;
}

.sys-user-menu-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 18px;
  font-size: 15px;
  color: var(--el-text-color-secondary);
  transition: color 0.15s ease;
}

.sys-user-menu-item:hover .sys-user-menu-icon {
  color: var(--note-accent);
}

.sys-user-menu-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sys-user-menu-trailing {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  transition: color 0.15s ease;
}

.sys-user-menu-item:hover .sys-user-menu-trailing {
  color: var(--el-text-color-secondary);
}

/* 退出登录: 危险色独立成行, 悬停淡红底 */
.sys-user-panel .el-dropdown-menu__item.sys-user-menu-item.is-danger,
.sys-user-menu-item.is-danger .sys-user-menu-icon {
  color: var(--el-color-danger);
}

.sys-user-panel .el-dropdown-menu__item.sys-user-menu-item.is-danger:hover,
.sys-user-panel .el-dropdown-menu__item.sys-user-menu-item.is-danger:focus {
  background: rgba(245, 108, 108, 0.08) !important;
  color: var(--el-color-danger) !important;
}

.sys-user-menu-item.is-danger:hover .sys-user-menu-icon {
  color: var(--el-color-danger);
}
</style>
