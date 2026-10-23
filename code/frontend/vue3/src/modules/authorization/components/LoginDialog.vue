<template>
  <!-- append-to-body: 吸顶 header 带 backdrop-filter 会成为 fixed 后代的包含块,
       不传送门到 body 弹窗会被困在顶栏内 -->
  <el-dialog v-model="visible" width="90%" class="auth-note-dialog max-w-[400px]" :modal="true" :close-on-click-modal="true"
    append-to-body draggable @close="handleClose">
    <template #header>
      <!-- 标题行: 手写体标题 + 朱砂闲章(pr-8 避让右上关闭键) -->
      <div class="flex items-center gap-12px pr-8">
        <span class="font-hand text-[1.45rem] font-semibold tracking-[0.08em] text-[var(--note-green-deep)]">{{
          $t('sign_in') }}</span>
        <span class="note-seal" aria-hidden="true">憩</span>
      </div>
    </template>

    <div p-10px>
      <el-form ref="loginFormRef" :model="loginForm" :rules="loginRules" label-position="top"
        @submit.prevent="handleLogin">
        <el-form-item :label="$t('username')" prop="username">
          <el-input v-model="loginForm.username" :placeholder="$t('placeholder_username')" autocomplete="username"
            :spellcheck="false" />
        </el-form-item>

        <el-form-item :label="$t('label_password')" prop="password">
          <el-input v-model="loginForm.password" type="password" :placeholder="$t('placeholder_password')"
            autocomplete="current-password"
            show-password />
        </el-form-item>

        <!-- 二次验证码(后端开启 login_security.mfa_enabled 时展示, 打开弹窗时拉取策略) -->
        <el-form-item v-if="mfaEnabled" :label="$t('label_email_code')" prop="code">
          <div flex gap-8px w-full>
            <el-input v-model="loginForm.code" :placeholder="$t('placeholder_email_code')"
              autocomplete="one-time-code" :spellcheck="false" />
            <el-button :disabled="countdown > 0" :loading="codeSending" @click="handleSendCode">
              {{ countdown > 0 ? $t('resend_in', { n: countdown }) : $t('send_code') }}
            </el-button>
          </div>
        </el-form-item>

        <el-form-item>
          <el-checkbox v-model="loginForm.remember">{{ $t('remember_me') }}</el-checkbox>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" w-full native-type="submit" :loading="loading">
            {{ $t('sign_in') }}
          </el-button>
        </el-form-item>
      </el-form>

      <div text-center mt-20px>
        <el-button type="info" link @click="handleSignUp">
          {{ $t('sign_up') }}
        </el-button>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
// 弹窗样式(渐变/纸纤维顶盖/EP 内部类覆盖)集中在模块内, 不污染全局
import '../styles/auth-dialog.css'
import { ElMessage } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { getLoginPolicy, loginUser, sendLoginCode } from '../api/auth'
import type {
  AuthLoginRequest,
  AuthResponse,
} from '../types/auth';
// 系统三语(中/英/日): 表单文案/校验/提示随语言切换
import { i18n } from '@/common/i18n/language'
const { t } = i18n.global


// 定义组件属性
const props = defineProps<{
  modelValue: boolean
}>()

// 定义事件发射
const emit = defineEmits<{
  'update:modelValue': [boolean]
  'login':  [AuthResponse]
  'register': []
}>()

// 控制弹窗显示
const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

// 登录表单引用
const loginFormRef = ref<FormInstance>()

// 加载状态
const loading = ref(false)

// 登录是否需要二次验证码(由后端 login_security.mfa_enabled 决定)
const mfaEnabled = ref(false)
// 验证码发送中
const codeSending = ref(false)
// 验证码重发倒计时(秒)
const countdown = ref(0)
let countdownTimer: ReturnType<typeof setInterval> | undefined

// 登录表单数据
const loginForm = reactive({
  username: '',
  password: '',
  code: '',
  remember: false
})

// 表单验证规则(computed: 校验文案随语言切换刷新)
const loginRules = computed(() => ({
  username: [
    { required: true, message: t('rule_username_required'), trigger: 'blur' }
  ],
  password: [
    { required: true, message: t('rule_password_required'), trigger: 'blur' },
    { min: 6, message: t('rule_password_min'), trigger: 'blur' }
  ],
  // 未开启二次验证时该表单项不渲染, 规则不会生效
  code: [
    { required: true, message: t('rule_code_required'), trigger: 'blur' }
  ]
}))

// 获取登录策略(是否需要二次验证码)
const loadLoginPolicy = async () => {
  try {
    const policy = await getLoginPolicy()
    mfaEnabled.value = policy.mfa_enabled
  } catch (error) {
    // 策略获取失败时按无需验证码处理, 避免阻塞登录
    console.error('获取登录策略失败:', error)
    mfaEnabled.value = false
  }
}

// 打开弹窗时同步登录策略
watch(visible, (val) => {
  if (val) loadLoginPolicy()
})

// 启动验证码重发倒计时
const startCountdown = () => {
  countdown.value = 60
  countdownTimer = setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0) clearInterval(countdownTimer)
  }, 1000)
}

// 发送登录二次验证码(发送至用户名绑定邮箱)
const handleSendCode = async () => {
  if (!loginFormRef.value) return
  // 先校验用户名必填, 校验不通过不发送
  try {
    await loginFormRef.value.validateField('username')
  } catch {
    return
  }
  codeSending.value = true
  try {
    await sendLoginCode(loginForm.username)
    ElMessage.success(t('msg_code_sent'))
    startCountdown()
  } catch (error) {
    ElMessage.error((error as { message?: string }).message || t('msg_code_send_failed'))
  } finally {
    codeSending.value = false
  }
}

// 关闭弹窗
const handleClose = () => {
  visible.value = false
  // 停止倒计时并重置表单
  clearInterval(countdownTimer)
  countdown.value = 0
  loginFormRef.value?.resetFields()
}

// 处理登录
const handleLogin = async () => {
  if (!loginFormRef.value) return
  await loginFormRef.value.validate(async (valid) => {
    if (valid) {
      loading.value = true
      try {
        // 准备登录数据(开启二次验证时携带验证码)
        const loginData: AuthLoginRequest = {
          username: loginForm.username,
          password: loginForm.password,
          ...(mfaEnabled.value ? { code: loginForm.code } : {})
        }
        // 调用登录API
        const authResponse: AuthResponse = await loginUser(loginData)
        // 发射登录事件
        emit('login', authResponse)
        handleClose()
      } catch (error: unknown) {
        console.error('登录失败:', error)
        // 添加错误提示(后端锁定/验证码等校验消息直接透出)
        ElMessage.error((error as { message?: string }).message || t('login_failed'))
      } finally {
        loading.value = false
      }
    }
  })
}

// 处理切换到注册
const handleSignUp = () => {
  handleClose()
  emit('register')
}

// 组件卸载时清理倒计时
onBeforeUnmount(() => clearInterval(countdownTimer))


</script>
