"""OpenAI 兼容图像生成实现(百炼 qwen-image 系列走兼容模式, 协议一致)

请求: POST {base_url}/images/generations
    {model, prompt, image?(参考图, 传入即图生图), size?, n?, negative_prompt?,
     seed?, prompt_extend?, watermark?}
响应: {"data": [{"url": "...", "revised_prompt": "..."}]}(部分实现返回 b64_json)
"""

import json

import aiohttp

from module_ai.utils.llm.image.interface import ImageGenerator

# 生图耗时显著高于文本(单张常 10~60s), 超时留足余量
_DEFAULT_TIMEOUT = 180


class OpenAIImage(ImageGenerator):
    """OpenAI 兼容协议生图引擎(文生图/图生图)

    配置默认参数(extra.size/n/negative_prompt/seed/prompt_extend/watermark)在
    构造时注入 defaults, 单次调用入参优先于默认值。
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        timeout: float = _DEFAULT_TIMEOUT,
        defaults: dict | None = None,
        engine_name: str = "image",
    ):
        """构造生图引擎

        :param api_key: 服务密钥
        :param model: 模型名称(如 qwen-image-3.0)
        :param base_url: OpenAI 兼容根地址(不含 /images/generations)
        :param timeout: 单次请求超时(秒)
        :param defaults: 配置层默认参数(见类说明)
        :param engine_name: 引擎标识(前端能力标签回显)
        """
        self.api_key = api_key
        self.model = model
        self.base_url = (base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1").strip().rstrip("/")
        self.timeout = timeout
        self.defaults = defaults or {}
        self.engine_name = engine_name

    @property
    def endpoint(self) -> str:
        """生图接口地址"""
        return f"{self.base_url}/images/generations"

    def _build_payload(
        self,
        prompt: str,
        *,
        image: str | None = None,
        size: str | None = None,
        n: int | None = None,
        negative_prompt: str | None = None,
        seed: int | None = None,
        prompt_extend: bool | None = None,
        watermark: bool | None = None,
    ) -> dict:
        """组装请求体: 显式入参优先, 缺省回退配置默认值, 空值不下发"""
        defaults = self.defaults
        payload: dict = {"model": self.model, "prompt": prompt}
        if image:
            payload["image"] = image
        # 尺寸统一为 "<宽>x<高>"(兼容调用方传入的 "*" 分隔写法)
        raw_size = size if size is not None else defaults.get("size")
        # n 未指定(None)时才回退配置默认张数, 显式传 1 照常下发
        resolved = {
            "size": str(raw_size).replace("*", "x") if raw_size else None,
            "n": n if n is not None else defaults.get("n", 1),
            "negative_prompt": negative_prompt if negative_prompt is not None else defaults.get("negative_prompt"),
            "seed": seed if seed is not None else defaults.get("seed"),
            "prompt_extend": prompt_extend if prompt_extend is not None else defaults.get("prompt_extend"),
            "watermark": watermark if watermark is not None else defaults.get("watermark"),
        }
        for key, value in resolved.items():
            if value is not None:
                payload[key] = value
        return payload

    @staticmethod
    def _parse_result(data: dict) -> list[dict]:
        """解析响应: 优先 url, 兼容 b64_json 转 data URL"""
        results: list[dict] = []
        for item in data.get("data") or []:
            url = item.get("url") or ""
            if not url and item.get("b64_json"):
                url = "data:image/png;base64," + str(item["b64_json"])
            if url:
                results.append(
                    {"url": url, "revised_prompt": item.get("revised_prompt") or ""}
                )
        return results

    async def agenerate(
        self,
        prompt: str,
        *,
        image: str | None = None,
        size: str | None = None,
        n: int | None = None,
        negative_prompt: str | None = None,
        seed: int | None = None,
        prompt_extend: bool | None = None,
        watermark: bool | None = None,
    ) -> list[dict]:
        """调用 /images/generations 生成图片(传入 image 即为图生图)"""
        payload = self._build_payload(
            prompt,
            image=image,
            size=size,
            n=n,
            negative_prompt=negative_prompt,
            seed=seed,
            prompt_extend=prompt_extend,
            watermark=watermark,
        )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(self.endpoint, headers=headers, json=payload) as response:
                body = await response.text()
                if response.status >= 400:
                    raise RuntimeError(
                        f"图像生成请求失败({response.status}): {body[:500]}"
                    )
        results = self._parse_result(json.loads(body))
        if not results:
            raise RuntimeError(f"图像生成结果为空: {body[:300]}")
        return results
