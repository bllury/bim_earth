<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import {
  clearConsoleLogs,
  useAppConsole,
  type ConsoleLogLevel,
} from '../features/console/appConsole'
import {
  CONSOLE_HANDLE_HEIGHT,
  CONSOLE_HEIGHT,
  useLayoutState,
} from '../features/layout/useLayoutState'

const { entries } = useAppConsole()
const { consoleOpen } = useLayoutState()

const bodyRef = ref<HTMLElement | null>(null)
const onlyErrors = ref(false)

const levelLabels: Record<ConsoleLogLevel, string> = {
  info: 'INFO',
  warn: 'WARN',
  error: 'ERROR',
}

/** Entries currently rendered, honoring the error-only filter. */
const visibleEntries = computed(() =>
  onlyErrors.value
    ? entries.value.filter((entry) => entry.level === 'error')
    : entries.value,
)

const errorCount = computed(
  () => entries.value.filter((entry) => entry.level === 'error').length,
)

watch(
  () => visibleEntries.value.length,
  async () => {
    await nextTick()
    const body = bodyRef.value
    if (body) {
      body.scrollTop = body.scrollHeight
    }
  },
  { immediate: true },
)
</script>

<template>
  <section
    class="console-panel"
    :class="{ 'is-collapsed': !consoleOpen }"
    :style="{ '--cp-height': `${CONSOLE_HEIGHT}px` }"
  >
    <div
      class="console-header"
      :style="{ height: `${CONSOLE_HANDLE_HEIGHT}px` }"
    >
      <span class="console-title">控制台</span>
      <button
        class="console-handle"
        :aria-expanded="consoleOpen"
        :title="consoleOpen ? '收起控制台' : '展开控制台'"
        @click="consoleOpen = !consoleOpen"
      >
        <svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true">
          <path
            d="M3.5 6 8 10.5 12.5 6"
            fill="none"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>
      <span v-if="entries.length" class="console-count">
        {{ entries.length }}
      </span>
      <button
        class="console-filter"
        :class="{ active: onlyErrors }"
        :title="onlyErrors ? '显示全部日志' : '只看错误'"
        @click="onlyErrors = !onlyErrors"
      >
        仅错误{{ errorCount ? ` · ${errorCount}` : '' }}
      </button>
      <button class="console-clear" @click="clearConsoleLogs">清空</button>
    </div>

    <div ref="bodyRef" class="console-body">
      <p v-if="!visibleEntries.length" class="console-empty">
        {{ onlyErrors ? '暂无错误' : '暂无输出' }}
      </p>
      <div
        v-for="entry in visibleEntries"
        :key="entry.id"
        class="console-line"
        :class="`level-${entry.level}`"
      >
        <span class="console-time">{{ entry.time }}</span>
        <span class="console-level">{{ levelLabels[entry.level] }}</span>
        <span class="console-message">
          {{ entry.message }}
          <span v-if="entry.detail" class="console-detail">
            — {{ entry.detail }}
          </span>
        </span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.console-panel {
  /* Light theme tokens; a dark theme only needs to override this block. */
  --cp-bg: #ffffff;
  --cp-fg: #24292f;
  --cp-muted: #6e7781;
  --cp-border: #e6e8eb;
  --cp-hover: #f3f4f6;
  --cp-header-bg: #fafbfc;
  --cp-info: #1a56db;
  --cp-warn: #9a6700;
  --cp-error: #c4362f;
  --cp-line-hover: #f7f8f9;
  --cp-accent-soft: #f2f7ff;
  --cp-accent-border: #c9dcfb;

  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  height: var(--cp-height);
  display: flex;
  flex-direction: column;
  background: var(--cp-bg);
  border-top: 1px solid var(--cp-border);
  color: var(--cp-fg);
  font-size: 12px;
  z-index: 1150;
  transition: transform 0.22s ease;
}

.console-panel.is-collapsed {
  transform: translateY(calc(var(--cp-height) - 26px));
}

.console-header {
  position: relative;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 10px;
  background: var(--cp-header-bg);
  border-bottom: 1px solid var(--cp-border);
}

.console-title {
  font-weight: 600;
}

.console-count {
  padding: 0 6px;
  border-radius: 8px;
  background: var(--cp-hover);
  color: var(--cp-muted);
  font-size: 11px;
}

.console-handle {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 18px;
  padding: 0;
  border: 1px solid var(--cp-border);
  border-radius: 9px;
  background: var(--cp-bg);
  color: var(--cp-muted);
  cursor: pointer;
}

.console-handle:hover {
  background: var(--cp-hover);
  color: var(--cp-fg);
}

.console-handle svg {
  transition: transform 0.22s ease;
}

.console-panel.is-collapsed .console-handle svg {
  transform: rotate(180deg);
}

.console-filter,
.console-clear {
  margin-left: auto;
  padding: 1px 8px;
  font-family: inherit;
  font-size: 11.5px;
  color: var(--cp-fg);
  background: var(--cp-bg);
  border: 1px solid var(--cp-border);
  border-radius: 4px;
  cursor: pointer;
}

.console-filter:hover,
.console-clear:hover {
  background: var(--cp-hover);
}

.console-filter.active {
  color: var(--cp-info);
  background: var(--cp-accent-soft);
  border-color: var(--cp-accent-border);
}

.console-clear {
  margin-left: 0;
}

.console-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 6px 10px 10px 10px;
  font-family: Consolas, 'Courier New', monospace;
}

.console-empty {
  margin: 4px 0 0 0;
  color: var(--cp-muted);
}

.console-line {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 1px 4px;
  border-radius: 3px;
  line-height: 1.55;
}

.console-line:hover {
  background: var(--cp-line-hover);
}

.console-time {
  flex: 0 0 auto;
  color: var(--cp-muted);
}

.console-level {
  flex: 0 0 46px;
  font-weight: 600;
}

.console-message {
  flex: 1 1 auto;
  min-width: 0;
  word-break: break-word;
}

.console-detail {
  color: var(--cp-muted);
}

.level-info .console-level {
  color: var(--cp-info);
}

.level-warn .console-level,
.level-warn .console-message {
  color: var(--cp-warn);
}

.level-error .console-level,
.level-error .console-message {
  color: var(--cp-error);
}
</style>
