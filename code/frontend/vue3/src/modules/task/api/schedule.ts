// 周期调度 API(REQ-012 定时任务: 调度定义 CRUD / 立即触发 / cron 预置)
import { http_base_server } from '@/common/api/http'
import type { PaginationParams, PaginationResponse } from '@/common/types/common'
import type { CronPreset, TaskSchedule, TaskScheduleSave, TaskScheduleTriggerResult } from '../types'

/** 调度列表过滤参数 */
export type ScheduleListParams = PaginationParams & {
  /** 调度名称模糊搜索 */
  keyword?: string
  /** 启停过滤 */
  enabled?: boolean
  /** 任务类型过滤 */
  task_type?: string
}

/**
 * cron 快捷表达式预置(创建对话框渲染快捷选项)
 */
export const getCronPresets = () => {
  return http_base_server.get<CronPreset[]>('/task/schedules/presets')
}

/**
 * 分页查询调度列表(含下次触发与最近执行快照)
 * @param params 分页与过滤参数
 */
export const listSchedules = (params: ScheduleListParams) => {
  return http_base_server.get<PaginationResponse<TaskSchedule>>('/task/schedules/list', { params })
}

/**
 * 创建调度(cron/间隔二选一, 创建即热生效)
 * @param data 调度定义
 */
export const createSchedule = (data: TaskScheduleSave) => {
  return http_base_server.post<TaskSchedule>('/task/schedules', data)
}

/**
 * 修改调度(启停/改周期即时热生效)
 * @param id 调度ID
 * @param data 调度定义(全量字段)
 */
export const updateSchedule = (id: number, data: TaskScheduleSave) => {
  return http_base_server.put<TaskSchedule>(`/task/schedules/${id}`, data)
}

/**
 * 删除调度定义(已派发任务不受影响)
 * @param id 调度ID
 */
export const deleteSchedule = (id: number) => {
  return http_base_server.delete<void>(`/task/schedules/${id}`)
}

/**
 * 手动立即触发一次(不影响周期节奏, 用于验证任务定义)
 * @param id 调度ID
 */
export const triggerSchedule = (id: number) => {
  return http_base_server.post<TaskScheduleTriggerResult>(`/task/schedules/${id}/trigger`)
}
