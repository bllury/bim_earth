import { createApp } from 'vue'
import App from './App.vue'
import {
  installConsoleBridge,
  installGlobalConsoleCapture,
  logError,
} from './features/console/appConsole'

installGlobalConsoleCapture()
installConsoleBridge()

const app = createApp(App)

/** Routes component-internal exceptions into the in-app console panel. */
app.config.errorHandler = (error, _instance, info) => {
  logError(`组件异常（${info}）`, error)
}

app.mount('#app')
