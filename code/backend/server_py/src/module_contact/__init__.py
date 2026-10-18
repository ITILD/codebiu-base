"""联系方式触达模块(库模式, 不挂路由): 邮件/短信发送与验证码统一生命周期

- service/email.py    EmailService SMTP 邮件发送
- service/sms.py      SmsService 阿里云短信发送(httpx 直连, 零额外 SDK)
- service/verify_code.py VerifyCodeService 验证码生成/冷却/校验(双通道自动路由)
对外仅暴露 service 与依赖注入工厂, 供认证等模块调用(如注册邮箱验证码)
"""
