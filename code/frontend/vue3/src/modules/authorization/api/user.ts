// src/modules/authorization/api/user.ts
import { http_base_server } from '@/common/api/http';
import type { PaginationParams, PaginationResponse } from '@/common/types/common';
import type { User, UserCreate, UserUpdate } from '../types/user';

/**
 * 创建新用户
 * @param user 用户数据
 * @returns 创建的用户ID
 */
export const createUser = (user: UserCreate) => {
  return http_base_server.post<object>('/authorization/users', user);
};

/**
 * 删除用户
 * @param userId 用户ID
 */
export const deleteUser = (userId: string) => {
  return http_base_server.delete<void>(`/authorization/users/${userId}`);
};

/**
 * 更新用户
 * @param userId 用户ID
 * @param user 用户数据
 */
export const updateUser = (userId: string, user: UserUpdate) => {
  return http_base_server.put<void>(`/authorization/users/${userId}`, user);
};

/**
 * 获取单个用户详情
 * @param userId 用户ID
 * @returns 用户详情
 */
export const getUser = (userId: string) => {
  return http_base_server.get<User>(`/authorization/users/${userId}`);
};

/** 用户列表扩展过滤参数(与后端 /users/list 查询参数对齐) */
export interface UserListParams extends PaginationParams {
  /** 用户名模糊搜索 */
  username?: string;
  /** 昵称模糊搜索 */
  nickname?: string;
  /** 状态过滤 */
  is_active?: boolean;
}

/**
 * 分页查询用户列表(支持用户名/昵称模糊搜索)
 * @param params 分页参数(可带过滤字段)
 * @returns 分页响应结果
 */
export const listUsers = (params: UserListParams) => {
  // 接口无索引签名, 经 unknown 断言为 http 层的 query 参数映射类型(字段均为标量)
  return http_base_server.get<PaginationResponse<User>>('/authorization/users/list', {
    params: params as unknown as Record<string, string | number | boolean | null | undefined>,
  });
};

/**
 * 用户认证
 * @param username 用户名
 * @param password 密码
 * @returns 认证成功的用户信息
 */
export const authenticateUser = (username: string, password: string) => {
  return http_base_server.post<User>('/authorization/users/authenticate', {
    username,
    password
  });
};