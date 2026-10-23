"""
module_contact 字典种子声明(通知类型字典)

字典项编码从模块代码常量 NOTIFY_TYPES(do/notification.py)派生,
保证字典与代码取值一致,不产生两处维护的漂移问题。

启动时由 module_main/config/dict_seed.py 的 ensure_default_dicts 统一批量幂等同步到 dict_type/dict_item 表。
"""
from module_contact.do.notification import NOTIFY_TYPES
from module_main.config.dict_seed import DictTypeSeed, DictItemSeed, dict_seed_registry

# 注册: 通知类型(与 NOTIFY_TYPES 对齐)
dict_seed_registry.register(
    DictTypeSeed(
        type_code="contact_notify_type",
        type_name="通知类型",
        description="通知中心的通知类型编码(埋点/订阅矩阵共用)",
        sort_order=1,
        items=[
            DictItemSeed(item_code=t["type_code"], item_name=t["type_name"], description=t.get("description"))
            for t in NOTIFY_TYPES
        ],
    )
)
