import { ref, watch } from 'vue'
import { logInfo } from '../console/appConsole'

/** Width of the left model-management sidebar. */
export const SIDEBAR_WIDTH = 320
/** Width of the right component-tree panel. */
export const TREE_WIDTH = 340
/** Height of the bottom console panel when it is open. */
export const CONSOLE_HEIGHT = 200
/** Height of the strip that stays visible when the console is collapsed. */
export const CONSOLE_HANDLE_HEIGHT = 26

const LAYOUT_KEY = 'bim-earth-layout'

interface StoredLayout {
  modelPanelOpen?: boolean
  consoleOpen?: boolean
  treePanelOpen?: boolean
}

/** Reads the persisted panel visibility flags. */
const readStoredLayout = (): StoredLayout => {
  try {
    const saved = localStorage.getItem(LAYOUT_KEY)
    return saved ? (JSON.parse(saved) as StoredLayout) : {}
  } catch (error) {
    logInfo('本地存储不可用，面板展开状态未恢复', error)
    return {}
  }
}

const storedLayout = readStoredLayout()

const modelPanelOpen = ref(storedLayout.modelPanelOpen !== false)
const consoleOpen = ref(storedLayout.consoleOpen !== false)
const treePanelOpen = ref(storedLayout.treePanelOpen !== false)

/** Persists the panel visibility flags so a reload restores the layout. */
const persistLayout = () => {
  try {
    localStorage.setItem(
      LAYOUT_KEY,
      JSON.stringify({
        modelPanelOpen: modelPanelOpen.value,
        consoleOpen: consoleOpen.value,
        treePanelOpen: treePanelOpen.value,
      }),
    )
  } catch (error) {
    logInfo('本地存储不可用，面板展开状态未保存', error)
  }
}

watch([modelPanelOpen, consoleOpen, treePanelOpen], persistLayout)

/** Shares panel visibility between the sidebar, console, and viewer layout. */
export const useLayoutState = () => ({
  modelPanelOpen,
  consoleOpen,
  treePanelOpen,
})
