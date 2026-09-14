import type { Ref } from 'vue'
import {
  fetchIfcConversionStatus,
  uploadIfcFile,
} from '../../services/ifcApi'
import type { IfcConversionStatus } from '../../types/bim'

export interface IfcConversionTask {
  taskId: string
  fileName: string
  status: IfcConversionStatus
  message?: string
  error?: string
}

interface CompletedConversion {
  taskId: string
  fileName: string
  longitude: number
  latitude: number
  tilesetUrl: string
  metadataUrl?: string
  modelId?: string
  projectId?: string
  revisionId?: string
}

interface ConversionResult {
  taskId: string
  fileName: string
  longitude: number
  latitude: number
  projectId?: string
  revisionId?: string
}

  /** Manages IFC upload polling and hands completed conversions to the viewer. */
export const useIfcConversion = (
  tasks: Ref<IfcConversionTask[]>,
  onCompleted: (conversion: CompletedConversion) => Promise<void>,
) => {
  const pollingTimers = new Map<string, number>()
  const pollingTasks = new Set<string>()
  const terminalTasks = new Set<string>()

  /** Clears a pending polling timer for one conversion task. */
  const clearPollingTimer = (taskId: string) => {
    const timer = pollingTimers.get(taskId)
    if (timer !== undefined) {
      window.clearTimeout(timer)
      pollingTimers.delete(taskId)
    }
  }

  /** Applies a partial status update to a conversion task. */
  const updateTask = (taskId: string, patch: Partial<IfcConversionTask>) => {
    tasks.value = tasks.value.map((task) =>
      task.taskId === taskId ? { ...task, ...patch } : task,
    )
  }

  /** Stops polling and marks a task as terminal. */
  const stop = (taskId: string) => {
    clearPollingTimer(taskId)
    pollingTasks.delete(taskId)
    terminalTasks.add(taskId)
  }

  /** Polls the backend until an IFC conversion reaches a terminal state. */
  const poll = async ({
    taskId,
    fileName,
    longitude,
    latitude,
    projectId,
    revisionId,
  }: ConversionResult): Promise<void> => {
    if (terminalTasks.has(taskId) || pollingTasks.has(taskId)) return

    pollingTasks.add(taskId)
    try {
      const result = await fetchIfcConversionStatus(taskId)
      if (terminalTasks.has(taskId)) return
      if (result.status === 'completed') {
        stop(taskId)
        updateTask(taskId, { status: 'completed', message: result.message })

        if (!result.tilesetUrl) {
          updateTask(taskId, {
            status: 'failed',
            error: '转换服务未返回 tilesetUrl',
          })
          return
        }

        await onCompleted({
          taskId,
          fileName,
          longitude,
          latitude,
          tilesetUrl: result.tilesetUrl,
          metadataUrl: result.metadataUrl,
          modelId: result.modelId,
          projectId: result.projectId ?? projectId,
          revisionId: result.revisionId ?? revisionId,
        })
        tasks.value = tasks.value.filter((task) => task.taskId !== taskId)
        return
      }

      if (result.status === 'failed') {
        stop(taskId)
        updateTask(taskId, {
          status: 'failed',
          error: result.error ?? result.message ?? 'IFC 转换失败',
        })
        return
      }

      updateTask(taskId, { status: result.status, message: result.message })
      pollingTasks.delete(taskId)
      pollingTimers.set(
        taskId,
        window.setTimeout(() => {
          void poll({ taskId, fileName, longitude, latitude })
        }, 2000),
      )
    } catch (error) {
      if (terminalTasks.has(taskId)) return
      stop(taskId)
      updateTask(taskId, {
        status: 'failed',
        error: error instanceof Error ? error.message : '查询转换状态失败',
      })
    }
  }

  /** Uploads an IFC file and starts polling its conversion task. */
  const start = async (
    file: File,
    longitude: number,
    latitude: number,
  ): Promise<void> => {
    if (
      tasks.value.some(
        (task) =>
          task.fileName === file.name &&
          (task.status === 'pending' || task.status === 'processing'),
      )
    ) {
      return
    }

    try {
      const accepted = await uploadIfcFile(file, longitude, latitude)
      if (!tasks.value.some((task) => task.taskId === accepted.taskId)) {
        tasks.value = [
          ...tasks.value,
          {
            taskId: accepted.taskId,
            fileName: file.name,
            status: 'pending',
          },
        ]
      }
      void poll({
        taskId: accepted.taskId,
        fileName: file.name,
        longitude,
        latitude,
        projectId: accepted.projectId,
        revisionId: accepted.revisionId,
      })
    } catch (error) {
      tasks.value = [
        ...tasks.value,
        {
          taskId: `local-${Date.now()}`,
          fileName: file.name,
          status: 'failed',
          error: error instanceof Error ? error.message : 'IFC 上传失败',
        },
      ]
    }
  }

  /** Cancels all timers and clears conversion task bookkeeping. */
  const dispose = () => {
    pollingTimers.forEach((timer) => window.clearTimeout(timer))
    pollingTimers.clear()
    pollingTasks.clear()
    terminalTasks.clear()
  }

  return {
    start,
    stop,
    dispose,
  }
}
