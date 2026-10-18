<template>
  <!-- append-to-body: 吸顶 header 带 backdrop-filter 会成为 fixed 后代的包含块,
       不传送门到 body 弹窗会被困在顶栏内 -->
  <el-dialog v-model="visible" width="90%" class="auth-note-dialog max-w-[400px]" :modal="true" :close-on-click-modal="true"
    append-to-body draggable @close="handleClose">
    <template #header>
      <!-- 标题行: 手写体标题 + 朱砂闲章(pr-8 避让右上关闭键) -->
      <div class="flex items-center gap-12px pr-8">
        <span class="font-hand text-[1.45rem] font-semibold tracking-[0.08em] text-[var(--note-green-deep)]">{{
          $t('sign_up') }}</span>
        <span class="note-seal" aria-hidden="true">憩</span>
      </div>
    </template>

    <div p-20px>
      <el-form ref="registerFormRef" :model="registerForm" :rules="registerRules as any" label-position="top"
        @submit.prevent="handleRegister">
        <el-form-item :label="$t('username')" prop="username">
          <el-input v-model="registerForm.username" :placeholder="$t('placeholder_username')" autocomplete="username"
            :spellcheck="false" />
        </el-form-item>

        <el-form-item :label="$t('email')" prop="email">
          <el-input v-model="registerForm.email" :placeholder="$t('email')" autocomplete="email" :spellcheck="false" />
        </el-form-item>

        <el-form-item v-if="emailVerify" :label="$t('label_email_code')" prop="code">
          <div flex gap-8px w-full>
            <el-input v-model="registerForm.code" :placeholder="$t('placeholder_email_code')"
              autocomplete="one-time-code" :spellcheck="false" />
            <el-button :disabled="countdown > 0" :loading="codeSending" @click="handleSendCode">
              {{ countdown > 0 ? $t('resend_in', { n: countdown }) : $t('send_code') }}
            </el-button>
          </div>
        </el-form-item>

        <el-form-item :label="$t('label_password')" prop="password">
          <el-input v-model="registerForm.password" type="password" :placeholder="$t('placeholder_password')"
            autocomplete="new-password" show-password />
        </el-form-item>

        <el-form-item :label="$t('label_confirm_password')" prop="confirmPassword">
          <el-input v-model="registerForm.confirmPassword" type="password" :placeholder="$t('placeholder_password_again')"
            autocomplete="new-password" show-password />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" w-full :loading="loading" @click="handleRegister">
            {{ $t('sign_up') }}
          </el-button>
        </el-form-item>
      </el-form>

      <div text-center mt-20px>
        <el-button type="info" link @click="handleBackToLogin">
          {{ $t('back_to_login') }}
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
import { getRegisterConfig, registerUser, sendRegisterCode } from '../api/auth'
import type { AuthRegisterRequest, AuthResponse } from '../types/auth'
// 系统三语(中/英/日): 表单文案/校验/提示随语言切换
import { i18n } from '@/common/i18n/language'
const { t } = i18n.global
// 定义组件属性
const props = defineProps<{
  modelValue: boolean
}>()

// 定义事件发射
const emit = defineEmits<{
  'update:modelValue': [boolean],
  'register-success': [AuthResponse],
  'back-to-login': []
}>()

// 控制弹窗显示
const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

// 注册表单引用
const registerFormRef = ref<FormInstance>()

// 加载状态
const loading = ref(false)

// 注册是否需要邮箱验证码(由后端 email.use_for_register 决定)
const emailVerify = ref(false)
// 验证码发送中
const codeSending = ref(false)
// 验证码重发倒计时(秒)
const countdown = ref(0)
let countdownTimer: ReturnType<typeof setInterval> | undefined

// 注册表单数据
const registerForm = reactive({
  username: '',
  email: '',
  password: '',
  confirmPassword: '',
  code: ''
})

// 表单验证规则(computed: 校验文案随语言切换刷新)
const registerRules = computed(() => ({
  username: [
    { required: true, message: t('rule_username_required'), trigger: 'blur' },
    { min: 3, max: 20, message: t('rule_username_len'), trigger: 'blur' }
  ],
  email: [
    { required: true, message: t('rule_email_required'), trigger: 'blur' },
    { type: 'email' as const, message: t('rule_email_invalid'), trigger: 'blur' }
  ],
  // 未开启邮箱验证时该表单项不渲染, 规则不会生效
  code: [
    { required: true, message: t('rule_code_required'), trigger: 'blur' }
  ],
  password: [
    { required: true, message: t('rule_password_required'), trigger: 'blur' },
    { min: 6, message: t('rule_password_min'), trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: t('rule_confirm_required'), trigger: 'blur' },
    {
      validator: (rule: unknown, value: string, callback: (error?: Error) => void) => {
        if (value !== registerForm.password) {
          callback(new Error(t('rule_password_mismatch')))
        } else {
          callback()
        }
      },
      trigger: 'blur'
    }
  ]
}))

// 获取注册配置(是否开启邮箱验证码)
const loadRegisterConfig = async () => {
  try {
    const config = await getRegisterConfig()
    emailVerify.value = config.email_verify
  } catch (error) {
    // 配置获取失败时按无需验证码处理, 避免阻塞注册
    console.error('获取注册配置失败:', error)
    emailVerify.value = false
  }
}

// 打开弹窗时同步注册配置
watch(visible, (val) => {
  if (val) loadRegisterConfig()
})

// 启动验证码重发倒计时
const startCountdown = () => {
  countdown.value = 60
  countdownTimer = setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0) clearInterval(countdownTimer)
  }, 1000)
}

// 发送邮箱验证码
const handleSendCode = async () => {
  if (!registerFormRef.value) return
  // 先校验邮箱格式, 校验不通过不发送
  try {
    await registerFormRef.value.validateField('email')
  } catch {
    return
  }
  codeSending.value = true
  try {
    await sendRegisterCode(registerForm.email)
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
  registerFormRef.value?.resetFields()
}

// 处理注册
const handleRegister = async () => {
  if (!registerFormRef.value) return

  await registerFormRef.value.validate(async (valid) => {
    if (valid) {
      loading.value = true
      try {
        // 准备注册数据
        const registerData: AuthRegisterRequest = {
          username: registerForm.username,
          password: registerForm.password,
          email: registerForm.email,
          // 开启邮箱验证时需携带验证码
          ...(emailVerify.value ? { code: registerForm.code } : {})
        }
        // 调用注册API
        const authResponse: AuthResponse = await registerUser(registerData)
        // 发射注册成功事件 并传递完整的AuthResponse对象
        emit('register-success', authResponse)
        handleClose()
      } catch (error) {
        console.error('注册失败:', error)
        if (error instanceof Error) {
          // 添加错误提示
          ElMessage.error(error.message || t('msg_register_failed'))
        }
      } finally {
        loading.value = false
      }
    }
  })
}

// 返回登录
const handleBackToLogin = () => {
  handleClose()
  emit('back-to-login')
}

// 组件卸载时清理倒计时
onBeforeUnmount(() => clearInterval(countdownTimer))


</script>
