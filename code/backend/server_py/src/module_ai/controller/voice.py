"""语音控制器(ASR/TTS): 模型能力全部通过外部服务接入

接口(路由前缀 /voice):
    - POST /asr         语音识别(音频上传)
          WS   /asr/stream  语音识别(麦克风实时流式)
    - POST /tts/file    语音合成(返回完整音频文件 wav)
          POST /tts/stream  语音合成(流式返回 PCM)

engine 参数可选：缺省时按模型配置(model_config 表 model_type=asr/tts)
自动选择方案(用户个人绑定优先)；旧值 dashscope/sherpa/qwen/local 自动归一化为 online。
具体业务逻辑见 module_ai/service/voice.py(VoiceService)。
"""
import logging
import time

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import StreamingResponse

from module_ai.config.server import module_app
from module_ai.dependencies.voice import get_voice_service
from module_ai.do.voice import ASRResponse, ASRStreamMessage, TTSRequest, VoiceEngine, resolve_engine
from module_ai.service.voice import VoiceService
from module_ai.utils.voice.audio import pcm_to_wav_bytes
from module_authorization.dependencies.auth import get_current_user_id_optional

logger = logging.getLogger(__name__)

router = APIRouter()


async def _ws_user_id(token: str | None) -> str | None:
    """WS 连接 query 参数 token -> 用户ID(可选登录; 缺失/无效按匿名处理走全局配置)"""
    if not token:
        return None
    try:
        # 延迟导入避免模块加载期耦合
        from module_authorization.dao.token import TokenDao
        from module_authorization.dao.user import UserDao
        from module_authorization.service.auth import AuthService
        from module_authorization.service.token import TokenService
        from module_authorization.service.user import UserService

        auth = AuthService(UserService(UserDao()), TokenService(TokenDao()))
        return await auth.get_current_user_id(token)
    except Exception as e:
        logger.warning(f"WS 连接令牌解析失败, 按匿名处理: {e}")
        return None


# ---------- 语音识别(ASR) ----------


@router.post(
    "/asr",
    response_model=ASRResponse,
    status_code=status.HTTP_200_OK,
    summary="语音识别(音频上传)",
    tags=["语音识别 ASR"],
)
async def asr_upload(
    audio: UploadFile,
    engine: str | None = Form(None, description="引擎方案 online(兼容旧值 dashscope/sherpa/qwen/local), 缺省按模型配置自动选择"),
    voice_service: VoiceService = Depends(get_voice_service),
    current_user_id: str | None = Depends(get_current_user_id_optional),
):
    """上传音频文件进行语音识别

    - **audio**: 音频文件(WAV/MP3 等可被解码格式)
    - **engine**: 引擎方案 online(缺省按用户绑定/模型配置自动选择)
    """
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "音频文件为空")
    resolved = resolve_engine(engine)
    start = time.time()
    text = await voice_service.asr(audio_bytes, resolved, user_id=current_user_id)
    return ASRResponse(
        text=text,
        engine=await voice_service.effective_engine("asr", resolved, current_user_id),
        elapsed=round(time.time() - start, 3),
    )


@router.websocket("/asr/stream")
async def asr_stream(ws: WebSocket):
    """麦克风实时流式语音识别

    协议：
    - 连接时通过 query 参数 engine 指定方案(online, 旧值自动归一化), 缺省按模型配置自动选择
    - 客户端发送二进制帧：16kHz 16bit 单声道 PCM
    - 客户端发送文本 "EOS" 表示结束
    - 服务端返回 JSON: ASRStreamMessage(text, is_final, engine)
    """
    engine = resolve_engine(ws.query_params.get("engine"))
    user_id = await _ws_user_id(ws.query_params.get("token"))

    await ws.accept()
    service = get_voice_service()
    # 先解析实际生效方案, 用于回显给客户端(恒为 online)
    effective = await service.effective_engine("asr", engine, user_id)
    try:
        session = await service.create_asr_stream(engine, user_id)
    except Exception as e:
        logger.error(f"ASR 流式会话创建失败: {e}")
        await _send_and_close(ws, f"引擎初始化失败: {e}", effective)
        return

    last_text = ""
    try:
        while True:
            msg = await ws.receive()
            if msg.get("text") is not None:
                if msg["text"].strip().upper() == "EOS":
                    final_text = await session.finish()
                    if not final_text:
                        final_text = last_text
                    await ws.send_text(
                        ASRStreamMessage(
                            text=final_text, is_final=True, engine=effective
                        ).model_dump_json()
                    )
                    break
                continue
            data = msg.get("bytes")
            if data:
                try:
                    await session.accept(data)
                    text = await session.result()
                    if text and text != last_text:
                        last_text = text
                        await ws.send_text(
                            ASRStreamMessage(
                                text=text, is_final=False, engine=effective
                            ).model_dump_json()
                        )
                except Exception as e:
                    logger.warning(f"流式 ASR 帧处理失败: {e}")
    except WebSocketDisconnect:
        logger.info("ASR 流式客户端断开")
    except Exception as e:
        logger.error(f"ASR 流式异常: {e}")
    finally:
        await session.close()
        try:
            await ws.close()
        except Exception:
            pass


async def _send_and_close(ws: WebSocket, text: str, engine) -> None:
    """发送错误消息并关闭连接(流式会话创建失败时)"""
    try:
        await ws.send_text(
            ASRStreamMessage(text=text, is_final=True, engine=engine or VoiceEngine.ONLINE).model_dump_json()
        )
        await ws.close()
    except Exception:
        pass


# ---------- 语音合成(TTS) ----------


@router.post(
    "/tts/file",
    summary="语音合成(返回完整音频文件)",
    tags=["语音合成 TTS"],
)
async def tts_file(
    req: TTSRequest,
    voice_service: VoiceService = Depends(get_voice_service),
    current_user_id: str | None = Depends(get_current_user_id_optional),
):
    """文本合成语音，返回完整 WAV 音频文件

    - **text**: 待合成文本
    - **engine**: 引擎方案 online(兼容旧值 dashscope/sherpa/qwen/local, 缺省按用户绑定/模型配置自动选择)
    """
    if not req.text.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "文本内容为空")
    pcm, sr = await voice_service.tts(
        req.text,
        resolve_engine(req.engine),
        req.speaker,
        req.speed,
        req.sample_rate,
        user_id=current_user_id,
    )

    wav_bytes = pcm_to_wav_bytes(pcm, sr)
    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={
            "Content-Disposition": "attachment; filename=tts.wav",
            "X-Sample-Rate": str(sr),
        },
    )


@router.post(
    "/tts/stream",
    summary="语音合成(流式返回 PCM)",
    tags=["语音合成 TTS"],
)
async def tts_stream(
    req: TTSRequest,
    voice_service: VoiceService = Depends(get_voice_service),
    current_user_id: str | None = Depends(get_current_user_id_optional),
):
    """文本合成语音，流式返回裸 PCM(16bit 单声道)

    通过响应头 X-Sample-Rate 返回采样率，客户端可边收边播。
    online 方案(dashscope 协议)走 CosyVoice 流式 WebSocket 真流式; 其余回退同步切片路径。
    - **text**: 待合成文本
    - **engine**: 引擎方案 online(兼容旧值 dashscope/sherpa/qwen/local, 缺省按用户绑定/模型配置自动选择)
    """
    if not req.text.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "文本内容为空")

    # 先解析引擎与实际生效方案(生成器内不能 await; 失败由全局异常处理器统一返回)
    iterator, effective, is_async = await voice_service.tts_stream_async(
        req.text, resolve_engine(req.engine), req.speaker, req.speed, req.sample_rate,
        user_id=current_user_id,
    )

    if is_async:
        async def agen_async():
            """异步生成器: 真流式逐块产出 PCM(引擎已在上方解析)"""
            try:
                async for chunk, sr, _is_final in iterator:
                    yield chunk
            except Exception as e:
                logger.error(f"TTS 流式合成失败: {e}")
                return

        return StreamingResponse(
            agen_async(),
            media_type="audio/pcm",
            headers={
                "X-Sample-Rate": str(req.sample_rate),
                "X-Engine": effective.value,
            },
        )

    def agen():
        """同步生成器: 逐块产出 PCM(引擎已在上方解析)"""
        try:
            for chunk, sr, is_final in iterator:
                yield chunk
        except Exception as e:
            logger.error(f"TTS 流式合成失败: {e}")
            return

    return StreamingResponse(
        agen(),
        media_type="audio/pcm",
        headers={
            "X-Sample-Rate": str(req.sample_rate),
            "X-Engine": effective.value,
        },
    )


# 将路由注册到模块应用
module_app.include_router(router, prefix="/voice")
