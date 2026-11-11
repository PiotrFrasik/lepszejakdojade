import './assets/main.css'

import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import { getCurrentLocale, i18n, syncDocumentLang } from './i18n'
import router from './router'

syncDocumentLang(getCurrentLocale())

const app = createApp(App)

app.use(createPinia())
app.use(i18n)
app.use(router)

app.mount('#app')
