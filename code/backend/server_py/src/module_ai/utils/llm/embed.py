"""向量化并发分批工具(入库效率优化)

背景: langchain OpenAIEmbeddings.aembed_documents 对多文本按 chunk_size 串行分批,
每个批次的网络请求依次等待 —— 文档入库时几百个分块的向量化耗时 ≈ 批次数 × 单次 RTT。

此处提供并发分批封装: 小批(单请求条数受服务端限制, dashscope text-embedding-v3 上限 10)
+ asyncio.gather 并发(信号量限流), 网络 IO 重叠后总耗时 ≈ 批次数 / 并发度 × 单次 RTT。
"""

import asyncio

from langchain_core.embeddings import Embeddings

# 单请求文本条数上限(对齐 dashscope text-embedding-v3 的批量限制, 通用安全值)
DEFAULT_BATCH_SIZE = 10
# 并发请求数(服务端限流友好, 网络 IO 主导时已足够重叠)
DEFAULT_CONCURRENCY = 8


async def embed_documents_concurrent(
    embeddings: Embeddings,
    texts: list[str],
    batch_size: int = DEFAULT_BATCH_SIZE,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> list[list[float]]:
    """并发分批向量化文本列表, 返回与输入同序的向量列表

    :param embeddings: langchain Embeddings 实例
    :param texts: 待向量化文本列表
    :param batch_size: 每次请求的文本条数
    :param concurrency: 最大并发请求数
    :raises Exception: 任一批次失败时立即抛出(gather 默认传播首个异常)
    """
    if not texts:
        return []

    batches = [texts[i : i + batch_size] for i in range(0, len(texts), batch_size)]
    semaphore = asyncio.Semaphore(concurrency)

    async def _run(batch: list[str]) -> list[list[float]]:
        async with semaphore:
            return await embeddings.aembed_documents(batch)

    # gather 保序: results[i] 与 batches[i] 对应, 摊平后与 texts 同序
    results = await asyncio.gather(*(_run(batch) for batch in batches))
    return [vec for batch in results for vec in batch]
