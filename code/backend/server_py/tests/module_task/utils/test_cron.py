"""module_task/utils/cron.py 单元测试: 5 字段 cron 解析与 next_fire 顺推

纯函数零外部依赖, 无需数据库/app 上下文
"""

from datetime import datetime

import pytest

from module_task.utils.cron import CRON_PRESETS, CronError, next_fire, parse_cron


# ==================== parse_cron 合法语法 ====================
def test_parse_wildcard_all_fields():
    mins, hours, days, months, dows = parse_cron("* * * * *")
    assert mins == set(range(60))
    assert hours == set(range(24))
    assert days == set(range(1, 32))
    assert months == set(range(1, 13))
    assert dows == set(range(1, 8))


def test_parse_step():
    mins, *_ = parse_cron("*/5 * * * *")
    assert mins == {0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}


def test_parse_exact_value():
    mins, hours, *_ = parse_cron("30 4 * * *")
    assert mins == {30}
    assert hours == {4}


def test_parse_range():
    mins, hours, *_ = parse_cron("10-20 8-18 * * *")
    assert mins == set(range(10, 21))
    assert hours == set(range(8, 19))


def test_parse_enum():
    mins, *_ = parse_cron("1,3,5 * * * *")
    assert mins == {1, 3, 5}


def test_parse_range_step_with_enum_combined():
    # 1-30/5 → {1,6,11,16,21,26}, 再并上枚举 40
    mins, *_ = parse_cron("1-30/5,40 * * * *")
    assert mins == {1, 6, 11, 16, 21, 26, 40}


def test_parse_single_value_with_step_expands_to_max():
    # 标准语义 "5/2" ≡ "5-59/2"
    mins, *_ = parse_cron("5/2 * * * *")
    assert mins == set(range(5, 60, 2))


def test_parse_week_zero_normalized_to_sunday():
    # 周字段 0 视为 7(周日)
    *_, dows = parse_cron("* * * * 0")
    assert dows == {7}


def test_parse_week_range_with_zero():
    *_, dows = parse_cron("* * * * 0-6")
    assert dows == {1, 2, 3, 4, 5, 6, 7}


# ==================== parse_cron 非法输入 ====================
@pytest.mark.parametrize(
    "expr",
    [
        "* * * *",            # 字段数不足
        "* * * * * *",        # 字段数超限
        "",                   # 空表达式
        "60 * * * *",         # 分钟越界
        "* 24 * * *",         # 小时越界
        "* * 32 * *",         # 日越界
        "* * * 13 *",         # 月越界
        "* * * * 8",          # 周越界(有效 1-7)
        "50-40 * * * *",      # 范围倒置
        "*/0 * * * *",        # 步进为 0
        "*/-1 * * * *",       # 步进为负
        "*/x * * * *",        # 步进非数字
        "a * * * *",          # 取值非法
        "1- * * * *",         # 范围缺右值
        "1,,2 * * * *",       # 枚举含空片段
    ],
)
def test_parse_invalid_expressions_raise(expr):
    with pytest.raises(CronError):
        parse_cron(expr)


def test_cron_error_is_value_error():
    # service 层按 ValueError 语义捕获转 400, 保证该继承关系不被破坏
    assert issubclass(CronError, ValueError)


# ==================== next_fire ====================
def test_next_fire_every_minute_strictly_after():
    after = datetime(2026, 10, 22, 10, 30, 30)
    result = next_fire("* * * * *", after)
    assert result == datetime(2026, 10, 22, 10, 31)
    assert result > after


def test_next_fire_step_minutes():
    after = datetime(2026, 10, 22, 10, 32)
    assert next_fire("*/5 * * * *", after) == datetime(2026, 10, 22, 10, 35)


def test_next_fire_exact_time_already_passed_moves_to_next_day():
    after = datetime(2026, 10, 22, 5, 0)  # 已过当天 04:00
    assert next_fire("0 4 * * *", after) == datetime(2026, 10, 23, 4, 0)


def test_next_fire_at_boundary_is_strictly_after():
    # 恰好命中触发时刻本身, 下一击应为下个周期(严格大于基准)
    after = datetime(2026, 10, 22, 4, 30, 0)
    assert next_fire("30 4 * * *", after) == datetime(2026, 10, 23, 4, 30)


def test_next_fire_weekly_dow_jump():
    # 2026-10-22 是周四, 下一个周一为 10-26
    after = datetime(2026, 10, 22, 12, 0)
    assert next_fire("0 4 * * 1", after) == datetime(2026, 10, 26, 4, 0)


def test_next_fire_month_and_day_jump_across_year():
    after = datetime(2026, 6, 1, 0, 0)
    assert next_fire("0 0 1 1 *", after) == datetime(2027, 1, 1, 0, 0)


def test_next_fire_impossible_date_raises():
    # 2 月 30 日不存在, 一年内无可命中时刻
    with pytest.raises(CronError):
        next_fire("0 0 30 2 *", datetime(2026, 1, 1))


def test_next_fire_invalid_expression_raises():
    with pytest.raises(CronError):
        next_fire("not a cron", datetime(2026, 1, 1))


def test_next_fire_result_seconds_truncated():
    after = datetime(2026, 10, 22, 10, 59, 59, 999999)
    result = next_fire("*/2 * * * *", after)
    assert result.second == 0
    assert result.microsecond == 0


# ==================== 预置表达式 ====================
@pytest.mark.parametrize("preset", list(CRON_PRESETS.values()))
def test_presets_all_parseable(preset):
    fields = parse_cron(preset)
    assert len(fields) == 5


def test_preset_daily_4am_next_fire():
    after = datetime(2026, 10, 22, 12, 0)
    assert next_fire(CRON_PRESETS["daily_4am"], after) == datetime(2026, 10, 23, 4, 0)
