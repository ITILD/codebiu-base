// 任务队列模块类型定义(Celery + Redis 异步任务)

/** 任务状态(与后端 QueueTaskStatus 对齐) */
type TaskStatus = 'pending' | 'running' | 'success' | 'failed' | 'cancelled' | 'revoked'

/** 状态显示配置(标签文本) */
const statusLabels: Record<TaskStatus, string> = {
  pending: '排队中',
  running: '执行中',
  success: '成功',
  failed: '失败',
  cancelled: '已取消',
  revoked: '已撤销',
}

/** 状态标签样式(element-plus tag type) */
type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'
const statusTagTypes: Record<TaskStatus, TagType> = {
  pending: 'info',
  running: 'primary',
  success: 'success',
  failed: 'danger',
  cancelled: 'warning',
  revoked: 'warning',
}

/** 状态筛选下拉选项 */
const statusOptions = (Object.keys(statusLabels) as TaskStatus[]).map(value => ({
  label: statusLabels[value],
  value,
}))

/** 任务类型定义(后端注册表条目, 供新建任务下拉/默认参数模板/优先级热调表) */
interface TaskTypeDef {
  type: string
  name: string
  description: string
  celery_task: string
  default_payload: Record<string, unknown>
  /** 类型默认优先级(创建未显式指定时采用) */
  default_priority?: number
  /** 运维覆盖的优先级(null/未定义=未覆盖) */
  priority_override?: number | null
  /** 当前生效优先级(覆盖值 ?? 默认值) */
  effective_priority?: number
  /** 按生效优先级路由的消费队列 */
  queue?: string
}

/** 任务记录(后端返回, 含 Celery 侧状态对照; 纯任务管理: 不含业务参数/结果) */
interface QueueTask {
  id: string
  name: string
  task_type: string
  priority: number
  status: TaskStatus
  /** 完成百分比 0~100(worker 实时回写) */
  progress: number
  /** 当前执行阶段描述 */
  message: string | null
  error: string | null
  celery_task_id: string | null
  /** Celery 结果后端状态(PENDING/STARTED/PROGRESS/SUCCESS/FAILURE/REVOKED) */
  celery_state: string | null
  /** Celery 侧回传百分比 */
  celery_progress: number | null
  started_at: string | null
  finished_at: string | null
  created_at: string
  updated_at: string
}

/** 创建任务请求体 */
interface QueueTaskCreate {
  name: string
  task_type: string
  payload: Record<string, unknown>
  /** 优先级(0~9 越大越优先; 不传时按类型生效优先级) */
  priority?: number | null
}

/** 任务状态统计(概览卡片) */
interface TaskStats {
  total: number
  pending: number
  running: number
  success: number
  failed: number
  cancelled: number
}

// ################ 周期调度(REQ-012 定时任务) ################

/** 调度定义(后端 task_schedule 表; 触发方式 cron/interval 二选一) */
interface TaskSchedule {
  id: number
  name: string
  task_type: string
  payload: Record<string, unknown>
  /** 5 字段 cron 表达式(分 时 日 月 周) */
  cron: string | null
  /** 固定触发间隔(秒, ≥60) */
  interval_seconds: number | null
  enabled: boolean
  /** 下次触发时刻(UTC, 停用时为 null) */
  next_fire_at: string | null
  last_fired_at: string | null
  /** 最近触发生成的任务ID(跳转任务详情) */
  last_task_id: string | null
  last_status: string | null
  remark: string | null
  created_by: string
  created_at: string
  updated_at: string
}

/** 创建/修改调度请求体(修改为全量字段) */
interface TaskScheduleSave {
  name: string
  task_type: string
  payload: Record<string, unknown>
  cron: string | null
  interval_seconds: number | null
  enabled: boolean
  remark: string | null
}

/** cron 快捷表达式预置(后端 /task/schedules/presets) */
interface CronPreset {
  key: string
  expr: string
}

/** 手动立即触发结果 */
interface TaskScheduleTriggerResult {
  task_id: string
  schedule_id: number
}

// ################ 执行器监控与任务自愈 ################

/** Celery 执行器(worker)运行状态条目 */
interface TaskWorkerInfo {
  name: string
  /** 消费的队列列表 */
  queues: string[]
  /** 并发槽位数 */
  concurrency: number
  /** 当前活跃任务数 */
  active: number
  /** 累计已处理任务数 */
  processed: number
  uptime_seconds?: number | null
  /** 正在执行的任务(name/id/args 摘要) */
  active_tasks: Array<{ name: string; id: string; args?: string }>
  pid?: number | null
}

/** 执行器状态响应(broker 不可用时 online=0 且带 error 提示) */
interface TaskWorkerList {
  total: number
  online: number
  workers: TaskWorkerInfo[]
  error?: string | null
}

/** 手动自愈结果(重派发遗留 PENDING + 清扫僵尸 RUNNING) */
interface TaskRecoverResult {
  recovered: number
  reaped: number
}

export {
  statusLabels,
  statusTagTypes,
  statusOptions,
  type TagType,
  type TaskStatus,
  type TaskTypeDef,
  type QueueTask,
  type QueueTaskCreate,
  type TaskStats,
  type TaskSchedule,
  type TaskScheduleSave,
  type CronPreset,
  type TaskScheduleTriggerResult,
  type TaskWorkerInfo,
  type TaskWorkerList,
  type TaskRecoverResult,
}
