<template>
  <!-- 中式水墨主题展示页: 不复用通用 ThemeShowcase, 按国画手卷构图重新排布组件 -->
  <div
    :style="{ ...theme.vars, fontFamily: 'var(--el-font-family)' }"
    :class="theme.rootClass"
    class="ink-page relative isolate overflow-hidden rounded-[2px]"
  >
    <!-- 氛围墨晕: 焦墨自左上洇开, 右下一道淡墨收气 -->
    <div v-if="theme.atmosphere" class="pointer-events-none absolute inset-0 -z-10" :style="theme.atmosphere" />

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
/* ---- 宣纸区块: 无硬边线, 用极淡墨角 + 纸纤维定义形状 ---- */
.ink-section {
    position: relative;
    isolation: isolate;
    padding: 14px 14px 16px;
    border: 1px solid #e4ddcd;
    border-radius: 2px;
    background-image:
        radial-gradient(58% 48% at 0% 0%, rgba(51, 64, 58, 0.05) 0%, transparent 68%),
        linear-gradient(180deg, rgba(255, 255, 255, 0.6) 0%, rgba(255, 255, 255, 0.12) 100%);
    box-shadow: 0 10px 30px -26px rgba(43, 51, 46, 0.6);
}

/* 纸纤维顶盖: 与全站卡片同一套噪声, 但用 multiply 让墨色更沉 */
.ink-section::after {
    content: '';
    position: absolute;
    inset: 0;
    z-index: 10;
    border-radius: inherit;
    pointer-events: none;
    background-image: var(--note-grain);
    background-size: 260px 260px;
    mix-blend-mode: multiply;
    opacity: 0.22;
}

.ink-section__body {
    position: relative;
    z-index: 1;
}

/* ---- 组件墨化: 只在本页生效 ---- */

/* 按钮: 方印感, 字距拉开, 去掉玻璃光泽 */
.ink-page :deep(.el-button) {
    border-radius: 2px;
    letter-spacing: 0.14em;
    box-shadow: none;
}

.ink-page :deep(.el-button--primary) {
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.12), 0 3px 10px -8px rgba(43, 51, 46, 0.9);
}

/* 输入/选择: 以一线代框, 聚焦时墨线加深 */
.ink-page :deep(.el-input__wrapper),
.ink-page :deep(.el-select__wrapper) {
    background-color: transparent;
    border-radius: 0;
    box-shadow: none !important;
    border-bottom: 1px solid #c9c1ae;
    padding-left: 2px;
    transition: border-color 0.2s ease-out;
}

.ink-page :deep(.el-input__wrapper:hover),
.ink-page :deep(.el-select__wrapper:hover) {
    border-bottom-color: #9aa39a;
}

.ink-page :deep(.el-input__wrapper.is-focus),
.ink-page :deep(.el-select__wrapper.is-focused) {
    box-shadow: none !important;
    border-bottom-color: #33403a;
}

/* 标签: 小印, 手写体 */
.ink-page :deep(.el-tag) {
    border-radius: 2px;
    font-family: var(--note-font-hand);
    letter-spacing: 0.12em;
}

/* 表格: 去掉外框与斑马纹, 只留细墨线 */
.ink-page :deep(.el-table) {
    --el-table-border-color: #e4ddcd;
    --el-table-header-bg-color: transparent;
    --el-table-tr-bg-color: transparent;
    --el-table-bg-color: transparent;
    --el-table-row-hover-bg-color: rgba(51, 64, 58, 0.05);
    border-radius: 0;
    box-shadow: none;
}

.ink-page :deep(.el-table th.el-table__cell) {
    background: transparent;
    font-family: var(--note-font-hand);
    font-weight: 600;
    letter-spacing: 0.1em;
}

/* 描述列表: 透明底, 标签用题跋字体 */
.ink-page :deep(.el-descriptions__body),
.ink-page :deep(.el-descriptions__cell) {
    background: transparent !important;
}

.ink-page :deep(.el-descriptions__label) {
    font-family: var(--note-font-hand);
    color: #6d756e;
}

/* 页签与对话框标题: 手写体收口 */
.ink-page :deep(.el-tabs__item),
.ink-page :deep(.el-dialog__title) {
    font-family: var(--note-font-hand);
    letter-spacing: 0.16em;
}

/* 提示条: 淡墨底, 无描边 */
.ink-page :deep(.el-alert) {
    background-color: rgba(51, 64, 58, 0.05);
}
</style>
