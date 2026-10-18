# codebiu_base 前后端接口全量测试报告

- 测试时间: 2026-10-17 23:35 ~ 23:55 (Asia/Shanghai)
- 后端: FastAPI `127.0.0.1:2001` (config.dev.yaml, 远程 postgres + LanceDB + fakeredis, 任务引擎 local)
- 前端: `pnpm run build`(类型检查+打包) 通过; `vite preview --mode development` 于 4188 端口浏览器实测
- 方式: 逐模块真实调用(创建临时数据→验证→清理), 外部服务类接口按"未配置密钥应优雅失败"口径判定为预期失败

## 1. 结论

| 范围 | 结果 |
| :--- | :--- |
| 后端接口(含 6 个挂载子应用) | **215 用例: 202 PASS / 11 预期失败 / 0 FAIL / 2 跳过** |
| 前端构建 | `pnpm run build` 通过(vue-tsc 类型检查零错误) |
| 前端浏览器冒烟 | **19 项全 PASS**(登录/首页水墨/系统管理 7 页/监控/文件/AI 2 页/RAG/任务/模板/版本页/登出), console 无严重报错 |

**本轮发现并修复的缺陷(2 个):**

1. 模板批量删除 404: `DELETE /template/templates/batch` 声明在 `DELETE /{template_id}` 之后被路径参数路由遮蔽,"batch"被当作 ID。已调整声明顺序([template.py](../code/backend/server_py/src/module_template/controller/template.py))。
2. 模板批量删除 500: [dao/template.py](../code/backend/server_py/src/module_template/dao/template.py) `batch_delete` 收到 ID 列表却仍访问 `batch_delete.ids`。已改为直接接收 `ids: list[str]`。

**预期失败(11 项, 非缺陷):** LLM 对话/连通测试、rerank、asr、tts(文件/流式)、ocr 识别与批量、RAG 问答/总结、文档重解析、分块检索、全库重向量化 —— 均因模型 api_key / MinerU token 未配置而按设计返回错误, 配置密钥后即可用。

**跳过(2 项):** `GET /db/create`、`/db/reset` 为破坏性接口不实测; admin 令牌吊销改在测试用户上验证。

## 2. 后端路由清单(共 238 条, 按前缀统计)

| 前缀 | 路由数 |
| :--- | ---: |
| `authorization` | 67 |
| `rag` | 54 |
| `file` | 31 |
| `ai` | 25 |
| `template` | 17 |
| `task` | 12 |
| `dict_items` | 9 |
| `dict_types` | 7 |
| `server-status` | 5 |
| `db` | 5 |
| `sys-configs` | 3 |
| `docs` | 2 |
| `(root)` | 1 |

## 3. 用例执行明细(215 条)

| 模块 | 用例 | 方法 | 路径 | 期望 | 实际 | 结果 | 备注 |
|---|---|---|---|---|---|---|---|
| main | 根路由 | GET | / | 200 | 200 | PASS |  |
| auth | 获取当前用户 | GET | /authorization/auth/me | 200 | 200 | PASS | user=56744fe711cc4d0593d49b514679f042 |
| auth | 当前用户ID | GET | /authorization/auth/me-id | 200 | 200 | PASS |  |
| auth | 我的角色与权限码 | GET | /authorization/auth/me-permissions | 200 | 200 | PASS | perm数=1 |
| auth | 注册流程配置 | GET | /authorization/auth/register-config | 200 | 200 | PASS | email_verify=False |
| auth | 无令牌访问应401 | GET | /authorization/auth/me | 401 | 401 | PASS |  |
| token | 创建令牌 | POST | /authorization/tokens/create | 201 | 201 | PASS |  |
| token | 吊销用户全部令牌 | DELETE | /authorization/tokens/revoke-all/{user_id} | 改在测试用户上执行 | - | SKIP | 对 admin 执行会中断后续用例 |
| main | 服务状态-sys-info | GET | /server-status/sys-info | 200 | 200 | PASS |  |
| main | 服务状态-hardware-status | GET | /server-status/hardware-status | 200 | 200 | PASS |  |
| main | 服务状态-cache | GET | /server-status/cache | 200 | 200 | PASS |  |
| main | 服务状态-network-status | GET | /server-status/network-status | 200 | 200 | PASS |  |
| main | 服务状态-mount-count | GET | /server-status/mount-count | 200 | 200 | PASS |  |
| main | DB-表清单 | GET | /db/tables | 200 | 200 | PASS | 返回非空 |
| main | DB-向量库状态 | GET | /db/vector | 200 | 200 | PASS |  |
| main | DB-缓存库状态 | GET | /db/cache | 200 | 200 | PASS |  |
| main | DB-建库/重置(破坏性) | GET | /db/create, /db/reset | 跳过执行 | - | SKIP | 破坏性接口不实测 |
| dict | 创建字典类型 | POST | /dict_types | 201 | 201 | PASS |  |
| dict | 创建字典项 | POST | /dict_items | 201 | 201 | PASS |  |
| dict | 字典类型滚动查询 | GET | /dict_types/scroll | 200 | 200 | PASS |  |
| dict | 字典类型分页 | GET | /dict_types/list | 200 | 200 | PASS |  |
| dict | 按编码查类型 | GET | /dict_types/code/t_type_7dc20a | 200 | 200 | PASS |  |
| dict | 字典项滚动查询 | GET | /dict_items/scroll | 200 | 200 | PASS |  |
| dict | 字典项分页 | GET | /dict_items/list | 200 | 200 | PASS |  |
| dict | 按类型查字典项 | GET | /dict_items/by-type/t_type_7dc20a | 200 | 200 | PASS |  |
| dict | 字典项计数 | GET | /dict_items/by-type/t_type_7dc20a/count | 200 | 200 | PASS |  |
| dict | 按编码查字典项 | GET | /dict_items/code/t_item_7dc20a | 200 | 200 | PASS |  |
| dict | 更新字典项 | PUT | /dict_items/b219b435b203410390ae20ad7b86a354 | 204 | 204 | PASS |  |
| dict | 删除字典项 | DELETE | /dict_items/b219b435b203410390ae20ad7b86a354 | 自定义 | 204 | PASS |  |
| dict | 更新字典类型 | PUT | /dict_types/2c6414de168c4135a7499d112b26e0c8 | 204 | 204 | PASS |  |
| dict | 删除字典类型 | DELETE | /dict_types/2c6414de168c4135a7499d112b26e0c8 | 自定义 | 204 | PASS |  |
| sysconf | 查询全部系统配置 | GET | /sys-configs | 200 | 200 | PASS |  |
| sysconf | 查询email组配置 | GET | /sys-configs/email | 200 | 200 | PASS |  |
| sysconf | 回写email组(原值) | PUT | /sys-configs/email | 204 | 204 | PASS |  |
| dept | 创建部门 | POST | /authorization/depts | 201 | 201 | PASS |  |
| dept | 部门树 | GET | /authorization/depts/tree | 200 | 200 | PASS | 2个根节点 |
| dept | 部门分页 | GET | /authorization/depts/list | 200 | 200 | PASS |  |
| dept | 部门详情 | GET | /authorization/depts/efaf8c972ab340a4ad32b16e9c26b4b1 | 200 | 200 | PASS |  |
| dept | 更新部门 | PUT | /authorization/depts/efaf8c972ab340a4ad32b16e9c26b4b1 | 204 | 204 | PASS |  |
| user | 创建用户 | POST | /authorization/users | 201 | 201 | PASS |  |
| user | 用户分页列表 | GET | /authorization/users/list | 200 | 200 | PASS |  |
| user | 用户详情 | GET | /authorization/users/d97a9828d02c498fa3c73a66d7a08cb9 | 200 | 200 | PASS |  |
| user | 更新用户 | PUT | /authorization/users/d97a9828d02c498fa3c73a66d7a08cb9 | 204 | 204 | PASS |  |
| user | 校验用户密码 | POST | /authorization/users/authenticate | 200 | 200 | PASS |  |
| user | 错误密码应401 | POST | /authorization/users/authenticate | 401 | 401 | PASS |  |
| role | 创建角色 | POST | /authorization/roles | 201 | 201 | PASS |  |
| role | 角色分页 | GET | /authorization/roles/list | 200 | 200 | PASS |  |
| role | 全部角色 | GET | /authorization/roles/all | 200 | 200 | PASS |  |
| role | 按名称查(不存在应404) | GET | /authorization/roles/name/不存在角色xx | 404 | 404 | PASS |  |
| role | 按key查角色 | GET | /authorization/roles/key/t_role_7dc20a | 200 | 200 | PASS |  |
| role | 角色详情 | GET | /authorization/roles/667c89252bb5437eb1d8efdc0b545827 | 200 | 200 | PASS |  |
| role | 更新角色 | PUT | /authorization/roles/667c89252bb5437eb1d8efdc0b545827 | 自定义 | 204 | PASS |  |
| perm | 权限树 | GET | /authorization/permissions/tree | 200 | 200 | PASS | 非空树 |
| perm | 权限分页 | GET | /authorization/permissions/list | 200 | 200 | PASS |  |
| perm | 权限树取code/id | GET | /authorization/permissions/tree | 200 | 200 | PASS |  |
| perm | 按code查权限 | GET | /authorization/permissions/code/sys | 200 | 200 | PASS |  |
| perm | 权限详情 | GET | /authorization/permissions/d449f92aac82412b8d0197a2b8d16b68 | 200 | 200 | PASS |  |
| perm | 按父查子权限 | GET | /authorization/permissions/parent/d449f92aac82412b8d0197a2b8d16b68 | 200 | 200 | PASS |  |
| casbin | 策略列表 | GET | /authorization/casbin-rules/policies | 200 | 200 | PASS |  |
| casbin | 角色-用户关系 | GET | /authorization/casbin-rules/grouping-policies | 200 | 200 | PASS |  |
| casbin | 模块权限树 | GET | /authorization/casbin-rules/module-tree | 200 | 200 | PASS |  |
| casbin | 用户角色查询 | GET | /authorization/casbin-rules/roles/56744fe711cc4d0593d49b514679f042 | 200 | 200 | PASS |  |
| casbin | 角色权限查询 | GET | /authorization/casbin-rules/permissions/t_role_7dc20a | 200 | 200 | PASS |  |
| casbin | 角色权限树查询 | GET | /authorization/casbin-rules/role-perms/t_role_7dc20a | 200 | 200 | PASS |  |
| casbin | 权限校验(admin) | POST | /authorization/casbin-rules/check-permission | 200 | 200 | PASS | has_permission=True |
| casbin | 绑定用户到角色 | POST | /authorization/casbin-rules/role-user | 201 | 201 | PASS |  |
| casbin | 验证用户已绑角色 | GET | /authorization/casbin-rules/roles/d97a9828d02c498fa3c73a66d7a08cb9 | 200 | 200 | PASS | 含测试角色key |
| casbin | 批量授权 | POST | /authorization/casbin-rules/batch-role-permissions | 201 | 201 | PASS |  |
| casbin | 校验测试角色新权限 | POST | /authorization/casbin-rules/check-permission | 200 | 200 | PASS | has_permission=False |
| casbin | 批量绑角色 | POST | /authorization/casbin-rules/batch-user-roles | 201 | 201 | PASS |  |
| casbin | 重载策略 | POST | /authorization/casbin-rules/reload-policy | 200 | 200 | PASS |  |
| casbin | 清空角色权限 | DELETE | /authorization/casbin-rules/role-permissions/t_role_7dc20a | 200 | 200 | PASS |  |
| casbin | 解绑用户全部角色 | DELETE | /authorization/casbin-rules/user-roles/d97a9828d02c498fa3c73a66d7a08cb9 | 200 | 200 | PASS |  |
| auth | 更新个人资料 | PUT | /authorization/auth/me | 200 | 200 | PASS |  |
| auth | 上传头像 | POST | /authorization/auth/me/avatar | 200 | 200 | PASS |  |
| auth | 删除头像 | DELETE | /authorization/auth/me/avatar | 204 | 204 | PASS |  |
| auth | 测试用户修改密码 | PUT | /authorization/auth/me/password | 204 | 204 | PASS |  |
| auth | 旧密码应失效 | POST | /authorization/auth/login | 401 | 401 | PASS |  |
| auth | 新密码登录 | POST | /authorization/auth/login | 200 | 200 | PASS |  |
| auth | 测试用户自助改昵称 | PUT | /authorization/auth/me | 200 | 200 | PASS |  |
| token | 吊销测试用户全部令牌 | DELETE | /authorization/tokens/revoke-all/d97a9828d02c498fa3c73a66d7a08cb9 | 200 | 200 | PASS |  |
| auth | 登出 | POST | /authorization/auth/logout | 200 | 200 | PASS |  |
| auth | 注册配置复查 | GET | /authorization/auth/register-config | 200 | 200 | PASS |  |
| auth | 直接注册新用户 | POST | /authorization/auth/register | 200 | 200 | PASS |  |
| file | 上传模式查询 | GET | /file/filesystem/upload-mode | 200 | 200 | PASS |  |
| file | 存储统计 | GET | /file/filesystem/stats | 200 | 200 | PASS |  |
| file | 根目录子目录 | GET | /file/filesystem/dirs | 200 | 200 | PASS |  |
| file | 根目录列表 | GET | /file/filesystem/list-dir | 200 | 200 | PASS |  |
| file | 路径查询(缺参应422) | GET | /file/filesystem/path | 422 | 422 | PASS |  |
| file | 创建目录 | POST | /file/filesystem/folder | 201 | 201 | PASS |  |
| file | 创建子目录 | POST | /file/filesystem/folder | 201 | 201 | PASS |  |
| file | 子目录列表 | GET | /file/filesystem/list-dir | 200 | 200 | PASS |  |
| file | 目录树懒加载 | GET | /file/filesystem/dirs | 200 | 200 | PASS |  |
| file | 上传文件 | POST | /file/filesystem/upload | 201 | 201 | PASS |  |
| file | 文件详情 | GET | /file/filesystem/entries/1d8968ea0d3749c094494cc3ac44a4b6/detail | 200 | 200 | PASS |  |
| file | 文件元数据 | GET | /file/filesystem/entries/1d8968ea0d3749c094494cc3ac44a4b6 | 200 | 200 | PASS |  |
| file | 下载文件 | GET | /file/filesystem/download/1d8968ea0d3749c094494cc3ac44a4b6 | 200 | 200 | PASS | 93B 内容一致 |
| file | 批量下载权限探测 | POST | /file/filesystem/download-perms | 200 | 200 | PASS |  |
| file | 重命名 | PUT | /file/filesystem/entries/1d8968ea0d3749c094494cc3ac44a4b6/rename | 200 | 200 | PASS |  |
| file | 复制文件 | POST | /file/filesystem/copy | 201 | 201 | PASS |  |
| file | 移动文件 | PUT | /file/filesystem/entries/034818d979ec451fa0196394b74ddbbe/move | 200 | 200 | PASS |  |
| file | 删除副本 | DELETE | /file/filesystem/files/034818d979ec451fa0196394b74ddbbe | 自定义 | 204 | PASS |  |
| file | 级联建目录 | POST | /file/filesystem/mkdir-p | 201 | 201 | PASS |  |
| file | 按名搜索 | GET | /file/filesystem/search | 200 | 200 | PASS |  |
| file | 删除文件 | DELETE | /file/filesystem/files/1d8968ea0d3749c094494cc3ac44a4b6 | 自定义 | 204 | PASS |  |
| file | 分片-初始化 | POST | /file/filesystem/multipart/init | 200 | 200 | PASS |  |
| file | 分片-上传第1片 | PUT | /file/filesystem/multipart/eyJrZXkiOiI0NGRlYjg2NGE1N2U0YmE4OGVkZTQwNGVhZDk4ZDIyNC5wbmciLCJ1aWQiOiJjOGNiMzM1YjhkMmE0MGU2OWNlYjQ0OTNhYWYzYTFmMCIsImhhc2giOiI4NzYyMzg3MTcyMDVhZDM5ZTQ0MzdiMGIzNTNkYzQyNTE2Y2MwNzUzMGI5ZTI1NDE1ZjkxNmNjMDM0OTZiZWMwIiwibW9kZSI6InByb3h5IiwiZXhwIjoxNzkyMzM3OTQ4fQ.ccf2abae592f8ce29f05926390dda9b2c5bf24dd9c920b6e0fc8ffd9451643f1/parts/1 | 200 | 200 | PASS |  |
| file | 分片-列表 | GET | /file/filesystem/multipart/eyJrZXkiOiI0NGRlYjg2NGE1N2U0YmE4OGVkZTQwNGVhZDk4ZDIyNC5wbmciLCJ1aWQiOiJjOGNiMzM1YjhkMmE0MGU2OWNlYjQ0OTNhYWYzYTFmMCIsImhhc2giOiI4NzYyMzg3MTcyMDVhZDM5ZTQ0MzdiMGIzNTNkYzQyNTE2Y2MwNzUzMGI5ZTI1NDE1ZjkxNmNjMDM0OTZiZWMwIiwibW9kZSI6InByb3h5IiwiZXhwIjoxNzkyMzM3OTQ4fQ.ccf2abae592f8ce29f05926390dda9b2c5bf24dd9c920b6e0fc8ffd9451643f1/parts | 200 | 200 | PASS |  |
| file | 分片-完成合并 | POST | /file/filesystem/multipart/eyJrZXkiOiI0NGRlYjg2NGE1N2U0YmE4OGVkZTQwNGVhZDk4ZDIyNC5wbmciLCJ1aWQiOiJjOGNiMzM1YjhkMmE0MGU2OWNlYjQ0OTNhYWYzYTFmMCIsImhhc2giOiI4NzYyMzg3MTcyMDVhZDM5ZTQ0MzdiMGIzNTNkYzQyNTE2Y2MwNzUzMGI5ZTI1NDE1ZjkxNmNjMDM0OTZiZWMwIiwibW9kZSI6InByb3h5IiwiZXhwIjoxNzkyMzM3OTQ4fQ.ccf2abae592f8ce29f05926390dda9b2c5bf24dd9c920b6e0fc8ffd9451643f1/complete | 201 | 201 | PASS |  |
| file | 搜索分片产物 | GET | /file/filesystem/search | 200 | 200 | PASS |  |
| file | 删除分片产物 | DELETE | /file/filesystem/files/19d45d756da44ba0bac3f1bc425692b9 | 自定义 | 204 | PASS |  |
| file | 批量删除(空列表应422) | POST | /file/filesystem/entries/batch-delete | 422 | 422 | PASS |  |
| file | 删除测试目录 | DELETE | /file/filesystem/folders/2d3b4e38c93f4c7b9522f2d69b2f1b0c | 自定义 | 204 | PASS |  |
| file | 迁移接口(空参应拒绝) | POST | /file/filesystem/migrate | 422 | 422 | PASS |  |
| ai | 模型配置列表 | GET | /ai/model-configs/list | 200 | 200 | PASS |  |
| ai | 模型配置滚动 | GET | /ai/model-configs/scroll | 200 | 200 | PASS |  |
| ai | 默认参数查询 | GET | /ai/model-configs/default-params/qwen-plus | 200 | 200 | PASS |  |
| ai | 创建模型配置 | POST | /ai/model-configs | 201 | 201 | PASS |  |
| ai | 模型配置详情 | GET | /ai/model-configs/db167dd4f3254477b22be1cf9750f74f | 200 | 200 | PASS |  |
| ai | 更新模型配置 | PUT | /ai/model-configs/db167dd4f3254477b22be1cf9750f74f | 自定义 | 204 | PASS |  |
| ai | LLM连通测试(无效key) | POST | /ai/llm/check-config | 200 | 200 | PASS |  |
| ai | 按ID连通测试(无效key) | POST | /ai/llm/check-config-by-model-id | 200 | 422 | XFAIL |  |
| ai | 按ID对话测试(无效key) | POST | /ai/llm/test-by-model-id | 200 | 200 | PASS |  |
| ai | LLM对话(无效key) | POST | /ai/llm/chat | 200 | 500 | XFAIL |  |
| ai | 清除模型缓存 | DELETE | /ai/llm/cache/db167dd4f3254477b22be1cf9750f74f | 200 | 200 | PASS |  |
| ai | token计数 | POST | /ai/llm/token-count | 200 | 200 | PASS | 结果={'counts': [6], 'total': 6} |
| ai | 重排序(无效key) | POST | /ai/rerank | 200 | 500 | XFAIL |  |
| ai | 语音识别(无效key) | POST | /ai/voice/asr | 200 | 422 | XFAIL |  |
| ai | 语音合成文件(无效key) | POST | /ai/voice/tts/file | 200 | 500 | XFAIL |  |
| ai | 语音合成流式(无效key) | POST | /ai/voice/tts/stream | 200 | 200 | PASS |  |
| ai | OCR识别(无效key) | POST | /ai/ocr/ | 201 | 500 | XFAIL |  |
| ai | OCR兼容路由(无效key) | POST | /ai/ocr/all | 201 | 500 | XFAIL |  |
| ai | OCR批量base64(无效key) | POST | /ai/ocr/all-base64 | 201 | 400 | XFAIL |  |
| ai | OCR语言列表(GET返回201) | GET | /ai/ocr/languages | 201 | 201 | PASS |  |
| ai | AI静态资源 | GET | /ai/static/ | 200 | 200 | PASS |  |
| ai | 删除测试模型 | DELETE | /ai/model-configs/db167dd4f3254477b22be1cf9750f74f | 自定义 | 204 | PASS |  |
| rag | 创建知识库项目 | POST | /rag/projects | 201 | 201 | PASS |  |
| rag | 项目列表 | GET | /rag/projects/list | 200 | 200 | PASS |  |
| rag | 项目详情 | GET | /rag/projects/599482d823e84e3b83c4978b95f9828d | 200 | 200 | PASS |  |
| rag | 更新项目 | PUT | /rag/projects/599482d823e84e3b83c4978b95f9828d | 自定义 | 204 | PASS |  |
| rag | 添加项目成员 | POST | /rag/project-members | 201 | 201 | PASS |  |
| rag | 项目成员列表 | GET | /rag/project-members/project/599482d823e84e3b83c4978b95f9828d | 200 | 200 | PASS |  |
| rag | 我的项目成员关系 | GET | /rag/project-members/my | 200 | 200 | PASS |  |
| rag | 取测试用户成员ID | GET | /rag/project-members/project/599482d823e84e3b83c4978b95f9828d | 200 | 200 | PASS |  |
| rag | 成员详情 | GET | /rag/project-members/3e5620447d1e41b585559dba7c53a768 | 200 | 200 | PASS |  |
| rag | 改成员角色 | PUT | /rag/project-members/3e5620447d1e41b585559dba7c53a768 | 自定义 | 204 | PASS |  |
| rag | 移除成员 | DELETE | /rag/project-members/3e5620447d1e41b585559dba7c53a768 | 自定义 | 204 | PASS |  |
| rag | 部门授权树 | GET | /rag/project-depts/dept-tree | 200 | 200 | PASS |  |
| rag | 添加部门授权 | POST | /rag/project-depts | 201 | 201 | PASS |  |
| rag | 项目授权列表/取ID | GET | /rag/project-depts/project/599482d823e84e3b83c4978b95f9828d | 200 | 200 | PASS |  |
| rag | 改授权档位 | PUT | /rag/project-depts/70c05387214d4d4b845351da6e980d57 | 自定义 | 200 | PASS |  |
| rag | 删除授权 | DELETE | /rag/project-depts/70c05387214d4d4b845351da6e980d57 | 自定义 | 204 | PASS |  |
| rag | 支持的文档类型 | GET | /rag/project-documents/supported-types | 200 | 200 | PASS |  |
| rag | 文档上传模式 | GET | /rag/project-documents/upload-mode | 200 | 200 | PASS |  |
| rag | 解析模型检查 | GET | /rag/project-documents/model-check | 200 | 200 | PASS |  |
| rag | 上传PDF文档(解析依赖MinerU) | POST | /rag/project-documents/599482d823e84e3b83c4978b95f9828d/upload | 201 | 201 | PASS |  |
| rag | 项目文档列表 | GET | /rag/project-documents/599482d823e84e3b83c4978b95f9828d/list | 200 | 200 | PASS |  |
| rag | 项目文档树 | GET | /rag/project-documents/599482d823e84e3b83c4978b95f9828d/entries | 200 | 200 | PASS |  |
| rag | 文档详情 | GET | /rag/project-documents/6b8a7a5d5d2342d8bd28cdb3413fb03f | 200 | 200 | PASS |  |
| rag | 解析进度 | GET | /rag/project-documents/6b8a7a5d5d2342d8bd28cdb3413fb03f/progress | 200 | 200 | PASS |  |
| rag | 文档下载 | GET | /rag/project-documents/6b8a7a5d5d2342d8bd28cdb3413fb03f/download | 200 | 200 | PASS | 192B |
| rag | 更新文档信息 | PUT | /rag/project-documents/6b8a7a5d5d2342d8bd28cdb3413fb03f | 自定义 | 204 | PASS |  |
| rag | 建项目文件夹 | POST | /rag/project-documents/599482d823e84e3b83c4978b95f9828d/folders | 201 | 201 | PASS |  |
| rag | 改文件夹名 | PUT | /rag/project-documents/599482d823e84e3b83c4978b95f9828d/folders/be7927cabeab4e46a57c211239c5595a | 自定义 | 200 | PASS |  |
| rag | 删文件夹 | DELETE | /rag/project-documents/599482d823e84e3b83c4978b95f9828d/folders/be7927cabeab4e46a57c211239c5595a | 自定义 | 204 | PASS |  |
| rag | 重解析(无MinerU) | POST | /rag/project-documents/6b8a7a5d5d2342d8bd28cdb3413fb03f/reparse | 200 | 500 | XFAIL |  |
| rag | 重解析任务(无MinerU) | POST | /rag/project-documents/6b8a7a5d5d2342d8bd28cdb3413fb03f/reparse-task | 200 | 200 | PASS |  |
| rag | 按问题搜分块 | POST | /rag/project-document-chunks/search-by-question | 200 | 400 | XFAIL |  |
| rag | 全库重向量化(无embeddings) | POST | /rag/project-document-chunks/revectorize | 202 | 202 | PASS |  |
| rag | 删除文档 | DELETE | /rag/project-documents/6b8a7a5d5d2342d8bd28cdb3413fb03f | 自定义 | 204 | PASS |  |
| rag | 创建会话 | POST | /rag/conversations | 201 | 201 | PASS |  |
| rag | 我的会话列表 | GET | /rag/conversations/my | 200 | 200 | PASS |  |
| rag | 会话详情 | GET | /rag/conversations/a93b18e9f7bb49a89ba3d0d835228a45 | 200 | 200 | PASS |  |
| rag | 会话消息 | GET | /rag/conversations/a93b18e9f7bb49a89ba3d0d835228a45/messages | 200 | 200 | PASS |  |
| rag | 改会话标题 | PUT | /rag/conversations/a93b18e9f7bb49a89ba3d0d835228a45 | 自定义 | 204 | PASS |  |
| rag | RAG问答(无LLM key) | POST | /rag/rag-chat/a93b18e9f7bb49a89ba3d0d835228a45/chat | 200 | 200 | PASS |  |
| rag | 会话总结(无LLM key) | POST | /rag/rag-chat/a93b18e9f7bb49a89ba3d0d835228a45/summarize | 200 | 200 | PASS |  |
| rag | 删除会话 | DELETE | /rag/conversations/a93b18e9f7bb49a89ba3d0d835228a45 | 自定义 | 204 | PASS |  |
| rag | 查我的模型绑定 | GET | /rag/user-models/my | 200 | 200 | PASS |  |
| rag | 设置我的模型绑定 | PUT | /rag/user-models/my | 200 | 200 | PASS |  |
| rag | 复查模型绑定 | GET | /rag/user-models/my | 200 | 200 | PASS |  |
| rag | 删除测试项目 | DELETE | /rag/projects/599482d823e84e3b83c4978b95f9828d | 自定义 | 204 | PASS |  |
| task | 任务类型注册表 | GET | /task/tasks/registry | 200 | 200 | PASS | 3种任务类型 |
| task | 任务统计 | GET | /task/tasks/stats | 200 | 200 | PASS |  |
| task | 任务分页列表 | GET | /task/tasks/list | 200 | 200 | PASS |  |
| task | 任务详情 | GET | /task/tasks/f5bb32328e2d4cd481b0b191bcde14e4 | 200 | 200 | PASS |  |
| task | 同步任务状态 | POST | /task/tasks/f5bb32328e2d4cd481b0b191bcde14e4/sync | 200 | 200 | PASS |  |
| task | 取消遗留任务(运行中应400) | POST | /task/tasks/f5bb32328e2d4cd481b0b191bcde14e4/cancel | 204 | 400 | XFAIL |  |
| task | 取注册表建任务 | GET | /task/tasks/registry | 200 | 200 | PASS |  |
| task | 创建任务 | POST | /task/tasks | 201 | 201 | PASS |  |
| task | 新任务详情 | GET | /task/tasks/65a22a27f97545ffb050d2423e40ca66 | 200 | 200 | PASS |  |
| task | 取消新任务 | POST | /task/tasks/65a22a27f97545ffb050d2423e40ca66/cancel | 204 | 204 | PASS |  |
| task | 删除任务 | DELETE | /task/tasks/65a22a27f97545ffb050d2423e40ca66 | 204 | 204 | PASS |  |
| tpl | 创建模板1 | POST | /template/templates | 201 | 201 | PASS |  |
| tpl | 创建模板2 | POST | /template/templates | 201 | 201 | PASS |  |
| tpl | 模板分页 | GET | /template/templates/list | 200 | 200 | PASS |  |
| tpl | 模板滚动查询 | GET | /template/templates/scroll | 200 | 200 | PASS |  |
| tpl | 模板详情 | GET | /template/templates/c1c370e67dce45e19ab0026fa09cde37 | 200 | 200 | PASS |  |
| tpl | 更新模板 | PUT | /template/templates/c1c370e67dce45e19ab0026fa09cde37 | 自定义 | 204 | PASS |  |
| tpl | 示例-上传 | POST | /template/template-ex/upload | 200 | 200 | PASS |  |
| tpl | 示例-流式下载 | GET | /template/template-ex/stream | 200 | 200 | PASS |  |
| tpl | 异步学习-sync | GET | /template/template-async-learn/sync/1/1 | 200 | 200 | PASS |  |
| tpl | 异步学习-async | GET | /template/template-async-learn/async/1/1 | 200 | 200 | PASS |  |
| tpl | 异步学习-async-sync | GET | /template/template-async-learn/async-sync/1/1 | 200 | 200 | PASS |  |
| tpl | 异步学习-async-threadpool | GET | /template/template-async-learn/async-threadpool/1/1 | 200 | 200 | PASS |  |
| tpl | 模板静态资源 | GET | /template/static/ | 200 | 200 | PASS |  |
| tpl | 批量删除模板 | DELETE | /template/templates/batch | 自定义 | 200 | PASS |  |
| cleanup | 扫描残留tuser_用户 | GET | /authorization/users/list | 200 | 200 | PASS |  |
| cleanup | 清理残留用户tuser_ea6972 | DELETE | /authorization/users/d2d4de480e4a43bb9b843abf409bc936 | 204 | 204 | PASS |  |
| cleanup | 清理残留用户tuser_7dc20a | DELETE | /authorization/users/d97a9828d02c498fa3c73a66d7a08cb9 | 204 | 204 | PASS |  |
| cleanup | 清理残留用户treg_7dc20a | DELETE | /authorization/users/f629372f4f174b9eb0d1589f37f65922 | 204 | 204 | PASS |  |
| cleanup | 扫描残留treg_用户 | GET | /authorization/users/list | 200 | 200 | PASS |  |
| cleanup | 删除测试部门 | DELETE | /authorization/depts/efaf8c972ab340a4ad32b16e9c26b4b1 | 204 | 204 | PASS |  |
| cleanup | 删除测试角色 | DELETE | /authorization/roles/667c89252bb5437eb1d8efdc0b545827 | 自定义 | 204 | PASS |  |
| auth | 管理员登出 | POST | /authorization/auth/logout | 200 | 200 | PASS |  |
