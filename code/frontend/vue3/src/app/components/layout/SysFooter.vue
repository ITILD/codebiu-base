<template>
  <!-- 页脚: 淡绿软底与顶栏呼应, 位于文档末尾随内容增长 -->
  <footer
    v-if="sysStyle.headFootShow"
    class="note-edge-t bg-note-soft px-4 py-4 lg:px-8"
  >
    <!-- 关联账号 本站 备案 -->
    <div flex flex-col items-center gap-3 sm:flex-row sm:items-center sm:justify-between sm:gap-6>
      <!-- 关联账号(图标链接触达区放大到 40px 满足移动端触控, 悬浮轻浮起更醒目) -->
      <div flex items-center text-note-sub>
        <a
          v-for="link in socialLinks"
          :key="link.name"
          :href="link.url"
          p-2.5
          text-note-green
          hover:-translate-y-0.5
          transition-transform
        >
          <component :is="link.icon" h-5 w-5 aria-hidden="true" />
          <span sr-only>{{ link.name }}</span>
        </a>
      </div>
      <!-- 年份提示 + 备案(合并为一组,移动端居中堆叠,避免长文本截断) -->
      <div flex flex-col items-center gap-1 text-center sm:flex-row sm:gap-6 text-note-sub>
        <span text-xs md:text-sm>© 2023-{{ yearNow }} <a :href="siteMeta.copyrightUrl"
            class="hover:underline underline-offset-2">{{ siteMeta.copyright }}</a>. All Rights Reserved.</span>
        <span v-if="siteMeta.icp" text-xs>© 备案号: <a :href="siteMeta.icpUrl"
            target="_blank" class="hover:underline underline-offset-2">{{ siteMeta.icp }}</a></span>
      </div>
    </div>
  </footer>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import GmailSVG from '@/common/components/icons/GmailSVG.vue'
import GithubSVG from '@/common/components/icons/GithubSVG.vue'
import DribbbleSVG from '@/common/components/icons/DribbbleSVG.vue'

// 样式控制
import { SysSettingStore } from '@/common/stores/sys'
const sysSettingStore = SysSettingStore()
const sysStyle = sysSettingStore.sysStyle

const yearNow = ref(new Date().getFullYear())

// 站点静态配置(备案号/版权): 发布后直接改 dist 下的 app-config.json 即可生效, 无需重新构建
interface SiteMeta {
  icp: string
  icpUrl: string
  copyright: string
  copyrightUrl: string
}
const siteMeta = ref<SiteMeta>({
  icp: '辽ICP备2022000388号-1',
  icpUrl: 'https://beian.miit.gov.cn/',
  copyright: 'ITILD',
  copyrightUrl: 'https://wx1s.com/',
})

onMounted(async () => {
  try {
    const base = import.meta.env.BASE_URL || '/'
    // 带时间戳 + no-store, 避免改完配置后仍读到浏览器缓存
    const res = await fetch(`${base}app-config.json?t=${Date.now()}`, { cache: 'no-store' })
    if (!res.ok) return
    siteMeta.value = { ...siteMeta.value, ...(await res.json()) }
  } catch {
    // 静态配置缺失或格式错误时保留内置默认值
  }
})

const socialLinks = [
  { name: 'Gmail', url: '#', icon: GmailSVG },
  { name: 'GitHub', url: '#', icon: GithubSVG },
  { name: 'Dribbble', url: '#', icon: DribbbleSVG }
]
</script>
