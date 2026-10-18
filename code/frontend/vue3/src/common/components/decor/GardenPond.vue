<template>
  <!-- 小池: 国画写意风 —— 以留白为水, 墨分五色; 波边荷叶(飞白/叶脉/卷边) + 勾线荷花 +
       点景小鱼 + 断续水纹 + 苔点收边; 水面随鼠标划过荡开椭圆涟漪(uniform 涟漪环);
       颜色走 --note-* 亮暗自适应; 画幅经 UnoCSS mask 四周渐隐融入纸底(无组件矩形截断感);
       WebGL 不可用时回退极简 SVG, 减少动态时绘制静帧 -->
  <!-- 负 margin 抵消容器 padding: 画心比上方纸片更宽, 国画手卷"铺出纸边"的扩张感 -->
  <div class="pond-stage relative -mx-4 md:-mx-8">
    <!-- 回退: 无 WebGL 时的极简水面(渐变水体 + 水纹线) -->
    <svg
      v-if="fallback"
      class="pond block h-auto w-full select-none"
      :class="EDGE_FADE"
      viewBox="0 0 900 240"
      preserveAspectRatio="xMidYMax meet"
      role="img"
      aria-label="一方涟漪轻荡的小池"
    >
      <defs>
        <linearGradient id="pond-fallback" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" class="fb-stop-top" />
          <stop offset="100%" class="fb-stop-bottom" />
        </linearGradient>
      </defs>
      <path d="M0 64 C 220 38 680 38 900 64 L900 200 L0 200 Z" fill="url(#pond-fallback)" />
      <path d="M120 92 Q 450 84 780 92" class="fb-line" stroke-width="1.2" fill="none" />
      <path d="M60 118 Q 460 110 850 118" class="fb-line" stroke-width="1.2" fill="none" opacity="0.7" />
      <path d="M160 146 Q 470 138 760 146" class="fb-line" stroke-width="1.2" fill="none" opacity="0.5" />
    </svg>

    <canvas
      v-show="!fallback"
      ref="glCanvas"
      class="pond block w-full cursor-crosshair select-none"
      :class="EDGE_FADE"
      style="aspect-ratio: 900 / 240; height: auto"
      role="img"
      aria-label="一方可荡开涟漪的水墨小池"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerleave="onPointerLeave"
    ></canvas>

    <!-- 竖排题款 + 朱砂闲章(国画构图"画完必题"; pointer-events-none 不挡水面交互) -->
    <div
      v-if="!fallback"
      class="pointer-events-none absolute right-[2.5%] top-[10%] flex flex-col items-center gap-1.5"
      aria-hidden="true"
    >
      <span class="font-hand text-[12px] text-[var(--note-sub)] opacity-80 [writing-mode:vertical-rl] tracking-[0.35em]">小池</span>
      <span class="font-hand flex h-[17px] w-[17px] items-center justify-center rounded-[3px] bg-[var(--note-seal)] text-[10px] text-white/90">憩</span>
    </div>
  </div>
</template>

<script setup lang="ts">
// 水墨技法(国画写意): ①留白为水 —— 不铺满水色, 只以极淡水意 + 云影 noise 示意水面;
// ②墨分五色 —— 焦墨(苔点/鱼眼/蕊丝)/浓墨(叶缘/勾线)/重墨(叶身)/淡墨(水纹/茎)/清(倒影/水意);
// ③笔触感 —— 叶缘极坐标波状起伏 + 洇墨边(fbm 扰动双阈值) + 门控飞白(疏密不均) + 参差叶脉(意到笔不到);
// ④构图 —— 左近景浓墨大叶, 右侧勾线荷花斜出, 中左留白处一尾小鱼点景, 竖排题款收边。
// 交互涟漪: pointermove 采样落点(环形缓冲 8 槽)传 uniform, 片元中扩散环同时扰动波高场与可见淡墨环。
import { onBeforeUnmount, onMounted, ref } from 'vue'

/** WebGL 不可用时置真, 模板切换为极简 SVG 回退 */
const fallback = ref(false)

const glCanvas = ref<HTMLCanvasElement | null>(null)
let glRaf = 0
let cleanupGl: (() => void) | null = null

/** 逻辑分辨率(着色器内所有坐标均在此系中, y 向下; 显示端按 aspect-ratio 900/240 纵向拉伸 1.2 倍) */
const RES_X = 900.0
const RES_Y = 200.0

/** 画幅四周渐隐遮罩(canvas 与回退 SVG 复用): 双层 linear-gradient 相交渐变,
 *  左右 6% / 顶 9% / 底 13% 渐隐 —— 墨迹到组件边界前已融进纸底, 无矩形截断感 */
const EDGE_FADE = '[mask-image:linear-gradient(to_right,transparent,black_6%,black_94%,transparent),linear-gradient(to_bottom,transparent,black_9%,black_87%,transparent)] [mask-composite:intersect] [-webkit-mask-composite:source-in]'

/** 涟漪环形缓冲槽数(与 GL_FS 中 u_rip[8] 的 8 必须一致) */
const RIPPLE_N = 8

// ---------- 涟漪缓冲与注入 ----------
// 每槽 3 float: x, y, 触发时刻(birth); birth=-100 表示空槽(age 超界自动失效)
const ripData = new Float32Array(RIPPLE_N * 3)
for (let i = 0; i < RIPPLE_N; i++) ripData[i * 3 + 2] = -100
let ripHead = 0
/** 当前着色器时钟秒(RAF 帧内刷新; 指针事件读取以打涟漪时间戳) */
let glNow = 0
/** 上一次指针涟漪点 [x, y, t], 用于距离/时间节流 */
let lastPt: [number, number, number] | null = null

/** 注入一枚涟漪(落点为 900x200 逻辑坐标, t 为着色器时钟) */
function injectRipple(x: number, y: number, t: number) {
  ripData[ripHead * 3] = x
  ripData[ripHead * 3 + 1] = y
  ripData[ripHead * 3 + 2] = t
  ripHead = (ripHead + 1) % RIPPLE_N
}

/** 指针事件坐标 → 逻辑坐标 */
function toLogical(e: PointerEvent): [number, number] {
  const canvas = glCanvas.value
  if (!canvas) return [-1, -1]
  const rect = canvas.getBoundingClientRect()
  return [((e.clientX - rect.left) / rect.width) * RES_X, ((e.clientY - rect.top) / rect.height) * RES_Y]
}

/** 划过水面: 距上点 >~25px 且间隔 >150ms 才落一笔涟漪(疏朗自然, 不密不闹) */
function onPointerMove(e: PointerEvent) {
  const [x, y] = toLogical(e)
  if (y < 50) return // 远岸以上不算水面
  const now = glNow
  if (lastPt) {
    const dx = x - lastPt[0]
    const dy = y - lastPt[1]
    if (dx * dx + dy * dy < 640 || now - lastPt[2] < 0.15) return
  }
  lastPt = [x, y, now]
  injectRipple(x, y, now)
}

/** 点按水面: 溅一圈更大的涟漪(注入两枚错位点) */
function onPointerDown(e: PointerEvent) {
  const [x, y] = toLogical(e)
  if (y < 50) return
  injectRipple(x, y, glNow)
  injectRipple(x + 3, y + 2, glNow + 0.08)
}

function onPointerLeave() {
  lastPt = null
}

/** 顶点着色器: 全屏四边形 + UV */
const GL_VS = `
attribute vec2 a;
varying vec2 v_uv;
void main() {
  v_uv = a * 0.5 + 0.5;
  gl_Position = vec4(a, 0.0, 1.0);
}`

/** 片元着色器: 国画写意小池(留白水面/波边荷叶/勾线荷花/小鱼/水纹/苔点/涟漪), straight alpha 输出 */
const GL_FS = `
precision mediump float;
varying vec2 v_uv;
uniform float u_time;
uniform vec3 u_water_top;   // 水意淡色(--note-water)
uniform vec3 u_water_deep;  // 近景深水(--note-water-deep)
uniform vec3 u_ink;         // 墨色(--note-ink, 亮暗自适应)
uniform vec3 u_ink_deep;    // 焦墨(JS 按主题亮度再压一档/提一档)
uniform vec3 u_glint;       // 波光(--note-green)
uniform vec3 u_lotus;       // 荷瓣(--note-lotus)
uniform vec3 u_core;        // 花蕊金(--note-lotus-core)
uniform vec3 u_line;        // 水纹线(--note-water-line)
uniform float u_ink_k;      // 主题墨浓因子: 亮纸 1.0(浓墨提神), 暗纸 ~0.5(夜荷剪影, 防亮墨大面积成灰盘)
uniform vec3 u_rip[8];      // 涟漪: xy=落点, z=触发时刻(与 JS RIPPLE_N 一致)

const vec2 RES = vec2(${RES_X}, ${RES_Y});

// ---------- 基础噪声 ----------
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123); }
float noise(vec2 p) {
  vec2 i = floor(p); vec2 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x),
             mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}
float fbm(vec2 p) {
  float v = 0.0; float a = 0.5;
  for (int i = 0; i < 2; i++) { v += a * noise(p); p = p * 2.07 + vec2(19.7, 7.3); a *= 0.5; }
  return v;
}

// ---------- SDF 工具 ----------
vec2 rot2(vec2 p, float a) { float c = cos(a); float s = sin(a); return mat2(c, -s, s, c) * p; }
float sdSeg(vec2 p, vec2 a, vec2 b) {
  vec2 pa = p - a; vec2 ba = b - a;
  float h = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0);
  return length(pa - ba * h);
}
float sdEllipse(vec2 p, vec2 c, vec2 r) {
  vec2 q = (p - c) / r;
  return (length(q) - 1.0) * min(r.x, r.y);
}
// 宣纸洇墨: SDF + fbm 扰动后双阈值 -> vec2(淡墨晕, 浓墨核)
vec2 ink(vec2 p, float d, float seed, float grain, float soft) {
  float n = (fbm(p * grain + seed) - 0.5) * 2.0;
  float dd = d + n * soft;
  return vec2(smoothstep(2.4, -0.8, dd), smoothstep(1.5, -1.5, dd));
}
// straight-alpha "src over dst" 合成
vec4 over(vec4 dst, vec4 src) {
  float a = src.a + dst.a * (1.0 - src.a);
  vec3 rgb = (src.rgb * src.a + dst.rgb * dst.a * (1.0 - src.a)) / max(a, 1e-4);
  return vec4(rgb, a);
}

// ---------- 涟漪(鼠标/环境落水): 扩散环, 返回 vec2(波高扰动, 可见环强度) ----------
// 波高用宽带(水感), 可见环用细带(细笔勾圈, 不随年龄摊宽成灰雾)
vec2 ripple(vec2 p, vec3 r3, float t) {
  float age = t - r3.z;
  if (age < 0.001 || age > 6.0) return vec2(0.0);
  vec2 dv = p - r3.xy;
  dv.y *= 2.4;                       // 俯视池塘透视: 涟漪压扁成横椭圆
  float d = length(dv);
  float x = d - age * 26.0;
  float sigW = 2.5 + age * 2.6;
  float sigR = 1.8 + age * 0.55;
  float rise = smoothstep(0.0, 0.1, age);
  float bandW = exp(-x * x / (2.0 * sigW * sigW));
  float bandR = exp(-x * x / (2.0 * sigR * sigR));
  return vec2(sin(x * 0.9) * bandW * exp(-age * 0.45) * rise, bandR * exp(-age * 0.85) * rise);
}

// ---------- 波光高度场: 双层 noise 轻量版(涟漪不进波场——可见环已单独负责, 省 24 次 ripple/px) ----------
float glintH(vec2 p, float t) {
  return noise(p * vec2(0.055, 0.12) + vec2(t * 0.14, -t * 0.05))
       + 0.5 * noise(p * 0.12 + vec2(-t * 0.2, t * 0.07));
}

// ---------- 水纹(淡墨长弧, 笔断意连: 噪声调制断续) ----------
float inkLine(vec2 p, float cy, float arc, float x0, float x1, float seed) {
  float halfw = (x1 - x0) * 0.5;
  float u = (p.x - (x0 + x1) * 0.5) / halfw;
  float yl = cy - arc * (1.0 - u * u) + sin(p.x * 0.03 + seed * 9.0) * 1.2;
  float seg = noise(vec2(p.x * 0.045 + seed * 40.0, cy * 0.1));
  float m = smoothstep(1.3, 0.4, abs(p.y - yl)) * smoothstep(1.0, 0.86, abs(u));
  return m * smoothstep(0.32, 0.60, seg);
}

// ---------- 远岸: 一条淡墨横带(两端渐隐, 下缘洇) ----------
float farBank(vec2 p) {
  float band = smoothstep(47.0, 41.5, p.y) * smoothstep(34.0, 38.5, p.y);
  float ends = smoothstep(60.0, 180.0, p.x) * smoothstep(880.0, 760.0, p.x);
  return band * ends * (0.55 + 0.9 * noise(p * 0.10 + 5.0)) * 0.18;
}

// ---------- 水墨荷叶(波边圆盘): 单位域归一后 SDF ----------
// 波状叶缘(三谐波起伏) + 叶裂缺口 + 心淡缘浓 + 侧锋浓淡起伏 + 门控飞白 + 偏心叶脉(意到笔不到) + 卷边折痕
vec4 lilyPad(vec2 p, vec2 c, vec2 r, float seed, float strength) {
  vec2 q = p - c;
  q.x *= r.y / r.x;
  float rl = length(q);
  float ang = atan(q.y, q.x);
  float wob = 1.0 + 0.13 * sin(ang * 3.0 + seed * 7.0) + 0.06 * sin(ang * 7.0 - seed * 3.7)
            + 0.045 * sin(ang * 11.0 + seed * 13.0);
  float rw = rl / (r.y * wob);  // 归一化到单位圆域(压缩域纵向半径 = r.y), 漏除会使叶塌缩成一点
  float d = (rw - 1.0) * r.y;
  // 叶裂缺口(向外楔形切入)
  float gapA = seed * 6.2832 + 1.2;
  float gd = abs(atan(sin(ang - gapA), cos(ang - gapA)));
  d -= smoothstep(0.34, 0.12, gd) * 10.0;
  vec2 m = ink(p, d, seed, 0.085, 2.3);
  float body = m.x;
  // 主题墨浓因子: 亮纸满浓(α² 后≈浓墨提神); 暗纸压回夜荷剪影。只压面积墨,
  // 线画(叶脉/折痕/心墨)不压——暗底上保留"微亮勾边"
  float kk = u_ink_k;
  float sh = body * 0.55 * kk;                                   // 叶身重墨
  sh += smoothstep(0.55, 0.95, rw) * body * 0.30 * kk;           // 墨向边缘聚(缘浓)
  // 浓面扇区: 半侧沉墨, 破"均匀灰盘"(浓淡两笔)
  sh += smoothstep(0.1, 0.9, sin(ang - (seed * 2.7 + 1.0))) * body * 0.14 * kk;
  // 侧锋扫笔的浓淡节奏(一笔之内有起伏, 不再均匀)
  sh *= 0.88 + 0.12 * sin(ang * 2.3 + seed * 3.1);
  // 飞白: 门控疏密不均(局部扇区才有干笔丝, 意到笔不到)
  float fbw = sin(ang * 18.0 + fbm(p * 0.10 + seed) * 9.0) * 0.5 + 0.5;
  float gate = noise(vec2(ang * 1.9 + seed, rw * 3.0));
  float fly = smoothstep(0.60, 0.80, fbw) * smoothstep(0.42, 0.62, gate)
            * smoothstep(0.30, 0.5, rw) * smoothstep(0.98, 0.82, rw);
  sh *= 1.0 - fly * body * 0.55;
  // 叶脉: 从偏心叶脐放射破"伞骨"感; 只画中环带短线, 心与缘都留白(意到笔不到)
  float vein = 1e3;
  vec2 umb = vec2(-0.10 + 0.06 * hash(vec2(seed, 1.0)), 0.07 * hash(vec2(seed, 2.0))) * 0.86;
  float a0 = gapA + 0.55;
  float vn = 3.0 + step(18.0, r.y) * 2.0;    // 小叶只勾 3 脉, 大叶 5 脉(防小叶挤成放射盘)
  for (int i = 0; i < 5; i++) {
    float fi = float(i);
    if (fi < vn) {
      float jit = (hash(vec2(seed, fi)) - 0.5) * 0.3;
      float len = 0.86 * (0.62 + 0.34 * hash(vec2(fi, seed)));
      float a = a0 + fi * 0.98 + jit;
      vein = min(vein, sdSeg(q, umb, umb + vec2(cos(a), sin(a)) * len));
    }
  }
  sh += smoothstep(0.30, 0.02, vein) * smoothstep(0.26, 0.5, rw) * smoothstep(0.96, 0.72, rw) * body * 0.42;
  sh += smoothstep(0.18, 0.02, rw) * body * 0.30;                // 叶心笔根驻墨
  // 卷边折痕: 从心向边的一笔浓墨弧(翻叶向背)
  float fa = seed * 5.1;
  float fold = sdSeg(q, vec2(cos(fa) * 0.15, sin(fa) * 0.15), vec2(cos(fa + 0.6) * 0.82, sin(fa + 0.6) * 0.82));
  sh += smoothstep(0.30, 0.02, fold) * body * 0.30;
  return vec4(mix(u_ink, u_glint, 0.16), clamp(sh, 0.0, 0.9) * strength);  // 叶面罩一丝汁绿(没骨淡彩)
}

// ---------- 水墨荷花(勾线填色): 极坐标瓣(中宽端尖) + 淡填 + 浓墨勾边 + 蕊 ----------
float petalN(float rr, float dA, float halfW) {
  float w = halfW * (1.0 - 0.62 * rr * rr);
  return max(rr - 1.0, dA / max(w, 0.06) - 1.0);
}
vec4 lotusFlower(vec2 p, vec2 c, float s, float alpha) {
  vec4 acc = vec4(0.0);
  // 5 主瓣参差排布(y 向下坐标, 正上为瓣尖; 正侧俯仰各有别)
  for (int i = 0; i < 5; i++) {
    float fi = float(i);
    // 写意: 瓣有正侧俯仰——角度/长短/宽窄各自参差, 不排扇形
    float jitA = (hash(vec2(fi * 3.7, s)) - 0.5) * 0.34;
    float jitL = 0.86 + 0.28 * hash(vec2(fi * 7.1, s + 1.3));
    float jitW = 0.36 + 0.12 * hash(vec2(fi * 2.9, s + 2.6));
    float a = radians(-72.0 + 36.0 * fi) + jitA;
    vec2 q = rot2(p - c, a);
    float rr = length(q) / (13.0 * s * jitL);
    float dA = abs(atan(q.x, -q.y));
    float d = petalN(rr, dA, jitW) + (fbm(p * 0.35 + fi * 3.1) - 0.5) * 0.12;
    float body = smoothstep(0.12, -0.06, d);
    // 勾线时浓时淡(笔断意连); 过渡带放宽如洇开, 系数已按 α² 显示效应反推
    float edge = smoothstep(0.60, 0.05, abs(d)) * (0.68 + 0.32 * noise(p * 0.22 + fi));
    acc = over(acc, vec4(u_lotus, body * 0.50 * alpha));
    acc = over(acc, vec4(u_ink, edge * 0.60 * alpha));
  }
  // 左右横卧侧瓣(淡填 + 勾线)
  float dl = sdEllipse(p, c + vec2(-10.5 * s, 2.0 * s), vec2(7.0 * s, 2.9 * s));
  float nl = (fbm(p * 0.35 + 13.7) - 0.5) * 2.0;
  float bl = smoothstep(1.1, -0.5, dl + nl * 1.2);
  acc = over(acc, vec4(u_lotus, bl * 0.44 * alpha));
  acc = over(acc, vec4(u_ink, smoothstep(1.8, 0.15, abs(dl + nl * 1.2)) * 0.42 * alpha));
  float dr = sdEllipse(p, c + vec2(10.5 * s, 2.0 * s), vec2(7.0 * s, 2.9 * s));
  float nr = (fbm(p * 0.35 + 21.3) - 0.5) * 2.0;
  float br = smoothstep(1.1, -0.5, dr + nr * 1.2);
  acc = over(acc, vec4(u_lotus, br * 0.44 * alpha));
  acc = over(acc, vec4(u_ink, smoothstep(1.8, 0.15, abs(dr + nr * 1.2)) * 0.42 * alpha));
  // 莲蕊: 花色淡晕 + 5 向焦墨蕊丝(角度参差) + 心点
  vec2 qc = p - c;
  float rc = length(qc) / s;
  acc = over(acc, vec4(u_core, smoothstep(4.6, 1.6, rc) * 0.36 * alpha));
  float st = 1e3;
  for (int i = 0; i < 5; i++) {
    float a = 6.2832 * float(i) / 5.0 + 0.35 + (hash(vec2(float(i), 9.1)) - 0.5) * 0.5;
    st = min(st, sdSeg(qc, vec2(cos(a), sin(a)) * 1.3 * s, vec2(cos(a), sin(a)) * 4.0 * s));
  }
  acc = over(acc, vec4(u_ink_deep, smoothstep(1.4, 0.2, st) * 0.55 * alpha));
  acc = over(acc, vec4(u_ink_deep, smoothstep(1.8 * s, 0.6 * s, rc) * 0.6 * alpha));
  return acc;
}

// ---------- 点景小鱼(写意三笔): 淡墨纺锤身 + 浓墨摆尾 + 焦墨眼 ----------
vec4 fish(vec2 p, vec2 c, float t, float alpha) {
  vec2 cc = c + vec2(sin(t * 0.32) * 17.0, sin(t * 0.75) * 1.6);
  vec2 q = p - cc;
  float wag = sin(t * 3.0) * 0.32;
  float db = sdEllipse(q, vec2(0.0), vec2(10.5, 2.9));
  float body = smoothstep(1.15, -0.5, db + (fbm(p * 0.5 + 7.0) - 0.5) * 1.3);
  float grad = 1.0 - smoothstep(-4.0, 10.0, q.x) * 0.42;   // 写意一笔: 头浓尾淡
  vec4 acc = over(vec4(0.0), vec4(u_ink, body * grad * 0.58 * alpha));
  acc = over(acc, vec4(u_ink, smoothstep(1.6, 0.05, sdSeg(q, vec2(-5.2, -2.2), vec2(-4.4, 2.2))) * 0.38 * alpha));
  vec2 tq = rot2(q - vec2(9.5, 0.0), wag);
  float tail = smoothstep(1.0, -0.3, sdEllipse(tq, vec2(5.5, 0.0), vec2(5.0, 2.1)));
  acc = over(acc, vec4(u_ink, tail * 0.72 * alpha));
  acc = over(acc, vec4(u_ink, smoothstep(1.6, 0.05, sdSeg(q, vec2(1.5, -2.4), vec2(5.0, -3.6))) * 0.45 * alpha));
  acc = over(acc, vec4(u_ink, smoothstep(1.4, 0.05, sdSeg(q, vec2(2.0, 2.3), vec2(-0.5, 4.4))) * 0.35 * alpha));
  acc = over(acc, vec4(u_ink_deep, smoothstep(1.6, 0.3, length(q - vec2(-7.4, -0.5))) * 0.9 * alpha));
  return acc;
}

// ---------- 苔点收边(焦墨聚点 + 淡晕) ----------
vec4 mossDots(vec2 p, vec2 c, float seed, float alpha) {
  float d = 1e3;
  for (int i = 0; i < 3; i++) {
    float fi = float(i);
    vec2 o = vec2(sin(seed * 9.0 + fi * 2.3) * 7.0, cos(seed * 5.0 + fi * 3.1) * 4.5);
    d = min(d, length(p - c - o) - (1.7 + fi * 0.4));
  }
  vec2 m = ink(p, d, seed, 0.3, 1.0);
  return vec4(u_ink_deep, clamp(m.y * 0.75 + m.x * 0.2, 0.0, 1.0) * alpha);
}

void main() {
  vec2 uv = v_uv;
  float t = u_time;
  vec2 p = vec2(uv.x * RES.x, (1.0 - uv.y) * RES.y);
  float bob = sin(t * 0.8) * 1.5;

  vec4 acc = vec4(0.0);

  // ===== 1. 水意留白: 极淡水色 + 云影浓淡(墨分五色之"清", 留白呼吸) =====
  // waterM 顶界再放宽(44..96, 水面与纸底长过渡带雾化不显截线); frameX 左右 110px 淡出 + 底部减淡,
  // 叠加组件级 UnoCSS mask 四周渐隐 —— shader 内淡出 + 显示遮罩双重柔化
  float waterM = smoothstep(44.0, 96.0, p.y);
  float frameX = smoothstep(0.0, 110.0, p.x) * smoothstep(900.0, 790.0, p.x);
  float frameB = 1.0 - smoothstep(184.0, 200.0, p.y) * 0.55;
  float depthT = smoothstep(44.0, 200.0, p.y);
  vec3 wash = mix(u_water_top, u_water_deep, depthT * 0.65);
  float washA = (0.10 + 0.05 * depthT) * (0.7 + 0.6 * noise(p * 0.013 + vec2(t * 0.012, 0.0)));
  acc = over(acc, vec4(wash, washA * waterM * frameX * frameB));

  // ===== 2. 远岸淡墨横带(两端渐隐) =====
  acc = over(acc, vec4(u_ink, farBank(p) * frameX));

  // ===== 3. 水纹三笔(笔断意连) =====
  float ln = inkLine(p, 112.0, 3.0, 210.0, 560.0, 0.2) * 0.34;
  ln = max(ln, inkLine(p, 156.0, 4.0, 140.0, 820.0, 0.5) * 0.22);
  ln = max(ln, inkLine(p, 78.0, 2.0, 470.0, 856.0, 0.8) * 0.17);
  acc = over(acc, vec4(u_line, ln * waterM * frameX));

  // ===== 4. 波场微光(轻量 noise 差分, 高光只留一丝) =====
  float h = glintH(p, t);
  float e = 2.0;
  float hx = glintH(p + vec2(e, 0.0), t) - h;
  float hy = glintH(p + vec2(0.0, e), t) - h;
  vec3 n = normalize(vec3(-hx * 3.0, hy * 3.0, 1.0));
  float spec = pow(max(dot(n, normalize(vec3(0.3, 0.55, 0.75))), 0.0), 26.0);
  acc = over(acc, vec4(u_glint, spec * 0.13 * waterM * frameX));

  // ===== 5. 涟漪可见环: 细墨勾圈 + 一丝波光(留白水面上清晰可读) =====
  float ripVis = 0.0;
  for (int i = 0; i < 8; i++) ripVis += ripple(p, u_rip[i], t).y;
  acc = over(acc, vec4(u_ink, min(ripVis, 1.2) * 0.30 * waterM * frameX));
  acc = over(acc, vec4(u_glint, min(ripVis, 1.2) * 0.15 * waterM * frameX));

  // ===== 6. 倒影墨晕(清档: 花影/大叶影, 极淡拉伸) =====
  acc = over(acc, vec4(u_lotus, smoothstep(40.0, 6.0, abs(p.y - 97.0)) * smoothstep(42.0, 10.0, abs(p.x - 672.0)) * 0.06));
  acc = over(acc, vec4(u_ink, smoothstep(26.0, 5.0, length((p - vec2(96.0, 176.0)) * vec2(1.0, 2.6))) * 0.06));

  // ===== 7. 收束: 花头无根斜入(画外旁逸), 不画茎——留白更显空灵 =====

  // ===== 8. 主体: 左近景浓墨大叶 -> 中叶/小叶 -> 勾线荷花 -> 点景小鱼 =====
  acc = over(acc, lilyPad(p, vec2(92.0, 148.0 + bob * 0.3), vec2(74.0, 24.0), 0.35, 1.0));
  acc = over(acc, lilyPad(p, vec2(592.0, 98.0 + bob * 0.5), vec2(44.0, 15.0), 2.9, 0.85));
  acc = over(acc, lilyPad(p, vec2(778.0, 88.0 + bob * 0.5), vec2(26.0, 9.0), 5.1, 0.72));
  acc = over(acc, lotusFlower(p, vec2(672.0, 60.0 + bob), 1.6, 0.95));
  acc = over(acc, fish(p, vec2(392.0, 128.0), t, 0.9));

  // ===== 9. 苔点收边(焦墨, 左右两组) =====
  acc = over(acc, mossDots(p, vec2(34.0, 184.0), 11.0, 0.9));
  acc = over(acc, mossDots(p, vec2(862.0, 178.0), 17.0, 0.85));

  // ===== 10. 岸际薄雾(水色极淡横雾, 缓慢漂移) =====
  {
    float band = exp(-pow((p.y - 52.0) / 13.0, 2.0));
    float m = noise(vec2(p.x * 0.012 - t * 0.02, p.y * 0.05));
    acc = over(acc, vec4(u_water_top, band * smoothstep(0.36, 0.8, m) * 0.12 * waterM * frameX));
  }

  gl_FragColor = acc;
}`

/** 从 CSS 变量读取颜色(亮暗主题自适应), 解析为 0..1 RGB */
function cssRGB(name: string, fallbackRgb: [number, number, number]): [number, number, number] {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  const probe = document.createElement('canvas').getContext('2d')
  if (!probe || !raw) return fallbackRgb
  probe.fillStyle = raw
  const m = /rgba?\(([^)]+)\)/.exec(probe.fillStyle as string)
  if (m) {
    const parts = m[1].split(',').map(Number)
    return [parts[0] / 255, parts[1] / 255, parts[2] / 255]
  }
  const hex = /^#([0-9a-f]{6})$/i.exec(probe.fillStyle as string)
  if (hex) {
    const n = parseInt(hex[1], 16)
    return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255]
  }
  return fallbackRgb
}

/** 初始化 WebGL 水墨池塘; 失败则切换 SVG 回退 */
function setupGl(reducedMotion: boolean) {
  const canvas = glCanvas.value
  if (!canvas) return
  // alpha 透明(留白处露出页面纸底), straight alpha 输出
  const gl = canvas.getContext('webgl', { antialias: false, alpha: true, premultipliedAlpha: false, powerPreference: 'low-power' })
  if (!gl) {
    fallback.value = true
    return
  }

  const compile = (type: number, src: string) => {
    const sh = gl.createShader(type)!
    gl.shaderSource(sh, src)
    gl.compileShader(sh)
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh) || 'compile failed')
    return sh
  }
  let program: WebGLProgram
  try {
    program = gl.createProgram()!
    gl.attachShader(program, compile(gl.VERTEX_SHADER, GL_VS))
    gl.attachShader(program, compile(gl.FRAGMENT_SHADER, GL_FS))
    gl.linkProgram(program)
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getShaderInfoLog(program) || 'link failed')
  } catch {
    fallback.value = true
    return
  }
  gl.useProgram(program)
  gl.enable(gl.BLEND)
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)
  gl.clearColor(0, 0, 0, 0)

  // 全屏四边形
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer())
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW)
  const loc = gl.getAttribLocation(program, 'a')
  gl.enableVertexAttribArray(loc)
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0)

  const U = (n: string) => gl.getUniformLocation(program, n)
  const uTime = U('u_time')
  const uWaterTop = U('u_water_top')
  const uWaterDeep = U('u_water_deep')
  const uInk = U('u_ink')
  const uInkDeep = U('u_ink_deep')
  const uGlint = U('u_glint')
  const uLotus = U('u_lotus')
  const uCore = U('u_core')
  const uLine = U('u_line')
  const uRip = U('u_rip')
  const uInkK = U('u_ink_k')

  // 颜色取自 --note-* 变量(亮暗自适应); 焦墨按墨色亮度再压一档(亮纸)/提一档(暗纸)
  const applyColors = () => {
    gl.uniform3f(uWaterTop, ...cssRGB('--note-water', [0.81, 0.89, 0.87]))
    gl.uniform3f(uWaterDeep, ...cssRGB('--note-water-deep', [0.64, 0.79, 0.74]))
    const ink = cssRGB('--note-ink', [0.24, 0.3, 0.27])
    const green = cssRGB('--note-green', [0.42, 0.62, 0.47])
    // 墨掺一滴汁绿(浅绛淡彩): 明暗主题的墨都带淡淡绿意, 不再纯黑白灰
    const inkGreen: [number, number, number] = [
      ink[0] + (green[0] - ink[0]) * 0.16,
      ink[1] + (green[1] - ink[1]) * 0.16,
      ink[2] + (green[2] - ink[2]) * 0.16,
    ]
    gl.uniform3f(uInk, ...inkGreen)
    const lum = inkGreen[0] * 0.3 + inkGreen[1] * 0.6 + inkGreen[2] * 0.1
    const k = lum > 0.5 ? 1.22 : 0.55
    gl.uniform3f(uInkDeep, inkGreen[0] * k, inkGreen[1] * k, inkGreen[2] * k)
    // 墨浓因子: 暗纸(墨色为亮值)把叶身面积墨压回夜荷剪影, 亮纸满浓
    gl.uniform1f(uInkK, lum > 0.5 ? 0.5 : 1.0)
    gl.uniform3f(uGlint, ...cssRGB('--note-green', [0.42, 0.62, 0.47]))
    gl.uniform3f(uLotus, ...cssRGB('--note-lotus', [0.91, 0.76, 0.73]))
    gl.uniform3f(uCore, ...cssRGB('--note-lotus-core', [0.76, 0.61, 0.34]))
    gl.uniform3f(uLine, ...cssRGB('--note-water-line', [0.33, 0.5, 0.38]))
  }
  applyColors()

  // 尺寸自适应(dpr 上限 1.25, 水墨低频画面视觉无差而像素量更省)
  const resize = () => {
    const dpr = Math.min(window.devicePixelRatio || 1, 1.25)
    const w = Math.max(1, Math.round(canvas.clientWidth * dpr))
    const h = Math.max(1, Math.round(canvas.clientHeight * dpr))
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w
      canvas.height = h
      gl.viewport(0, 0, w, h)
    }
  }
  resize()
  const ro = new ResizeObserver(resize)
  ro.observe(canvas)

  // 主题切换(html.dark)时重读颜色
  const mo = new MutationObserver(applyColors)
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })

  const draw = (time: number) => {
    gl.uniform1f(uTime, time)
    gl.uniform3fv(uRip, ripData)
    gl.clear(gl.COLOR_BUFFER_BIT)
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
  }

  if (reducedMotion) {
    // 减少动态: 静帧, 预置两圈涟漪保持画意
    injectRipple(470, 120, 6 - 1.3)
    injectRipple(300, 142, 6 - 2.6)
    draw(6)
    return
  }

  // 环境涟漪: 无鼠标时每隔数秒在两处轮替落一滴, 维持画面生气
  let lastAuto = 0
  let autoSlot = 0

  // 页面不可见时暂停渲染循环, 回来时续播(时钟连续, 涟漪不跳变)
  let pausedAt: number | null = null
  let elapsed = 0
  const t0 = performance.now()
  let lastFrameAt = 0
  // 视口外不绘制(canvas 滚出屏幕即停, 回来自动恢复), 省下页面上半屏操作时的 GPU
  let inView = true
  const io = new IntersectionObserver((es) => { inView = es[0]?.isIntersecting ?? true })
  io.observe(canvas)
  const frame = () => {
    glRaf = requestAnimationFrame(frame)
    if (pausedAt !== null || !inView) return
    const nowMs = performance.now()
    if (nowMs - lastFrameAt < 33) return // 限 30fps: 水墨动态缓慢, 视觉无差而 GPU 约减半
    lastFrameAt = nowMs
    elapsed = (nowMs - t0) / 1000
    glNow = elapsed
    if (elapsed - lastAuto > 7.0) {
      lastAuto = elapsed
      autoSlot = 1 - autoSlot
      const ax = autoSlot === 0 ? 470 : 300
      const ay = autoSlot === 0 ? 120 : 142
      injectRipple(ax + (Math.random() - 0.5) * 24, ay + (Math.random() - 0.5) * 12, elapsed)
    }
    draw(elapsed)
  }
  glRaf = requestAnimationFrame(frame)
  const onVis = () => {
    if (document.hidden) pausedAt = performance.now()
    else pausedAt = null
  }
  document.addEventListener('visibilitychange', onVis)

  cleanupGl = () => {
    ro.disconnect()
    mo.disconnect()
    io.disconnect()
    document.removeEventListener('visibilitychange', onVis)
  }
}

onMounted(() => {
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  setupGl(reducedMotion)
})

onBeforeUnmount(() => {
  cancelAnimationFrame(glRaf)
  cleanupGl?.()
})
</script>

<style scoped>
/* 回退 SVG 渐变与墨线(仅无 WebGL 时可见) */
.fb-stop-top { stop-color: var(--note-water); }
.fb-stop-bottom { stop-color: var(--note-water-deep); }
.fb-line { stroke: var(--note-water-line); stroke-linecap: round; }
</style>
