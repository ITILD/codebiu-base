"""图像生成引擎抽象接口"""

from abc import ABC, abstractmethod


class ImageGenerator(ABC):
    """文生图/图生图抽象接口

    统一约定:
        - 不传 image: 文生图(T2I); 传 image: 图生图/图像编辑(I2I, 参考图支持 data URL 或 http URL)
        - `agenerate` 返回 [{url, revised_prompt}], 顺序与请求一致
        - 图片 URL 通常为临时地址(约 24 小时), 仅用于即时展示/试听, 需长期保存请调用方及时转存
    """

    engine_name: str = "image"

    @abstractmethod
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
        """异步生成图像, 返回图片列表 [{url, revised_prompt}]

        :param prompt: 提示词(图生图时为编辑指令)
        :param image: 参考图(data URL 或 http URL), 传入即走图生图
        :param size: 输出尺寸(宽*高, 如 1024*1024; 缺省由模型按提示词推荐)
        :param n: 生成张数(1~4, None 时取配置默认值)
        :param negative_prompt: 反向提示词
        :param seed: 随机种子(相同种子+参数结果可复现)
        :param prompt_extend: 是否开启提示词智能改写
        :param watermark: 是否添加水印
        """
        ...
