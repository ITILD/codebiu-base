<!-- 外部能力面板(REQ-018 批次 3): Skill Hub 社区包(zip 导入/删除) + MCP server 登记(反射注册 tools) -->
<template>
  <div flex flex-col gap-4>
    <!-- ============================== Skill Hub 社区包 ============================== -->
    <div>
      <div mb-3 flex flex-wrap items-center gap-2>
        <span text-sm font-medium>Skill Hub 社区包</span>
        <span text-xs text-note-sub>导入 SKILL.md 包(zip): 指令 → pack.{包}.main, 脚本 → pack.{包}.{名}</span>
        <div flex-1 />
        <el-upload
          v-if="canUpdateExternal"
          :show-file-list="false" accept=".zip" :disabled="importing"
          :before-upload="handleImportPackage"
        >
          <el-button type="primary" :loading="importing">
            <el-icon mr-1><Upload /></el-icon>导入 zip 包
          </el-button>
        </el-upload>
      </div>
      <el-table :data="packages" v-loading="packagesLoading" stripe w-full>
        <el-table-column type="expand">
          <template #default="{ row }">
            <div px-4 py-2>
              <div mb-2 text-xs text-note-sub>包内技能(注册状态)</div>
              <el-table :data="row.skills" border size="small">
                <el-table-column label="技能键" min-width="200" show-overflow-tooltip>
                  <template #default="{ row: s }">
                    <span class="font-mono text-xs">{{ s.key }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="实现类型" width="110" align="center">
                  <template #default="{ row: s }">
                    <el-tag :type="skillTypeTagType(s.skill_type)" size="small">
                      {{ skillTypeLabel(s.skill_type) }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="注册状态" width="100" align="center">
                  <template #default="{ row: s }">
                    <el-tag :type="s.registered ? 'success' : 'danger'" size="small">
                      {{ s.registered ? '已注册' : '未注册' }}
                    </el-tag>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="包" min-width="180">
          <template #default="{ row }">
            <div flex flex-col>
              <span>{{ row.name }}</span>
              <span text-xs text-note-sub>{{ row.namespace }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="version" label="版本" width="70" align="center" />
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="publishStatusTagType(row.status)" size="small">
              {{ publishStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="技能数" width="80" align="center">
          <template #default="{ row }">{{ row.skills.length }}</template>
        </el-table-column>
        <el-table-column prop="owner_user_id" label="导入者" min-width="120" show-overflow-tooltip />
        <el-table-column v-if="canUpdateExternal" label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="handleRemovePackage(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty
        v-if="!packagesLoading && !packages.length" :image-size="60"
        description="暂无社区包, 可导入 SKILL.md 格式的 zip 包"
      />
    </div>

    <!-- ============================== MCP server ============================== -->
    <div>
      <div mb-3 flex flex-wrap items-center gap-2>
        <span text-sm font-medium>MCP Server</span>
        <span text-xs text-note-sub>登记 stdio server, 连接验证后反射注册 tools 为 mcp.{名}.{工具}</span>
        <div flex-1 />
        <el-button v-if="canUpdateExternal" type="primary" @click="mcpDialogVisible = true">
          <el-icon mr-1><Plus /></el-icon>登记 Server
        </el-button>
      </div>
      <el-table :data="servers" v-loading="serversLoading" stripe w-full>
        <el-table-column type="expand">
          <template #default="{ row }">
            <div px-4 py-2>
              <div mb-2 text-xs text-note-sub>反射注册的 tools</div>
              <el-table :data="row.tools" border size="small">
                <el-table-column label="工具名" min-width="140" show-overflow-tooltip>
                  <template #default="{ row: t }">{{ t.name }}</template>
                </el-table-column>
                <el-table-column label="技能键" min-width="220" show-overflow-tooltip>
                  <template #default="{ row: t }">
                    <span class="font-mono text-xs">{{ t.key }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="注册状态" width="100" align="center">
                  <template #default="{ row: t }">
                    <el-tag :type="t.registered ? 'success' : 'danger'" size="small">
                      {{ t.registered ? '已注册' : '未注册' }}
                    </el-tag>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="Server" min-width="200">
          <template #default="{ row }">
            <span class="font-mono text-xs">{{ row.namespace }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="publishStatusTagType(row.status)" size="small">
              {{ publishStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="tools 数" width="90" align="center">
          <template #default="{ row }">{{ row.tools.length }}</template>
        </el-table-column>
        <el-table-column prop="owner_user_id" label="登记人" min-width="120" show-overflow-tooltip />
        <el-table-column v-if="canUpdateExternal" label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="handleRemoveServer(row)">
              移除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty
        v-if="!serversLoading && !servers.length" :image-size="60"
        description="暂无登记的 MCP server"
      />
    </div>

    <!-- MCP 登记对话框(名称/命令/参数 JSON/环境变量 JSON) -->
    <el-dialog v-model="mcpDialogVisible" title="登记 MCP Server" width="92%" class="max-w-[520px]">
      <el-form :model="mcpForm" label-width="92px" label-position="left" @submit.prevent>
        <el-form-item label="名称" required>
          <el-input
            v-model="mcpForm.name" maxlength="50"
            placeholder="不含 '.', 如 filesystem(命名空间 mcp.filesystem)"
          />
        </el-form-item>
        <el-form-item label="启动命令" required>
          <el-input v-model="mcpForm.command" placeholder="如 npx / uvx / python -m 形式的 stdio 启动命令" />
        </el-form-item>
        <el-form-item label="参数 (args)">
          <el-input
            v-model="mcpArgsText" type="textarea" :rows="2"
            placeholder='JSON 数组, 如 ["--port", "8080"]'
          />
        </el-form-item>
        <el-form-item label="环境变量">
          <el-input
            v-model="mcpEnvText" type="textarea" :rows="2"
            placeholder='JSON 对象, 如 {"API_KEY": "xxx"}'
          />
        </el-form-item>
        <el-alert
          title="登记时会实际连接该 server 并拉取工具清单(握手失败将拒绝登记)"
          type="info" :closable="false"
        />
      </el-form>
      <template #footer>
        <span>
          <el-button @click="mcpDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="registering" @click="handleRegisterServer">登记</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { Plus, Upload } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listSkillHubPackages, importSkillHubPackage, removeSkillHubPackage,
  listMcpServers, registerMcpServer, removeMcpServer,
} from '../api/agent'
import type { SkillHubPackage, McpServerInfo } from '../types'
import { publishStatusLabel, publishStatusTagType, skillTypeLabel, skillTypeTagType } from '../types/labels'
import { usePermission } from '@/common/composables/usePermission'

const { hasPerm } = usePermission()
/** 外部能力写操作(zip 导入/删包/登记/移除 server)与后端 agent:skill:update 对齐 */
const canUpdateExternal = computed(() => hasPerm('agent:skill:update'))

// 外部技能清单刷新回调(导入/删除后技能清单页签同步)
const emit = defineEmits<{ changed: [] }>()

// ============================== Skill Hub 社区包 ==============================
const packagesLoading = ref(false)
const packages = ref<SkillHubPackage[]>([])
const importing = ref(false)

const loadPackages = async () => {
  try {
    packagesLoading.value = true
    packages.value = await listSkillHubPackages()
  } catch (error) {
    console.error('获取社区包清单失败:', error)
    ElMessage.error('获取社区包清单失败')
  } finally {
    packagesLoading.value = false
  }
}

/** 导入 zip 包(el-upload before-upload 拦截手动提交, 返回 false 阻止默认上传) */
const handleImportPackage = async (file: File) => {
  if (!file.name.toLowerCase().endsWith('.zip')) {
    ElMessage.warning('仅支持 .zip 格式的 SKILL.md 包')
    return false
  }
  try {
    importing.value = true
    const result = await importSkillHubPackage(file)
    ElMessage.success(`已导入 ${result.skills.length} 个技能(${result.namespace}@${result.version})`)
    await loadPackages()
    emit('changed')
  } catch (error) {
    // 导入失败: 展示后端 detail(缺少 SKILL.md/包已存在/包名非法等)
    console.error('导入社区包失败:', error)
    ElMessage.error(error instanceof Error ? error.message : '导入失败')
  } finally {
    importing.value = false
  }
  return false
}

/** 删除社区包(注册表移除该包全部技能) */
const handleRemovePackage = async (row: SkillHubPackage) => {
  try {
    await ElMessageBox.confirm(
      `确定删除社区包「${row.name}」吗？删除后注册表移除该包全部技能(${row.skills.length} 个), 历史调用记录保留。`,
      '删除社区包',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    await removeSkillHubPackage(row.namespace)
    ElMessage.success('已删除')
    await loadPackages()
    emit('changed')
  } catch (error) {
    if (error !== 'cancel') console.error('删除社区包失败:', error)
  }
}

// ============================== MCP server ==============================
const serversLoading = ref(false)
const servers = ref<McpServerInfo[]>([])
const mcpDialogVisible = ref(false)
const registering = ref(false)
const mcpForm = ref({ name: '', command: '' })
// 参数/环境变量以 JSON 文本域录入(避免动态键值行的复杂度)
const mcpArgsText = ref('')
const mcpEnvText = ref('')

const loadServers = async () => {
  try {
    serversLoading.value = true
    servers.value = await listMcpServers()
  } catch (error) {
    console.error('获取 MCP server 清单失败:', error)
    ElMessage.error('获取 MCP server 清单失败')
  } finally {
    serversLoading.value = false
  }
}

/** 解析 args/env JSON 文本(空串返回 undefined) */
const parseJsonText = (text: string, label: string): unknown => {
  const trimmed = text.trim()
  if (!trimmed) return undefined
  try {
    return JSON.parse(trimmed)
  } catch {
    ElMessage.warning(`${label} 不是合法 JSON`)
    return null
  }
}

/** 登记 MCP server(连接验证 + tools 反射注册) */
const handleRegisterServer = async () => {
  const name = mcpForm.value.name.trim()
  const command = mcpForm.value.command.trim()
  if (!name || name.includes('.')) {
    ElMessage.warning('请填写名称(不含 \'.\')')
    return
  }
  if (!command) {
    ElMessage.warning('请填写启动命令')
    return
  }
  const args = parseJsonText(mcpArgsText.value, '参数(args)')
  if (args === null) return
  if (args !== undefined && !Array.isArray(args)) {
    ElMessage.warning('参数(args)需为 JSON 数组')
    return
  }
  const env = parseJsonText(mcpEnvText.value, '环境变量')
  if (env === null) return
  if (env !== undefined && (typeof env !== 'object' || Array.isArray(env))) {
    ElMessage.warning('环境变量需为 JSON 对象')
    return
  }
  try {
    registering.value = true
    const result = await registerMcpServer({
      name,
      command,
      ...(args !== undefined ? { args: args as string[] } : {}),
      ...(env !== undefined ? { env: env as Record<string, string> } : {}),
    })
    ElMessage.success(`已登记并注册 ${result.tools.length} 个工具(${result.namespace})`)
    mcpDialogVisible.value = false
    mcpForm.value = { name: '', command: '' }
    mcpArgsText.value = ''
    mcpEnvText.value = ''
    await loadServers()
    emit('changed')
  } catch (error) {
    // 登记/握手失败: 展示后端 detail(连接/握手失败/已登记等)
    console.error('登记 MCP server 失败:', error)
    ElMessage.error(error instanceof Error ? error.message : '登记失败')
  } finally {
    registering.value = false
  }
}

/** 移除 MCP server(反注册全部 tools) */
const handleRemoveServer = async (row: McpServerInfo) => {
  try {
    await ElMessageBox.confirm(
      `确定移除「${row.namespace}」吗？注册表将反注册其全部工具(${row.tools.length} 个)。`,
      '移除 MCP Server',
      { type: 'warning', confirmButtonText: '移除', cancelButtonText: '取消' },
    )
    await removeMcpServer(row.namespace)
    ElMessage.success('已移除')
    await loadServers()
    emit('changed')
  } catch (error) {
    if (error !== 'cancel') console.error('移除 MCP server 失败:', error)
  }
}

/** 加载全部(包清单 + server 清单) */
const loadAll = () => {
  loadPackages()
  loadServers()
}

// 页签 lazy 渲染: 首次挂载(=用户切入页签)即自加载, 无需父级触发
onMounted(loadAll)
</script>
