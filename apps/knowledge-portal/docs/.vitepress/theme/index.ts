import DefaultTheme from 'vitepress/theme'
import type { Theme } from 'vitepress'

import DocMeta from './components/DocMeta.vue'
import TagCloud from './components/TagCloud.vue'
import ActivityCalendar from './components/ActivityCalendar.vue'
import HomeDashboard from './components/HomeDashboard.vue'
import DocMetaLayout from './components/DocMetaLayout.vue'

import './style/custom.css'

export default {
  extends: DefaultTheme,
  Layout: DocMetaLayout,
  enhanceApp({ app }) {
    app.component('DocMeta', DocMeta)
    app.component('TagCloud', TagCloud)
    app.component('ActivityCalendar', ActivityCalendar)
    app.component('HomeDashboard', HomeDashboard)
  },
} satisfies Theme
