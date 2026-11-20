// 任务队列模块 API(Celery+Redis 异步任务管理)
import { http_base_server } from '@/common/api/http'
import type { PaginationParams, PaginationResponse } from '@/common/types/common'
import type {
  QueueTask,
  QueueTaskCreate,
  TaskQueueRegistry,
  TaskQueueRegistryCreate,
  TaskQueueRegistryUpdate,
  TaskRecoverResult,
  TaskStats,
  TaskTypeDef,
  TaskWorkerList,
  WorkerHostCreate,
  WorkerHostUpdate,
  WorkerHostView,
  WorkerScaleBody,
  WorkerScaleOp,
} from '../types'

/** 任务列表过滤参数 */
export type TaskListParams = PaginationParams & {
  /** 任务名称模糊搜索 */
  keyword?: string
  /** 状态过滤(pending/running/success/failed/cancelled) */
  status?: string
  /** 任务类型过滤 */
  task_type?: string
  /** 优先级过滤(0~9) */
  priority?: number
}

/**
 * 查询任务类型注册表(新建任务下拉 + 默认参数模板 + 优先级热调表)
 */
export const getTaskRegistry = () => {
  return http_base_server.get<TaskTypeDef[]>('/task/tasks/registry')
}

/**
 * 查询 Celery 执行器(worker)在线状态(broker 不可用时返回 online=0)
 */
export const getTaskWorkers = () => {
  return http_base_server.get<TaskWorkerList>('/task/tasks/workers')
}

/**
 * 热调任务类型入队优先级(传 null 清除覆盖回落默认值)
 * @param task_type 任务类型编码
 * @param priority 0~9; null=清除覆盖
 */
export const updateTaskTypePriority = (task_type: string, priority: number | null) => {
  return http_base_server.patch<TaskTypeDef>(
    `/task/tasks/registry/${task_type}/priority`,
    { priority },
  )
}

/**
 * 手动触发任务自愈(重派发遗留 PENDING + 清扫僵尸 RUNNING)
 */
export const recoverTasks = () => {
  return http_base_server.post<TaskRecoverResult>('/task/tasks/recover')
}

/**
 * 任务状态统计(概览卡片, 轮询刷新)
 */
export const getTaskStats = () => {
  return http_base_server.get<TaskStats>('/task/tasks/stats')
}

/**
 * 分页查询任务列表(含 Celery 状态对照字段)
 * @param params 分页与过滤参数
 */
export const listTasks = (params: TaskListParams) => {
  return http_base_server.get<PaginationResponse<QueueTask>>('/task/tasks/list', { params })
}

/**
 * 查询任务详情(含 Celery 侧状态/百分比)
 * @param id 任务ID
 */
export const getTask = (id: string) => {
  return http_base_server.get<QueueTask>(`/task/tasks/${id}`)
}

/**
 * 创建任务并投递 Celery 队列
 * @param data 任务数据(名称/类型/参数 JSON)
 */
export const createTask = (data: QueueTaskCreate) => {
  return http_base_server.post<string>('/task/tasks', data)
}

/**
 * 从 Celery 结果后端同步任务状态(worker 回写中断时校正)
 * @param id 任务ID
 */
export const syncTask = (id: string) => {
  return http_base_server.post<QueueTask>(`/task/tasks/${id}/sync`)
}

/**
 * 取消任务(排队/执行中)
 * @param id 任务ID
 */
export const cancelTask = (id: string) => {
  return http_base_server.post<void>(`/task/tasks/${id}/cancel`)
}

/**
 * 重试任务(已结束的任务重新入队)
 * @param id 任务ID
 */
export const retryTask = (id: string) => {
  return http_base_server.post<QueueTask>(`/task/tasks/${id}/retry`)
}

/**
 * 删除任务记录
 * @param id 任务ID
 */
export const deleteTask = (id: string) => {
  return http_base_server.delete<void>(`/task/tasks/${id}`)
}

// ################ 队列注册表(P2: 逻辑队列动态增减) ################

/**
 * 查询队列注册表(含实时订阅 worker 数与积压深度)
 */
export const listQueueRegistry = () => {
  return http_base_server.get<TaskQueueRegistry[]>('/task/queues')
}

/**
 * 登记新队列(落库即生效, worker 60s 内自动订阅; 可再调 subscribe 立即拉起)
 */
export const createQueueRegistry = (data: TaskQueueRegistryCreate) => {
  return http_base_server.post<TaskQueueRegistry>('/task/queues', data)
}

/**
 * 更新队列属性/启停(启停即时广播订阅增减, 秒级生效)
 */
export const updateQueueRegistry = (queueName: string, data: TaskQueueRegistryUpdate) => {
  return http_base_server.patch<TaskQueueRegistry>(`/task/queues/${queueName}`, data)
}

/**
 * 删除队列登记(内置队列不允许删除; 有订阅时先停用等退订)
 */
export const deleteQueueRegistry = (queueName: string) => {
  return http_base_server.delete<void>(`/task/queues/${queueName}`)
}

/**
 * 广播增加队列订阅(返回确认订阅的 worker 数)
 * @param worker 目标节点名(不传=广播全部动态模式 worker)
 */
export const subscribeQueue = (queueName: string, worker?: string) => {
  return http_base_server.post<number>(`/task/queues/${queueName}/subscribe`, { worker: worker ?? null })
}

// ################ 执行器运维(P3: 宿主机/容器/伸缩) ################

/**
 * 查询 worker 宿主机聚合状态(agent 可达性 + 容器列表)
 */
export const listWorkerHosts = () => {
  return http_base_server.get<WorkerHostView[]>('/task/workers/hosts')
}

/**
 * 登记worker宿主机(agent 地址 + Bearer token, 立即探活验证)
 */
export const createWorkerHost = (data: WorkerHostCreate) => {
  return http_base_server.post<WorkerHostView>('/task/workers/hosts', data)
}

/**
 * 更新worker宿主机登记
 */
export const updateWorkerHost = (hostId: string, data: WorkerHostUpdate) => {
  return http_base_server.patch<WorkerHostView>(`/task/workers/hosts/${hostId}`, data)
}

/**
 * 删除worker宿主机登记(不影响其上容器)
 */
export const deleteWorkerHost = (hostId: string) => {
  return http_base_server.delete<void>(`/task/workers/hosts/${hostId}`)
}

/**
 * 伸缩worker副本数(扩容同步完成; 缩容后台安全流程, 轮询 op 状态)
 */
export const scaleWorkerHost = (hostId: string, data: WorkerScaleBody) => {
  return http_base_server.post<WorkerScaleOp>(`/task/workers/hosts/${hostId}/scale`, data)
}

/**
 * 查询伸缩操作状态(phase: checking/waiting_stable/draining/scaling/done/failed/aborted)
 */
export const getScaleOp = (opId: string) => {
  return http_base_server.get<WorkerScaleOp>(`/task/workers/scale-ops/${opId}`)
}

/**
 * 单容器运维(start/stop/restart)
 * @param grace stop/restart 优雅等待秒数
 */
export const containerAction = (
  hostId: string, containerId: string, action: 'start' | 'stop' | 'restart', grace = 60,
) => {
  return http_base_server.post<Record<string, unknown>>(
    `/task/workers/hosts/${hostId}/containers/${containerId}/${action}`, { grace },
  )
}

/**
 * 优雅摘除worker节点(control.shutdown: 停止取新任务, 在途完成后退出)
 */
export const drainWorker = (workerName: string) => {
  return http_base_server.post<number>(`/task/workers/drain/${encodeURIComponent(workerName)}`)
}
