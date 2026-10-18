"""token 计数(仅 tiktoken, 不依赖 transformers 等重型库)

非 OpenAI 系模型统一回退到 o200k_base 编码做近似估算, 足以满足
消息裁剪/上下文预算等场景的 token 预算需求。
"""
import tiktoken


class Tokenizer:
    # 模型到 tiktoken 编码的映射
    TIKTOKEN_MODELS = {
        "gpt-3.5-turbo": "cl100k_base",
        "gpt-4-turbo": "cl100k_base",
        "gpt-4o": "o200k_base",
        "gpt-4o-mini": "o200k_base",
        "gpt-4": "cl100k_base",
    }
    # 未识别模型的回退编码
    FALLBACK_ENCODING = "o200k_base"

    def __init__(self, cache_dir: str | None = None):
        self._tiktoken_encodings: dict[str, tiktoken.Encoding] = {}

    def _get_tiktoken_encoding(self, encoding_name: str) -> tiktoken.Encoding:
        if encoding_name not in self._tiktoken_encodings:
            self._tiktoken_encodings[encoding_name] = tiktoken.get_encoding(
                encoding_name
            )
        return self._tiktoken_encodings[encoding_name]

    def _resolve_encoding(self, model_name: str) -> tiktoken.Encoding:
        """按模型名解析编码(未识别模型回退 o200k_base 近似估算)"""
        model_lower = model_name.lower()
        for key, encoding in self.TIKTOKEN_MODELS.items():
            if key in model_lower:
                return self._get_tiktoken_encoding(encoding)
        return self._get_tiktoken_encoding(self.FALLBACK_ENCODING)

    def count_tokens(self, text: str, model_name: str) -> tuple[int, list[int]]:
        """统计文本 token 数
        :param text: 待统计文本
        :param model_name: 模型名(仅用于选择 tiktoken 编码)
        :return: (token 数量, token id 列表)
        """
        enc = self._resolve_encoding(model_name)
        tokens = enc.encode(text)
        return len(tokens), tokens

    def text_tokens(self, text: str, model_name: str) -> list[str]:
        """返回可读的 token 文本列表"""
        enc = self._resolve_encoding(model_name)
        tokens = enc.encode(text)
        decoded = []
        for t in tokens:
            try:
                # 尝试 UTF-8 解码，失败则保留 repr
                token_bytes = enc.decode_single_token_bytes(t)
                decoded.append(token_bytes.decode("utf-8", errors="replace"))
            except Exception:
                decoded.append(f"<{t}>")
        return decoded


# === 使用示例 ===
if __name__ == "__main__":
    tokenizer = Tokenizer()
    text = "token number test,hello world,你好世界,こんにちは"

    for model in ["gpt-3.5-turbo", "gpt-4o", "qwen-plus"]:
        try:
            count, ids = tokenizer.count_tokens(text, model)
            tokens_text = tokenizer.text_tokens(text, model)
            print(f"\n=== [{model}] ===")
            print(f"Token 数量: {count}")
            print(f"Token IDs: {ids}")
            print(f"可读 tokens: {tokens_text}")
        except Exception as e:
            print(f"[{model}] error: {e}")
