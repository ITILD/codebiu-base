"""AI 模型接入模块 llm 接口层: 参数校验并调度 service"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, UploadFile

# from fastapi.responses import StreamingResponse
from module_ai.dependencies.llm import LLMService, get_llm_service
from module_ai.do.llm import (
    ChatRequest,
    EmbeddingRequest,
    CacheClearRequest,
    ImageGenerateRequest,
    ImageGenerateResponse,
    ImageTestRequest,
    ModelConfigCheckResponse,
    ModelCustomTestRequest,
    ModelCustomTestResponse,
    ModelTestRequest,
    ModelTestResponse,
    RerankRequest,
    RerankResponse,
    TokenCountRequest,
    TokenCountResponse,
    TtsTestRequest,
)
from common.utils.fastapi_ex.exceptions import BusinessError
from module_ai.config.server import module_app
from module_ai.do.model_config import ModelConfigCreateRequest
from module_ai.utils.llm.token.tokenizer import Tokenizer
from sse_starlette import EventSourceResponse, ServerSentEvent
from module_ai.utils.llm.stream.sse import agui_event_generator, event_generator

import logging


logger = logging.getLogger(__name__)

router = APIRouter()

# token 计数器单例(tiktoken 编码按名称缓存, 非开盘重复加载)
_tokenizer = Tokenizer()



@router.post("/check-config", summary="配置校验")
async def check_config(
    model_config: ModelConfigCreateRequest,
    llm_service: LLMService = Depends(get_llm_service),
) -> ModelConfigCheckResponse:
    """
    校验模型配置是否有效

    - **model_config**: 模型配置对象，包含模型类型、服务类型、URL、API密钥等信息
    """
    result: ModelConfigCheckResponse = await llm_service.check_config(model_config)
    return result


@router.post("/check-config-by-model-id", summary="配置校验")
async def check_config_by_model_id(
    model_id: str,
    llm_service: LLMService = Depends(get_llm_service),
):
    """
    校验模型配置是否有效

    - **model_id**: 模型配置ID或模型标识名称
    """
    result: bool = await llm_service.check_config_by_model_id(model_id)
    return {"message": "配置校验通过" if result else "配置校验失败:智能程度低"}


@router.post("/test-by-model-id", summary="模型能力测试")
async def test_by_model_id(
    request: ModelTestRequest,
    llm_service: LLMService = Depends(get_llm_service),
) -> ModelTestResponse:
    """
    按模型配置ID运行能力测试(问答/结构化/多模态/向量化/重排), 结果持久化到
    model_config.check_result, 供前端能力标签常驻展示

    - **model_id**: 模型配置ID
    - **capability**: 可选, 仅测试指定能力(缺省测试该类型全部能力)
    """
    try:
        return await llm_service.test_and_persist(request.model_id, request.capability)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/test-custom", summary="模型单独测试(自定义参数)")
async def test_custom(
    request: ModelCustomTestRequest,
    llm_service: LLMService = Depends(get_llm_service),
) -> ModelCustomTestResponse:
    """按模型配置ID用自定义参数做单次真实调用(chat 问答/向量化/重排打分)

    - **model_id**: 模型配置ID
    - **question**: chat 自定义提问
    - **text**: embeddings 待向量化文本
    - **query** + **documents**: rerank 检索与候选文档
    """
    try:
        return await llm_service.run_custom_test(
            request.model_id,
            question=request.question,
            text=request.text,
            query=request.query,
            documents=request.documents,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/test-tts", summary="TTS 单独测试(文本合成语音)")
async def test_tts(
    request: TtsTestRequest,
    llm_service: LLMService = Depends(get_llm_service),
):
    """按指定 TTS 模型配置把自定义文本合成语音, 直接返回 WAV 音频(试听)

    - **model_id**: 模型配置ID
    - **text**: 待合成文本
    - **speed**: 语速(0.5~2.0)
    """
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="请输入待合成文本")
    try:
        wav_bytes, sr = await llm_service.tts_test(request.model_id, request.text.strip(), request.speed)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"TTS 单独测试失败: {e}")
        raise HTTPException(status_code=500, detail=f"合成失败: {str(e)[:300]}")
    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={"X-Sample-Rate": str(sr)},
    )


@router.post("/test-asr", summary="ASR 单独测试(音频识别)")
async def test_asr(
    model_id: str = Form(..., description="模型配置ID"),
    audio: UploadFile = Form(..., description="音频文件(WAV/MP3 等)"),
    llm_service: LLMService = Depends(get_llm_service),
):
    """按指定 ASR 模型配置识别上传音频, 返回识别文本"""
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="音频文件为空")
    try:
        text = await llm_service.asr_test(model_id, audio_bytes)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"ASR 单独测试失败: {e}")
        raise HTTPException(status_code=500, detail=f"识别失败: {str(e)[:300]}")
    return {"ok": True, "text": text or "(无识别结果)"}


@router.post("/test-ocr", summary="OCR 单独测试(图片识别)")
async def test_ocr(
    model_id: str = Form(..., description="模型配置ID"),
    image: UploadFile = Form(..., description="图片文件"),
    llm_service: LLMService = Depends(get_llm_service),
):
    """按指定 OCR 模型配置识别上传图片, 返回识别文本行"""
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="图片文件为空")
    try:
        result = await llm_service.ocr_test(model_id, image_bytes)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"OCR 单独测试失败: {e}")
        raise HTTPException(status_code=500, detail=f"识别失败: {str(e)[:300]}")
    return {"ok": True, **result}


@router.post("/image", response_model=ImageGenerateResponse, summary="图像生成(文生图/图生图)")
async def generate_image(
    request: ImageGenerateRequest,
    llm_service: LLMService = Depends(get_llm_service),
) -> ImageGenerateResponse:
    """按模型配置生成图像(百炼 qwen-image 系列 / OpenAI 兼容生图服务)

    - **prompt**: 提示词(图生图时为编辑指令)
    - **image**: 参考图(data URL / base64 / http URL), 传入即走图生图(图像编辑)
    - **size**: 输出尺寸(宽*高, 缺省由模型按提示词推荐)
    - **model_id**: 模型配置ID(缺省取 image 类型默认配置)
    """
    try:
        return await llm_service.generate_image(request)
    except BusinessError as e:
        # 参考图超限/压缩失败等输入问题: 400 便于前端直接提示用户
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"图像生成失败: {e}")
        raise HTTPException(status_code=500, detail=f"图像生成失败: {str(e)[:300]}")


@router.post("/test-image", response_model=ImageGenerateResponse, summary="生图单独测试")
async def test_image(
    request: ImageTestRequest,
    llm_service: LLMService = Depends(get_llm_service),
) -> ImageGenerateResponse:
    """按指定模型配置生成图片(模型配置页单独测试, 失败以 ok=False 返回)

    - **model_id**: 模型配置ID
    - **prompt**: 提示词
    - **image**: 参考图(data URL / base64 / http URL), 传入即为图生图
    """
    try:
        return await llm_service.image_test(request)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/rerank", response_model=RerankResponse, summary="文本重排序")
async def rerank_documents(
    request: RerankRequest,
    llm_service: LLMService = Depends(get_llm_service),
) -> RerankResponse:
    """对文档列表按查询相关性重排序(与生图/对话同属 llm 能力线)

    - **query**: 检索查询文本
    - **documents**: 待排序文档(字符串或含 sort_key 字段的字典)
    - **model_id**: 模型配置(缺省取 rerank 类型默认配置)
    """
    return await llm_service.rerank(request)


@router.post("/chat", summary="聊天接口 支持流式SSE(legacy/agui 双协议)")
async def chat_completion(
    chat_http_request: Request,
    request: ChatRequest, llm_service: LLMService = Depends(get_llm_service)
):
    """
    聊天完成接口(直连 LLM, 无 RAG/图编排)

    协议定位:
    - **event_protocol=agui**(推荐): AG-UI 标准事件流(官方 SDK ag-ui-protocol,
      正文 TEXT_MESSAGE_* / 推理 REASONING_*), 供前端聊天页等标准客户端消费
    - **event_protocol=legacy**(默认): 旧 StreamChunkResponse 协议,
      定位为简单 AI 问答工具接口(外部脚本/调试直连场景), 不含过程事件语义

    - **model_id**: 模型配置ID或模型标识名称
    - **messages**: 消息内容，可以是字符串或消息列表
    - **streaming**: 是否启用流式响应 返回SSE事件流
    - **event_protocol**: 流式事件协议 legacy(默认) | agui
    """
    try:
        # 调用LLM服务
        responses = await llm_service.chat_completion(request)
        if request.streaming:
            # 流式响应SSE事件流
            if request.event_protocol == "agui":
                return EventSourceResponse(
                    agui_event_generator(
                        responses, chat_http_request, raw_llm_chunks=True
                    ),
                    media_type="text/event-stream",
                )
            return EventSourceResponse(
                event_generator(responses, chat_http_request), media_type="text/event-stream"
            )
        else:
            # 非流式响应
            return responses
    except BusinessError as e:
        # 输入超限等可执行提示: 400 而非 500, 前端直接展示文案
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"聊天完成接口失败: {e}")
        raise HTTPException(status_code=500, detail=f"模型调用失败: {str(e)}")


@router.delete("/cache/{model_id}", summary="清除模型缓存")
async def _test_cache_clear(
    model_id: str, llm_service: LLMService = Depends(get_llm_service)
):
    """
    按 model_id 前缀匹配清除已缓存的模型实例，使下次请求重新加载模型；model_id 为空时清空全部模型缓存

    - **model_id**: 模型配置ID或模型标识名称，为空则清除所有缓存
    """
    llm_service.clear_cache(model_id)
    if model_id:
        return {"message": f"模型 {model_id} 缓存已清除"}
    else:
        return {"message": "所有模型缓存已清除"}


@router.post("/token-count", summary="token 计数", response_model=TokenCountResponse)
async def token_count(
    request: TokenCountRequest,
    llm_service: LLMService = Depends(get_llm_service),
) -> TokenCountResponse:
    """批量统计文本 token 数(前端 AI 对话的输入/输出/上下文统计用)

    计数口径与后端上下文预算/消息裁剪一致(tiktoken, 非 OpenAI 系模型
    回退 o200k_base 编码近似估算)。

    - **texts**: 待计数的文本列表(批量, 顺序与返回 counts 一一对应)
    - **model_id**: 可选模型配置ID, 传入时同时返回该模型输入上限与剩余量
    """
    counts = [
        _tokenizer.count_tokens(text, "qwen-plus")[0]
        for text in request.texts
    ]
    total = sum(counts)
    limit = None
    remaining = None
    if request.model_id:
        limit, _model = await llm_service.input_token_limit(request.model_id)
        if limit:
            remaining = max(0, limit - total)
    return TokenCountResponse(
        counts=counts,
        total=total,
        limit=limit or None,
        remaining=remaining,
        exceeded=bool(limit and total > limit),
    )


@router.get("/input-limit", summary="查询对话模型输入上限")
async def get_input_limit(
    model_id: str | None = None,
    llm_service: LLMService = Depends(get_llm_service),
) -> dict:
    """返回对话模型的输入 token 上限(前端展示"已输入/限制"的初始值)

    - **model_id**: 模型配置ID(缺省取全局默认 chat 配置)
    """
    limit, model = await llm_service.input_token_limit(model_id)
    return {"limit": limit, "model": model, "unit": "token"}


# 将路由注册到模块应用
module_app.include_router(router, prefix="/llm", tags=["模型基础调用"])
