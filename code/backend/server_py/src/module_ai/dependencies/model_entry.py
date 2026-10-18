"""AI 模型接入模块 model_entry FastAPI 依赖注入"""

from module_ai.service.model_entry import ModelEntryService, get_model_entry

# 全局单例(统一模型入口: 引擎实例缓存由 model_entry 模块维护)


def get_model_entry_service() -> ModelEntryService:
    """获取统一模型入口服务单例(FastAPI 依赖注入用)"""
    return get_model_entry()
