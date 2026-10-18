# doc

开发组织记录文档

## 基线仓库包
| 仓库包名 | 仓库地址 | 仓库说明 |
| :---: | :---: | :---: |
| [base_web](http://zwork1.w1.luyouxia.net/gitea/codebiu_2025/base_web) | [http://zwork1.w1.luyouxia.net/gitea/codebiu_2025/base_web](http://zwork1.w1.luyouxia.net/gitea/codebiu_2025/base_web) | 前端基线 |
| [base_server](http://zwork1.w1.luyouxia.net/gitea/codebiu_2025/base_server) | [http://zwork1.w1.luyouxia.net/gitea/codebiu_2025/base_server](http://zwork1.w1.luyouxia.net/gitea/codebiu_2025/base_server) | 后端基线 |
| [doc](http://zwork1.w1.luyouxia.net/gitea/codebiu_2025/doc) | [http://zwork1.w1.luyouxia.net/gitea/codebiu_2025/doc](http://zwork1.w1.luyouxia.net/gitea/codebiu_2025/doc) | 记录文档 |

## 新人导航

| 文档 | 说明 |
| :--- | :--- |
| [技术基础](./01-入门/1-技术基础.md) | 前置语言与框架基础 |
| [项目基础](./01-入门/2-项目基础.md) | 环境安装与第一天的开发任务 |
| [开发环境配置](./01-入门/3-开发环境.md) | uv / pnpm / 数据库等基础环境 |
| [后端开发指南](./02-开发指南/2-后端开发.md) | MVC 分层与新模块开发六步法 |
| [前端开发指南](./02-开发指南/3-前端开发.md) | 页面开发三件套与主题规范 |
| [权限体系](./02-开发指南/4-权限体系.md) | Casbin RBAC 接入 |
| [需求功能登记册](./03-设计文档/00-需求功能登记册.md) | **需求/功能唯一台账（批准门禁核心）** |
| [需求分析](./03-设计文档/01-需求分析.md) | 基线业务功能与非功能需求 |
| [总体架构与功能设计](./03-设计文档/02-总体架构与功能设计.md) | 系统架构、模块划分 |
| [权限设计](./03-设计文档/03-权限设计.md) | 权限模型现状（v4 定案已并入本文） |
| [需求卡模板](./03-设计文档/99-需求卡模板.md) | 新需求/功能登记模板 |
| [需求与功能管理](./04-规范/需求与功能管理.md) | **需求→批准→开发→交付治理规则（批准门禁）** |
| [开发流程](./04-规范/开发流程.md) | 新功能开发手册（前后端接入清单） |
| [代码规范](./04-规范/代码规范.md) | Python3.13/Vue3 命名/注释/分层/依赖约束 |
| [前端样式规范](./04-规范/前端样式规范.md) | 样式写入位置决策树（原子类优先/页内常量/scoped 白名单） |
| 部署运维 | 见仓库根目录 `deveops/` |

## 目录结构

```
doc_ch/
├── 01-入门/       技术基础、项目基础、开发环境、数据库、IDE 插件、其他环境
├── 02-开发指南/   大模型调用、后端开发、前端开发、权限体系、内存优化
├── 03-设计文档/   需求功能登记册、需求分析、总体架构与功能设计、权限设计、需求卡模板
└── 04-规范/       需求与功能管理、开发流程、代码规范、前端样式、响应式自适应、版本管理、Markdown 格式
```

> AI 协作与需求流转的入口见根目录 [README_AI.md](../../README_AI.md)。

## 版本导航

本仓库为从真实项目抽取的**精简基线**：

| 阶段 | 说明 |
| :--- | :--- |
| 基线版本 | 通用底座能力：健康检测/数据监测/字典/通用配置（module_main）、注册登录 JWT/用户角色部门/Casbin 权限（module_authorization，含注册邮箱验证码）、虚拟文件系统（module_file）、模型配置/LLM 对话/重排/OCR/语音（module_ai）、知识库问答（module_rag）、文档解析 MinerU 外部服务（module_office）、本地+Celery 双引擎任务队列（module_task）、模板示例（module_template） |
| 按需扩展 | 智能体、邮件、个人小站、生活工具、地理空间、图数据库、网页搜索等业务模块已裁剪，参照 [后端开发指南](./02-开发指南/2-后端开发.md) 的模块开发六步法按需新建 |

## 项目仓库人员介绍

| 仓库人员 | 专业 | 年级 |职责|
| :---: | :---: | :---: | :---: |
| [itild](http://zwork1.w1.luyouxia.net/gitea/itild) | 地信 | 12 | PM |


# 贡献方式
分支dev  
pr审查
