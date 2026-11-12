"""内置只读技能包(REQ-013 → REQ-018 Manifest 化迁移)

四个技能(网络搜索/图片OCR/文件检索/知识库问答)由旧 SkillDef 迁移为 Manifest 声明:
- 实现签名统一为 run(input, ctx, caps, progress) -> dict(三入口共用, CA-04)
- 对话场景由 Tool Adapter(skills/adapter.py)转为 LLM 工具, dict 结果序列化为文本
"""

from module_agent.skills.builtin import (  # noqa: F401 (导入即注册)
    file_search,
    ocr_image,
    rag_qa,
    web_search,
)
