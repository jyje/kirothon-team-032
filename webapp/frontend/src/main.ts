import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import '@fontsource/rubik/500.css'
import '@fontsource/rubik/700.css'
import '@fontsource/rubik-mono-one/400.css'
import '@fontsource/permanent-marker/400.css'
import '@design/tokens.css'
import './styles/base.css'
import './styles/components.css'

createApp(App).use(router).mount('#app')
