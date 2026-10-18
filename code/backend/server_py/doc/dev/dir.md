# 项目目录结构说明

## 根目录结构
```
├── .env                          # 环境变量配置文件
├── .gitignore                    # Git忽略文件配置
├── .python-version              # Python版本声明
├── LICENSE                       # 许可证文件
├── README.md                     # 项目说明文档
├── config.yaml                   # 项目主配置文件
├── doc\                          # 文档目录
├── public\                       # 静态资源目录
├── pyproject.toml                # Python项目配置文件
├── pytest.ini                    # Pytest测试配置
├── rbac_model.conf               # RBAC权限模型配置
├── src\                          # 源代码主目录
├── tests\                        # 测试代码目录
└── tools\                        # 工具脚本目录
```

## 主要模块目录结构

### 核心源码目录(src)
```
src\
├── app.py                        # API 服务入口(Uvicorn 启动)
├── app_task.py                   # Celery Worker 入口(任务队列消费进程)
├── common\                       # 公共组件目录
│   ├── config\                   # 公共配置模块(db/tasks/lifespan/server 等)
│   ├── enum\                     # 公共枚举(任务状态等)
│   ├── exceptions\               # 公共异常处理模块
│   ├── middleware\               # 中间件模块
│   └── utils\                    # 公共工具函数模块
├── module_ai\                    # AI 功能模块(对话/模型配置/OCR/语音)
├── module_authorization\         # 权限认证模块(用户/角色/部门/权限/策略/注册邮箱验证码)
├── module_file\                  # 文件管理模块
├── module_main\                  # 主业务模块(字典/数据库/健康检测/通用配置)
├── module_office\                # 办公模块(文档解析/分块)
├── module_rag\                   # 知识库模块(项目/文档/成员/问答)
├── module_task\                  # 任务队列模块(本地+Celery 双引擎)
└── module_template\              # 模块模板(新模块脚手架)
```

> 已注册权限声明的模块: sys(系统管理) / main(基础资源) / rag(知识库) / task(任务队列)。
> 新加模块默认不带权限,接入方式见 [permission.md](./permission.md)。

### 各功能模块标准结构
大多数模块遵循以下标准目录结构：
```
module_xxx\
├── __init__.py                   # 模块初始化文件
├── config\                       # 模块配置
├── controller\                   # 控制器层（API接口）
├── dao\                          # 数据访问对象层
├── dependencies\                 # 依赖项
├── do\                           # 领域对象（Domain Object）
├── service\                      # 业务逻辑层
└── utils\                        # 模块专用工具函数
```

### 文档目录(doc)
```
doc\
├── dev\                          # 开发相关文档
│   ├── dir.md                    # 项目目录结构说明
│   ├── lib.md                    # 依赖库清单
│   └── permission.md             # 权限体系说明与新模块接入指南
├── sql\                          # SQL脚本文件
│   └── module_template.sql       # 模块数据表模板
└── tag_doc\                      # 版本标签文档
    ├── version_info.md           # 版本索引
    ├── tag_0.0.1.md / tag_0.0.2.md
    └── tag_todo.md               # 待办规划
```

### 静态资源目录(public)
```
public\
├── ai\                           # AI相关前端页面
├── common\                       # 通用静态资源
├── main\                         # 主应用前端页面
└── template\                     # 模板页面
```

### 测试目录(tests)
```
tests\
├── common\                       # 公共测试组件
├── conftest.py                   # Pytest配置文件
└── module_xxx\                   # 各模块对应的测试代码
```

### 工具目录(tools)
```
tools\
├── docker_build\                 # Docker构建工具
├── docker_dev\                   # Docker开发环境工具
└── test\                         # 测试运行工具
```