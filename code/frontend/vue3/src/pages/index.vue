<template>
  <!-- select-none: 首页为展示页, 文字不允许被选中复制 -->
  <div w-full max-w-5xl mx-auto p-4 md:p-8 relative class="select-none">
    <!-- 页面级落叶: 自右上枝冠飘落, 一直落到页尾池塘水面 -->
    <FallingLeaves />

    <!-- Hero: 自然笔记大纸片(苔绿渐变+格线+纸纤维顶盖), 登录态感知;
         不裁剪溢出 —— 水墨生长枝(Canvas)自卡内右上生发并垂出卡底 -->
    <section
      class="paper-sheet z-10"
      relative
      rounded-note-lg
      border-note
      bg-note-gradient
      p-8
      md:p-14
      mb-10
    >
      <!-- 水墨生长枝: 右上入笔向左下生长, 最细枝垂出卡底 -->
      <FractalBranch />

      <!-- 纸面颗粒层(数字花园 PaperCard 噪声配方): fractalNoise 高频细颗粒, overlay 印出纸孔质感 -->
      <div class="note-age-stain" absolute inset-0 pointer-events-none rounded-note-lg overflow-hidden />

      <!-- 注意: 含方括号的任意值类名必须写进 class(attributify 陷阱: 裸属性名含 [] 会使 setAttribute 抛 InvalidCharacterError, 整页渲染失败) -->
      <div relative z-10 class="max-w-[68%] md:max-w-[64%]">
        <!-- Hero 主标题: 已登录显示时段问候, 未登录显示品牌名;
             min-w-0 + break-words: flex 匿名文本项默认不收缩, 长英文昵称(如 Administrator)
             会顶穿 68% 文字区被裁断, 放开收缩并允许断词换行 -->
        <h1
          flex items-center flex-wrap min-w-0 font-serif text-2xl sm:text-3xl md:text-5xl font-bold text-note-green
          :class="isLoggedIn ? 'mb-3' : 'mb-4'"
          class="note-etch [overflow-wrap:anywhere]"
        >
          {{ heroTitle }}
          <span class="note-seal ml-3 md:ml-4" title="小憩">憩</span>
        </h1>
        <p text-base md:text-lg text-note-sub max-w-xl leading-relaxed :class="isLoggedIn ? 'mb-6' : 'mb-2'">
          {{ $t('home_sub') }}
        </p>

        <!-- 已登录: 最近访问快捷入口(仅展示可在首页直达的业务单页) -->
        <div v-if="isLoggedIn && recentHomePages.length" mb-2>
          <p text-xs text-note-sub mb-2>{{ $t('home_recent') }}</p>
          <div flex flex-wrap gap-2>
            <RouterLink
              v-for="item in recentHomePages.slice(0, 6)"
              :key="item.path"
              :to="homeLink(item.path)"
              px-3 py-1.5 rounded-full bg-note-tint text-xs md:text-sm text-note hover:text-note-green hover:shadow-note note-transition
            >
              {{ item.title }}
            </RouterLink>
          </div>
        </div>

        <!-- 未登录: 登录引导(仅 !isLoggedIn 时显示; 已登录但无最近访问不能落到这里) -->
        <p v-if="!isLoggedIn" text-sm md:text-base text-note-sub mb-2 max-w-xl>
          {{ $t('home_login_hint') }}
        </p>
      </div>
    </section>

    <!-- 业务入口卡: 后台侧边栏中标记 home 的末级页面, 点击以单页模式进入(不渲染侧边栏) -->
    <section>
      <div flex items-center gap-2 mb-6>
        <span text-xl>🧭</span>
        <h2 font-serif text-2xl font-semibold text-note class="note-etch">{{ $t('home_apps') }}</h2>
        <hr class="note-line-fade flex-1" />
      </div>

      <div grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5>
        <RouterLink
          v-for="entry in visibleHomeEntries"
          :key="entry.index"
          :to="homeLink(entry.index)"
          class="paper-grain note-glow-hover"
          bg-note-card
          rounded-note-lg
          p-5 md:p-6
          overflow-hidden
          duration-300
          hover:-translate-y-0.5
          group
          flex
          flex-col
        >
          <div flex items-center gap-2.5 mb-4>
            <div
              w-11
              h-11
              rounded-note-lg
              bg-note-tint
              text-note-green
              flex-center
              shrink-0
            >
              <el-icon :size="22" class="note-transition group-hover:scale-110"><component :is="entry.icon" /></el-icon>
            </div>
            <span v-ellipsis text-xs text-note-sub truncate>{{ entry.groupTitle }}</span>
            <div flex-1 />
            <el-icon
              text-note-sub
              class="note-transition group-hover:text-note-green group-hover:translate-x-0.5"
            >
              <ArrowRight />
            </el-icon>
          </div>
          <h3 text-lg font-semibold text-note mb-1.5>{{ entry.title }}</h3>
          <p text-sm text-note-sub leading-relaxed m-0>{{ entry.desc }}</p>
        </RouterLink>
      </div>
    </section>

    <!-- 页尾小池: 仅保留画面, 不加题词, 方便作为各类项目的基础首页 -->
    <section relative mt-10>
      <GardenPond />
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowRight } from '@element-plus/icons-vue'
import { useAuthStore } from '@/common/stores/auth'
import { useVisibleHome } from '@/app/composables/useMenu'
import { homeEntries, homeLink } from '@/app/config/menu'
import { useRecentPages } from '@/app/composables/useRecentPages'
// 系统三语(中/英/日): 问候语等脚本侧取词
import { i18n } from '@/common/i18n/language'
// 诗意场景装饰: 分形悬枝与涟漪小池(纯 SVG, 零图片依赖) + 页面级落叶
import FractalBranch from '@/common/components/decor/FractalBranch.vue'
import FallingLeaves from '@/common/components/decor/FallingLeaves.vue'
import GardenPond from '@/common/components/decor/GardenPond.vue'

const TITLE = import.meta.env.VITE_GLOB_APP_TITLE

const authStore = useAuthStore()
const { visibleHomeEntries } = useVisibleHome()
const { recentPages } = useRecentPages()

// ===== 登录态与问候 =====
const isLoggedIn = computed(() => Boolean(authStore.authState.user.id))
const displayName = computed(() => authStore.authState.user.nickname || authStore.authState.user.username)

/** 按当前时段返回问候语 i18n key(展示时经 $t 翻译) */
function greetingByHour(): string {
  const h = new Date().getHours()
  if (h < 6) return 'g_night'
  if (h < 12) return 'g_morning'
  if (h < 14) return 'g_noon'
  if (h < 18) return 'g_afternoon'
  return 'g_evening'
}
const greeting = ref(greetingByHour())

/** Hero 主标题: 已登录为时段问候 + 昵称, 未登录为品牌名(t 随语言切换刷新) */
const heroTitle = computed(() =>
  isLoggedIn.value ? i18n.global.t('hello_fmt', { g: i18n.global.t(greeting.value), name: displayName.value }) : TITLE
)

// ===== 最近访问(仅保留首页可直达的业务单页, 其余后台页面不出现在首页) =====
const homePathSet = new Set(homeEntries.map((entry) => entry.index))
const recentHomePages = computed(() =>
  recentPages.value.filter((item) => homePathSet.has(item.path))
)
</script>

<style scoped>
/* 笔记本格线背景(横线纸): 首页 Hero 专用, 从 base.css 迁入。
   note-seal(朱砂闲章)已改用 uno.config 的全局 shortcut, pond-quote 已转 uno 原子类 */
.note-lined-paper {
  background-image: repeating-linear-gradient(
    transparent,
    transparent 27px,
    rgba(46, 124, 107, 0.1) 28px
  );
}

/* 笔记本侧边装订线(红色竖线太重, 用苔绿竖虚线): 首页专用 */
.note-margin-line {
  background-image: linear-gradient(to right, transparent 40px, rgba(46, 124, 107, 0.22) 40px, rgba(46, 124, 107, 0.22) 41px, transparent 41px);
}

/* 蚀刻标题(数字花园 Distress 配方改 CSS mask 实现):
   阈值化噪声(0 / 0.6 / 1 三档)烘进 data URI 作 mask-image, alpha 遮罩把文字"啃"出碑刻磨损 ——
   不用 SVG filter: filter 会让 Chromium 把元素栅格化, 破坏文本选区与复制;
   mask 只影响绘制不影响命中测试, 文字可正常选中复制。
   颗粒度 = baseFrequency(越大咬痕越细), 完整度 = tableValues 档值放行量(越大越完整) */
.note-etch {
  -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='240' height='240'%3E%3Cfilter id='m'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.11' numOctaves='3' stitchTiles='stitch'/%3E%3CfeComponentTransfer%3E%3CfeFuncA type='discrete' tableValues='0 0.6 1'/%3E%3C/feComponentTransfer%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23m)'/%3E%3C/svg%3E");
  mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='240' height='240'%3E%3Cfilter id='m'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.11' numOctaves='3' stitchTiles='stitch'/%3E%3CfeComponentTransfer%3E%3CfeFuncA type='discrete' tableValues='0 0.6 1'/%3E%3C/feComponentTransfer%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23m)'/%3E%3C/svg%3E");
  -webkit-mask-size: 240px 240px;
  mask-size: 240px 240px;
}

/* Hero 大纸片落影配套: 陈纸压桌的暖调深影, 替代全局绿色光晕;
   并覆盖 --note-grain: 全局配方是 0.02 0.4 的横向拉丝(横纹元凶), 首页换成纯高频细颗粒 */
.paper-sheet {
  --note-grain: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='h'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='120' height='120' filter='url(%23h)' opacity='0.5'/%3E%3C/svg%3E");
  box-shadow:
    0 0 0 1px hsla(150, 22%, 16%, 0.07),
    0 1px 2px hsla(150, 25%, 12%, 0.14),
    0 12px 32px -6px hsla(150, 25%, 12%, 0.28);
}

html.dark .paper-sheet {
  box-shadow:
    0 0 0 1px hsla(0, 0%, 0%, 0.3),
    0 12px 32px -6px rgba(0, 0, 0, 0.55);
}

/* Hero 纸面颗粒层: 高频 fractalNoise 细颗粒(纸孔), overlay 混合
   (暗处更暗亮处更亮, 噪声同时"印"进纸色底层, 是 PaperCard 的纸张配方);
   保留轻微角落黄斑(foxing)与微黄陈色 */
.note-age-stain {
  background-image:
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='g'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='120' height='120' filter='url(%23g)' opacity='0.6'/%3E%3C/svg%3E"),
    radial-gradient(ellipse 60% 45% at 88% 10%, hsla(38, 45%, 30%, 0.1), transparent 70%),
    radial-gradient(ellipse 50% 40% at 6% 95%, hsla(36, 42%, 26%, 0.09), transparent 68%),
    linear-gradient(hsla(42, 38%, 62%, 0.08), hsla(42, 38%, 62%, 0.08));
  background-size: 120px 120px, cover, cover, cover;
  mix-blend-mode: overlay;
  opacity: 0.9;
}

/* 暗色下颗粒收敛, 避免大面积死黑 */
html.dark .note-age-stain {
  opacity: 0.5;
}

/* Hero 顶盖渐晕同步加档: 蚀刻内影更明显 */
.paper-sheet::after {
  opacity: 0.85;
}

html.dark .paper-sheet::after {
  opacity: 0.68;
}
</style>
