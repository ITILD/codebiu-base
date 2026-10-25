<template>
  <!-- 中式水墨主题展示页: 不复用通用 ThemeShowcase, 按国画手卷构图重新排布组件 -->
  <div
    :style="{ ...theme.vars, fontFamily: 'var(--el-font-family)' }"
    :class="theme.rootClass"
    class="ink-page relative isolate overflow-hidden rounded-[2px]"
  >
    <!-- 氛围墨晕: 焦墨自左上洇开, 右下一道淡墨收气 -->
    <div v-if="theme.atmosphere" class="pointer-events-none absolute inset-0 -z-10" :style="theme.atmosphere" />
    <!-- 宣纸纤维: 极细横纹 multiply 印进纸底, 只为"摸到纸", 不压淡墨 -->
    <div class="ink-paper pointer-events-none absolute inset-0 -z-10" aria-hidden="true" />

    <!-- 引首: 与首页同源的水墨小池(荷叶/荷花/涟漪), 让整页先是一张画 -->
    <section class="relative">
      <div class="pointer-events-none absolute left-4 top-3 z-10 flex flex-col items-center gap-1.5 md:left-7 md:top-4">
        <span class="font-hand text-[13px] tracking-[0.35em] text-[#47504a] [writing-mode:vertical-rl]">墨戏</span>
        <span class="note-seal !h-[18px] !w-[18px] !text-[10px]" aria-hidden="true">墨</span>
      </div>
      <GardenPond class="!mx-0" />
      <p class="relative -mt-1 px-6 text-center font-hand text-xs leading-6 text-[#6d756e] md:text-sm">
        以留白为纸，以墨色为骨 —— 下面这些控件，都安放在一方宣纸上。
      </p>
    </section>

    <!-- 枯笔飞白: 国画手卷的段与段之间用笔触分开, 不用实线 -->
    <div class="ink-divider mx-4 mt-3 md:mx-6" aria-hidden="true" />

    <!-- 题头 -->
    <header class="relative px-4 pt-3 md:px-6">
      <div class="ink-wash absolute -inset-x-2 -top-2 -bottom-2" pointer-events-none aria-hidden="true" />
      <div class="relative flex flex-wrap items-end justify-between gap-3">
        <div class="min-w-0">
          <h2 class="font-hand text-2xl font-bold leading-tight tracking-[0.12em] text-[#2b332e] md:text-3xl">
            {{ theme.name }}
          </h2>
          <p class="mt-1.5 max-w-3xl text-sm leading-6 text-[#47504a]">{{ theme.desc }}</p>
        </div>
        <span class="shrink-0 rounded-[2px] border border-[#c9c1ae] px-2 py-1 font-hand text-xs tracking-[0.25em] text-[#6d756e]">
          组件选型 · 卷之四
        </span>
      </div>
      <div class="ink-rule mt-3" aria-hidden="true" />
    </header>

    <div class="space-y-5 px-4 pb-5 pt-5 md:px-6">
      <!-- 壹 · 按钮 -->
      <section class="ink-section">
        <SectionHead no="壹" title="墨印 · 按钮" note="浓墨为底，朱砂点眼" />
        <div class="ink-section__body flex flex-wrap items-center gap-3">
          <el-button type="primary">主要按钮</el-button>
          <el-button>默认按钮</el-button>
          <el-button type="success">成功</el-button>
          <el-button type="warning">警告</el-button>
          <el-button type="danger">危险</el-button>
          <el-button type="info">信息</el-button>
          <el-button type="primary" plain>朴素</el-button>
          <el-button round>圆角</el-button>
          <el-button disabled>禁用</el-button>
        </div>
      </section>

      <!-- 貳 · 标签 -->
      <section class="ink-section">
        <SectionHead no="貳" title="印泥 · 标签" note="小印钤于纸角" />
        <div class="ink-section__body flex flex-wrap items-center gap-3">
          <el-tag>默认</el-tag>
          <el-tag type="success">成功</el-tag>
          <el-tag type="warning">警告</el-tag>
          <el-tag type="danger">朱砂</el-tag>
          <el-tag type="info">信息</el-tag>
          <el-tag type="primary" effect="dark">实底</el-tag>
          <el-tag type="primary" effect="plain">朴素</el-tag>
          <el-tag round>圆角</el-tag>
        </div>
      </section>

      <!-- 叁 · 表单 -->
      <section class="ink-section">
        <SectionHead no="叁" title="笔锋 · 表单" note="以一线代框，如纸上走笔" />
        <div class="ink-section__body grid gap-4 md:grid-cols-2">
          <el-input v-model="input" placeholder="写下点什么…" clearable />
          <el-select v-model="select" placeholder="择其一">
            <el-option v-for="s in options" :key="s" :label="s" :value="s" />
          </el-select>
          <div class="flex items-center gap-3">
            <span class="font-hand text-sm text-[#47504a]">开关</span>
            <el-switch v-model="on" />
            <span class="font-hand text-sm text-[#47504a]">评分</span>
            <el-rate v-model="rate" />
          </div>
          <div class="flex items-center gap-3">
            <span class="shrink-0 font-hand text-sm text-[#47504a]">浓淡 {{ slider }}</span>
            <el-slider v-model="slider" class="flex-1" />
          </div>
        </div>
      </section>

      <!-- 肆 · 提示 -->
      <section class="ink-section">
        <SectionHead no="肆" title="云气 · 提示" note="淡墨一层，不夺主体" />
        <div class="ink-section__body flex flex-col gap-2">
          <el-alert title="信息提示" type="info" show-icon :closable="false" />
          <el-alert title="成功提示" type="success" show-icon :closable="false" />
          <el-alert title="警告提示" type="warning" show-icon :closable="false" />
          <el-alert title="错误提示" type="error" show-icon :closable="false" />
        </div>
      </section>

      <!-- 伍 · 描述列表 -->
      <section class="ink-section">
        <SectionHead no="伍" title="砚台 · 描述" note="题跋分栏，一栏一事" />
        <div class="ink-section__body">
          <el-descriptions :column="3" border>
            <el-descriptions-item label="主题">{{ theme.name }}</el-descriptions-item>
            <el-descriptions-item label="主色">
              <el-tag size="small">{{ theme.colors[0] }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="用途">组件样式选型</el-descriptions-item>
          </el-descriptions>
        </div>
      </section>

      <!-- 陆 · 表格 -->
      <section class="ink-section">
        <SectionHead no="陆" title="卷轴 · 表格" note="横平竖直，仍留纸气" />
        <div class="ink-section__body">
          <el-table :data="rows" size="small">
            <el-table-column prop="name" label="组件" min-width="120" />
            <el-table-column prop="status" label="状态" min-width="90">
              <template #default="{ row }">
                <el-tag :type="row.status === '推荐' ? 'success' : 'info'" size="small">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="note" label="备注" min-width="160" />
          </el-table>
        </div>
      </section>

      <!-- 柒 · 进度与页签 -->
      <section class="ink-section">
        <SectionHead no="柒" title="水痕 · 进度" note="由浓至淡，一线到底" />
        <div class="ink-section__body">
          <el-progress :percentage="60" />
          <el-progress :percentage="100" status="success" />
          <el-tabs class="mt-2">
            <el-tab-pane label="页签一">当前主题下页签一的内容样式。</el-tab-pane>
            <el-tab-pane label="页签二">当前主题下页签二的内容样式。</el-tab-pane>
          </el-tabs>
        </div>
      </section>

      <!-- 捌 · 对话框 -->
      <section class="ink-section">
        <SectionHead no="捌" title="落款 · 对话框" note="收笔，钤印" />
        <div class="ink-section__body">
          <el-button type="primary" @click="dialog = true">打开对话框</el-button>
        </div>
      </section>
    </div>

    <!-- 卷尾题款 -->
    <div class="ink-divider mx-4 md:mx-6" aria-hidden="true" />
    <p class="px-4 pb-5 pt-3 text-center font-hand text-xs tracking-[0.3em] text-[#8a918a] md:px-6">
      —— 墨分五色 · 留白为上 ——
    </p>

    <el-dialog v-model="dialog" title="墨戏 · 对话" width="90%" class="max-w-[420px]">
      <p class="text-sm">对话框在当前主题下渲染(非 append-to-body)，纸底、墨字、朱砂钮随主题变化。</p>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="dialog = false">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
// 中式水墨主题展示: 组件安放在宣纸手卷上 —— 首页同款小池引首、枯笔分隔、朱砂闲章、
// 手写体题头; 输入类改为"一线代框"的墨线样式, 表格去掉外框只留细墨线
import type { PlaygroundTheme } from './themes'
import GardenPond from '@/common/components/decor/GardenPond.vue'
import SectionHead from './InkSectionHead.vue'

/** 当前展示的主题 */
defineProps<{ theme: PlaygroundTheme }>()

// 表单控件演示值
const input = ref('')
const select = ref('')
const options = ['选项一', '选项二', '选项三']
const on = ref(true)
const rate = ref(4)
const slider = ref(40)

// 对话框显隐
const dialog = ref(false)

// 表格静态数据
const rows = [
  { name: 'el-button', status: '推荐', note: '按钮' },
  { name: 'el-card', status: '推荐', note: '内容卡片容器' },
  { name: 'el-table', status: '可选', note: '数据表格' },
]
</script>

<style scoped>
/* 宣纸底: 显式落在样式表里而不只依赖主题字符串类名, 保证暖白纸色一定生效
   (纸色比全站淡绿纸更暖一档, 才像宣纸而不像普通卡片) */
.ink-page {
    background-color: #f5f0e3;
    color: #232a26;
    border: 1px solid #e3dcc9;
}

/* ============================================
   宣纸与水印: 区块不铺卡片底色、不画边框,
   只用两笔错位的淡墨水痕界定边界 —— 相邻两笔在间隙处交叠, 交界略深, 即"笔与笔之间的水印"
   ============================================ */
.ink-section {
    position: relative;
    isolation: isolate;
    padding: 16px 14px 18px;
    border-radius: 2px;
}

/* 淡墨水痕: 中心薄(透明干净)、洇开边缘略深(颜料在干边沉积)、再迅速回落为无 ——
   透明度整体压得很低, 叠在宣纸纤维上仍是"淡墨", 不发灰发脏 */
.ink-section::before {
    content: '';
    position: absolute;
    inset: -13px -10px;
    z-index: 0;
    border-radius: 8px;
    pointer-events: none;
    background-image:
        radial-gradient(58% 52% at 16% 16%, rgba(90, 107, 98, 0.045) 0%, rgba(90, 107, 98, 0.03) 54%, rgba(90, 107, 98, 0.082) 67%, rgba(90, 107, 98, 0.012) 72%, transparent 82%),
        radial-gradient(54% 48% at 85% 84%, rgba(90, 107, 98, 0.038) 0%, rgba(90, 107, 98, 0.026) 52%, rgba(90, 107, 98, 0.072) 67%, rgba(90, 107, 98, 0.01) 72%, transparent 81%);
}

/* 纸纤维: 极轻, 只为"摸到"纸, 不压淡墨 */
.ink-section::after {
    content: '';
    position: absolute;
    inset: 0;
    z-index: 20;
    border-radius: inherit;
    pointer-events: none;
    background-image: var(--note-grain);
    background-size: 260px 260px;
    mix-blend-mode: multiply;
    opacity: 0.08;
}

/* 整页宣纸纤维: 与区块同源, 让留白处也是一张纸而不是一块纯色 */
.ink-paper {
    background-image: var(--note-grain);
    background-size: 300px 300px;
    mix-blend-mode: multiply;
    opacity: 0.07;
}

.ink-section__body {
    position: relative;
    z-index: 1;
}

/* ============================================
   组件墨化: 淡墨为面, 焦墨点睛(只在本页生效)
   ============================================ */

/* 按钮: 方印感, 字距拉开, 去掉玻璃光泽 */
.ink-page :deep(.el-button) {
    border-radius: 2px;
    letter-spacing: 0.14em;
    box-shadow: none;
}

/* 主按钮 = 焦墨: 全页唯一的重色块, 与大片淡墨形成对比支撑 */
.ink-page :deep(.el-button--primary) {
    background-color: #2b332e;
    border-color: #2b332e;
    box-shadow:
        inset 0 0 0 1px rgba(255, 255, 255, 0.08),
        0 8px 20px -16px rgba(11, 14, 12, 0.9);
}

.ink-page :deep(.el-button--primary:hover) {
    background-color: #3a453e;
    border-color: #3a453e;
}

/* 默认按钮 = 淡墨: 半透明墨气浮在纸上, 不压纸 */
.ink-page :deep(.el-button:not([class*='el-button--']):not(.is-text):not(.is-link)) {
    background-color: rgba(90, 107, 98, 0.06);
    border-color: rgba(90, 107, 98, 0.16);
    color: #3b453d;
}

.ink-page :deep(.el-button:not([class*='el-button--']):not(.is-text):not(.is-link):hover) {
    background-color: rgba(90, 107, 98, 0.11);
    border-color: rgba(90, 107, 98, 0.26);
}

/* 输入/选择: 一线代框 —— 平时淡墨, 悬停略浓, 聚焦才落焦墨(淡浓层次) */
.ink-page :deep(.el-input__wrapper),
.ink-page :deep(.el-select__wrapper) {
    background-color: transparent;
    background-image: linear-gradient(180deg, transparent 62%, rgba(90, 107, 98, 0.045) 100%);
    border-radius: 0;
    box-shadow: none !important;
    border-bottom: 1px solid rgba(90, 107, 98, 0.22);
    padding-left: 2px;
    transition:
        border-color 0.2s ease-out,
        background-image 0.2s ease-out;
}

.ink-page :deep(.el-input__wrapper:hover),
.ink-page :deep(.el-select__wrapper:hover) {
    border-bottom-color: rgba(90, 107, 98, 0.38);
}

.ink-page :deep(.el-input__wrapper.is-focus),
.ink-page :deep(.el-select__wrapper.is-focused) {
    box-shadow: none !important;
    border-bottom-color: #232a26;
    background-image: linear-gradient(180deg, transparent 38%, rgba(90, 107, 98, 0.08) 100%);
}

/* 标签: 小印, 手写体 */
.ink-page :deep(.el-tag) {
    border-radius: 2px;
    font-family: var(--note-font-hand);
    letter-spacing: 0.12em;
}

/* 表格: 去掉外框与斑马纹, 只留细墨线; 表头一条较浓的墨线压住 */
.ink-page :deep(.el-table) {
    --el-table-border-color: rgba(90, 107, 98, 0.14);
    --el-table-header-bg-color: transparent;
    --el-table-tr-bg-color: transparent;
    --el-table-bg-color: transparent;
    --el-table-row-hover-bg-color: rgba(90, 107, 98, 0.05);
    border-radius: 0;
    box-shadow: none;
}

.ink-page :deep(.el-table th.el-table__cell) {
    background: transparent;
    border-bottom-color: rgba(35, 42, 38, 0.26);
    font-family: var(--note-font-hand);
    font-weight: 600;
    letter-spacing: 0.1em;
    color: #232a26;
}

/* 描述列表: 透明底, 标签用题跋字体 */
.ink-page :deep(.el-descriptions__body),
.ink-page :deep(.el-descriptions__cell) {
    background: transparent !important;
}

.ink-page :deep(.el-descriptions__label) {
    font-family: var(--note-font-hand);
    color: #7c847d;
}

/* 页签: 指示条为一道焦墨短线, 底轨是淡墨渐隐线 */
.ink-page :deep(.el-tabs__item),
.ink-page :deep(.el-dialog__title) {
    font-family: var(--note-font-hand);
    letter-spacing: 0.16em;
}

.ink-page :deep(.el-tabs__active-bar) {
    height: 2px;
    background-color: #232a26;
}

.ink-page :deep(.el-tabs__nav-wrap::after) {
    height: 1px;
    background: linear-gradient(
        to right,
        transparent,
        rgba(90, 107, 98, 0.18) 18%,
        rgba(90, 107, 98, 0.18) 82%,
        transparent
    );
}

/* 进度/滑块/评分: 轨道用淡墨, 填充与星点用焦墨 */
.ink-page :deep(.el-progress-bar__outer) {
    background-color: rgba(90, 107, 98, 0.08);
    border-radius: 2px;
}

.ink-page :deep(.el-progress-bar__inner) {
    border-radius: 2px;
}

.ink-page :deep(.el-slider) {
    --el-slider-runway-bg-color: rgba(90, 107, 98, 0.1);
}

.ink-page :deep(.el-rate) {
    --el-rate-fill-color: #3b453d;
    --el-rate-void-color: rgba(90, 107, 98, 0.22);
}

/* 对话框: 宣纸底 + 极淡墨边 */
.ink-page :deep(.el-dialog) {
    background-color: #fdfaf2;
    border: 1px solid rgba(90, 107, 98, 0.12);
    border-radius: 3px;
    box-shadow: 0 24px 60px -34px rgba(35, 42, 38, 0.8);
}

/* 提示条: 只收圆角, 保留语义色淡底 */
.ink-page :deep(.el-alert) {
    border-radius: 2px;
}
</style>
