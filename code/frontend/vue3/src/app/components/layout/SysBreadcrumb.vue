<template>
  <!-- 面包屑: 路由路径匹配菜单树 → ['首页', '分组', '当前页']
       仅后台路由渲染; md 以下隐藏(手机由抽屉菜单承担定位), 避免头部拥挤 -->
  <el-breadcrumb v-if="isAdmin && trail.length > 1" separator="/" class="hidden md:block min-w-0">
    <el-breadcrumb-item v-for="(node, i) in trail" :key="node.index + i">
      <!-- 末级为当前页(深色), 上级可点击返回 -->
      <RouterLink
        v-if="i < trail.length - 1"
        :to="node.index"
        class="text-note-sub hover:text-note-green transition-colors"
      >
        {{ node.title }}
      </RouterLink>
      <span v-else v-ellipsis class="text-note font-medium truncate inline-block max-w-[20vw] align-bottom">{{ node.title }}</span>
    </el-breadcrumb-item>
  </el-breadcrumb>
</template>

<script lang="ts" setup>
import { findMenuTrail } from '@/app/config/menu'
// 菜单轨迹: findMenuTrail 未收录的路径(如 /setting)返回空数组 → 不渲染
const route = useRoute()
// bare=1 单页模式(首页入口卡进入): 不渲染侧边栏, 也不显示后台面包屑
const isAdmin = computed(
  () => Boolean(route.meta.admin && String(route.query.bare ?? '') !== '1'),
)
const trail = computed(() => findMenuTrail(route.path))
</script>
