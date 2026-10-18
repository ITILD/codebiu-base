"""验证码通用缓存策略(邮件/短信双通道共用, 与通道实现解耦)"""

# 验证码位数
CODE_LENGTH = 6
# 验证码有效期(秒)
CODE_TTL_SECONDS = 300
# 同一目标验证码发送间隔(秒), 防止频繁发送
CODE_COOLDOWN_SECONDS = 60

# 验证码缓存键(值: 验证码字符串; scene 区分业务场景, 防跨场景复用)
CODE_KEY = "contact:code:{scene}:{target}"
# 发送冷却缓存键(值: 固定标记)
CODE_COOLDOWN_KEY = "contact:code:cooldown:{scene}:{target}"
