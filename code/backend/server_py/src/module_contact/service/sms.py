"""阿里云短信服务(httpx 直连 Dysmsapi RPC 接口, 零额外 SDK 依赖)

- 配置来自动态配置中心 SmsSettings(AccessKey/签名/模板)
- 使用阿里云 RPC V1.0 签名(HMAC-SHA1), 参见阿里云短信 API 文档
- send_code 发送手机验证码短信, 供 VerifyCodeService 双通道调度
"""
import base64
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from common.config.dynamic import get_settings
from common.config.dynamic.schemas import SmsSettings

logger = logging.getLogger(__name__)

# 阿里云短信 API 入口(dysmsapi)
_DYSMSAPI_URL = "https://dysmsapi.aliyuncs.com/"


def _percent_encode(value: str) -> str:
    """阿里云 RPC 签名专用百分号编码(RFC3986, 仅保留 A-Za-z0-9-_.~)"""
    return quote(str(value), safe="-_.~")


def _sign(params: dict[str, str], access_key_secret: str) -> str:
    """阿里云 RPC V1.0 签名: 参数按名排序拼接 → HMAC-SHA1(密钥 = Secret + '&')"""
    sorted_query = "&".join(
        f"{_percent_encode(k)}={_percent_encode(v)}" for k, v in sorted(params.items())
    )
    string_to_sign = f"GET&%2F&{_percent_encode(sorted_query)}"
    digest = hmac.new(
        f"{access_key_secret}&".encode(), string_to_sign.encode(), hashlib.sha1
    ).digest()
    return base64.b64encode(digest).decode()


class SmsService:
    """阿里云短信服务(异步发送, 按需读取动态配置)"""

    async def _send(self, phone: str, template_param: dict, template_code: str | None = None) -> bool:
        """发送短信
        :param phone: 收件手机号(大陆 11 位)
        :param template_param: 模板变量(如 {"code": "123456"})
        :param template_code: 模板 CODE(默认取动态配置的验证码模板)
        :return: 是否发送成功(失败仅告警, 由调用方决定提示语)
        """
        cfg = await get_settings(SmsSettings)
        if not cfg.access_key_id or not cfg.access_key_secret:
            logger.warning("短信服务未配置(access_key_id/access_key_secret 为空), 跳过发送")
            return False
        params = {
            "Action": "SendSms",
            "Version": "2017-05-25",
            "Format": "JSON",
            "RegionId": "cn-hangzhou",
            "AccessKeyId": cfg.access_key_id,
            "SignatureMethod": "HMAC-SHA1",
            "SignatureVersion": "1.0",
            "SignatureNonce": str(uuid.uuid4()),
            "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "PhoneNumbers": phone,
            "SignName": cfg.sign_name,
            "TemplateCode": template_code or cfg.template_code,
            "TemplateParam": json.dumps(template_param, ensure_ascii=False),
        }
        params["Signature"] = _sign(params, cfg.access_key_secret)
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(_DYSMSAPI_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
            # 阿里云业务失败 HTTP 仍 200, 以响应 Code 判定
            if data.get("Code") != "OK":
                logger.error(f"短信发送失败(to={phone}): {data.get('Code')} {data.get('Message')}")
                return False
            return True
        except Exception as e:
            logger.error(f"短信发送异常(to={phone}): {e}")
            return False

    async def send_code(self, phone: str, code: str, ttl_minutes: int) -> bool:
        """发送验证码短信(邮件/短信双通道统一入口)
        :param phone: 收件手机号
        :param code: 验证码
        :param ttl_minutes: 有效期(分钟), 模板需含 ${code} 变量; 有效期文案由短信模板自定
        :return: 是否发送成功
        """
        return await self._send(phone, {"code": code})

    async def send_notification(self, phone: str, title: str) -> bool:
        """发送通知短信(REQ-011 通知中心外部通道)
        :param phone: 收件手机号
        :param title: 通知标题(截取前 20 字作模板变量, 模板需含 ${title} 变量)
        :return: 是否发送成功(通知模板未配置时返回 False, 由通知服务降级站内)
        """
        cfg = await get_settings(SmsSettings)
        if not cfg.notify_template_code:
            logger.info("通知短信模板未配置(sms.notify_template_code 为空), 跳过通知短信")
            return False
        return await self._send(
            phone, {"title": title[:20]}, template_code=cfg.notify_template_code
        )


# 全局单例(无状态, 复用避免重复构造)
_sms_service = SmsService()


def get_sms_service() -> SmsService:
    """SmsService 依赖注入工厂(FastAPI Depends 使用)"""
    return _sms_service
