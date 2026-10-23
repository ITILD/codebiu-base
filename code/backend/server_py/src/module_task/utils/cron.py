"""
标准 5 字段 cron 表达式解析(分钟级精度, 零依赖自研)

支持语法(每字段):
    *        任意值
    */n      步进(每 n 个单位)
    a        精确值
    a-b      范围
    a,b,c    枚举(可与范围/步进组合, 如 1-30/5,10,40)
字段顺序: 分 时 日 月 周(1=周一...7=周日, 0 视为 7)

设计取舍:
    - 不引入 croniter/APScheduler, 控制依赖体积(基线零新增依赖)
    - 分钟级精度已覆盖数据清理/同步/周期报表场景; next_fire 顺推法
      最坏 366 天内必命中(日/月/周组合不存在时按标准 cron 语义跳到可命中日)
"""
from datetime import datetime, timedelta

# 各字段(分钟 小时 日 月 周)取值区间; 周字段 0(周日)归一化为 7
_FIELD_RANGES = [
    (0, 59),  # 分钟
    (0, 23),  # 小时
    (1, 31),  # 日
    (1, 12),  # 月
    (1, 7),   # 周(1=周一 ... 7=周日)
]


class CronError(ValueError):
    """cron 表达式非法(创建/修改调度时由 service 层转为 400)"""


def _parse_field(field: str, idx: int) -> set[int]:
    """
    解析单个字段为允许值集合
    :param field: 字段原文(如 "*/5" "1-30/5,40" "0")
    :param idx: 字段下标(0分/1时/2日/3月/4周)
    :raises CronError: 语法或取值非法
    """
    lo, hi = _FIELD_RANGES[idx]
    allowed: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            raise CronError(f"cron 字段含空片段: {field!r}")
        # 步进: "*/n" "a-b/n" "a/n"(标准语义 a/n ≡ a-上限/n)
        step = 1
        has_step = "/" in part
        if has_step:
            base, _, step_s = part.partition("/")
            if not step_s.isdigit() or int(step_s) < 1:
                raise CronError(f"cron 步进非法: {part!r}(应为正整数)")
            step = int(step_s)
        else:
            base = part
        # 范围/单值: * 展开为全区间
        if base == "*":
            start, end = lo, hi
        elif base.isdigit():
            start = end = int(base)
            if has_step:
                end = hi  # "5/2" ≡ "5-59/2"
        elif "-" in base:
            a, _, b = base.partition("-")
            if not (a.isdigit() and b.isdigit()):
                raise CronError(f"cron 范围非法: {base!r}")
            start, end = int(a), int(b)
        else:
            raise CronError(f"cron 取值非法: {base!r}")
        if idx == 4:  # 周字段 0 归一化为 7(周日)
            start, end = (7 if v == 0 else v for v in (start, end))
        if not (lo <= start <= hi and lo <= end <= hi):
            raise CronError(f"cron 取值越界: {part!r}(允许 {lo}-{hi})")
        if start > end:
            if idx == 4:
                # 周字段环绕: "0-6"归一化为 7-6, 标准语义为周日..周六(整周),
                # 按环绕顺序 7,1,2,...,end 展开并保留步进语义
                seq = list(range(start, 8)) + list(range(1, end + 1))
                allowed.update(seq[::step])
                continue
            raise CronError(f"cron 范围倒置: {part!r}")
        allowed.update(range(start, end + 1, step))
    if not allowed:
        raise CronError(f"cron 字段无有效取值: {field!r}")
    return allowed


def parse_cron(expr: str) -> tuple[set[int], set[int], set[int], set[int], set[int]]:
    """
    解析完整表达式
    :param expr: 5 字段 cron(空格分隔)
    :return: (分钟集, 小时集, 日集, 月集, 周集)
    :raises CronError: 字段数不是 5 或任一字段非法
    """
    fields = expr.split()
    if len(fields) != 5:
        raise CronError(f"cron 须为 5 字段(分 时 日 月 周): {expr!r}")
    return tuple(_parse_field(f, i) for i, f in enumerate(fields))  # type: ignore[return-value]


# 预置常用表达式(创建调度时前端快捷选项)
CRON_PRESETS = {
    "every_minute": "* * * * *",
    "hourly": "0 * * * *",
    "daily_4am": "0 4 * * *",
    "weekly_mon_4am": "0 4 * * 1",
    "monthly_1st_4am": "0 4 1 * *",
}


def next_fire(expr: str, after: datetime) -> datetime:
    """
    计算严格晚于 after 的下一次触发时刻(分钟对齐顺推)
    :param expr: 5 字段 cron 表达式
    :param after: 基准时刻(含秒, 返回值秒/微秒清零且必然 > after)
    :return: 下次触发时刻
    :raises CronError: 表达式非法; 或顺推一年仍无可命中时刻(如 2 月 30 日)
    """
    mins, hours, days, months, dows = parse_cron(expr)
    # 从 after 的下一分钟对齐开始顺推(丢弃秒)
    candidate = (after + timedelta(minutes=1)).replace(second=0, microsecond=0)
    limit = candidate + timedelta(days=366)  # 最坏一年内必命中或判定无解
    while candidate <= limit:
        if (
            candidate.minute in mins
            and candidate.hour in hours
            and candidate.day in days
            and candidate.month in months
            and candidate.isoweekday() in dows
        ):
            return candidate
        # 不可能命中的维度直接跳跃, 避免逐分钟空转(月/时 → 时 → 分 → 日)
        if candidate.month not in months or candidate.hour not in hours:
            candidate = candidate.replace(minute=0) + timedelta(hours=1)
        elif candidate.minute not in mins:
            later = [m for m in mins if m > candidate.minute]
            if later:
                candidate = candidate.replace(minute=min(later))
            else:
                candidate = candidate.replace(minute=0) + timedelta(hours=1)
        elif candidate.day not in days or candidate.isoweekday() not in dows:
            candidate = candidate.replace(minute=0, hour=0) + timedelta(days=1)
        else:
            candidate += timedelta(minutes=1)
    raise CronError(f"cron 表达式一年内无可命中时刻(如 2 月 30 日): {expr!r}")
