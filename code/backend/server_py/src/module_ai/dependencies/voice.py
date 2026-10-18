"""AI 模型接入模块 voice FastAPI 依赖注入"""

from module_ai.service.voice import VoiceService

# 全局单例(在线引擎按模型配置缓存, 配置变更自动重建)
voice_service = VoiceService()


def get_voice_service() -> VoiceService:
    """获取语音服务单例"""
    return voice_service
