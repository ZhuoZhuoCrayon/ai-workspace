import DefaultTheme from 'vitepress/theme'
import type { Theme } from 'vitepress'
import { inBrowser, useRoute } from 'vitepress'
import { nextTick, watch } from 'vue'

import DocMeta from './components/DocMeta.vue'
import TagCloud from './components/TagCloud.vue'
import ActivityCalendar from './components/ActivityCalendar.vue'
import HomeDashboard from './components/HomeDashboard.vue'
import DocMetaLayout from './components/DocMetaLayout.vue'

import './style/custom.css'

let mermaidLoadTask: Promise<typeof import('mermaid').default> | null = null
let mermaidRenderTask: Promise<void> | null = null

async function loadMermaid() {
  if (!mermaidLoadTask) {
    mermaidLoadTask = import('mermaid').then((module) => module.default)
  }
  return mermaidLoadTask
}

async function renderMermaidDiagrams() {
  if (!inBrowser) return
  if (mermaidRenderTask) return mermaidRenderTask

  mermaidRenderTask = (async () => {
    const mermaid = await loadMermaid()
    const isDark = document.documentElement.classList.contains('dark')

    mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'strict',
      theme: isDark ? 'dark' : 'default',
    })

    document.querySelectorAll<HTMLElement>('.vp-mermaid[data-mermaid-source]').forEach((host) => {
      host.textContent = host.dataset.mermaidSource ?? ''
    })

    const blocks = Array.from(document.querySelectorAll<HTMLElement>('.language-mermaid'))
    blocks.forEach((block) => {
      const code = block.querySelector<HTMLElement>('pre code')
      const source = code?.textContent?.trim()
      if (!source) return

      const host = document.createElement('div')
      host.className = 'mermaid vp-mermaid'
      host.dataset.mermaidSource = source
      host.textContent = source
      block.replaceWith(host)
    })

    document.querySelectorAll<HTMLElement>('pre code.language-mermaid').forEach((code) => {
      const pre = code.closest('pre')
      const source = code.textContent?.trim()
      if (!pre || !source) return

      const host = document.createElement('div')
      host.className = 'mermaid vp-mermaid'
      host.dataset.mermaidSource = source
      host.textContent = source
      pre.replaceWith(host)
    })

    const nodes = Array.from(document.querySelectorAll<HTMLElement>('.vp-mermaid'))
    if (nodes.length > 0) {
      await mermaid.run({ nodes, suppressErrors: true })
    }
  })().finally(() => {
    mermaidRenderTask = null
  })

  return mermaidRenderTask
}

export default {
  extends: DefaultTheme,
  Layout: DocMetaLayout,
  setup() {
    if (!inBrowser) return

    const route = useRoute()
    const triggerRender = () => {
      nextTick(() => {
        void renderMermaidDiagrams()
      })
    }

    watch(() => route.path, triggerRender, { immediate: true })

    const observer = new MutationObserver((mutations) => {
      if (!mutations.some((item) => item.attributeName === 'class')) return
      triggerRender()
    })
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
  },
  enhanceApp({ app }) {
    app.component('DocMeta', DocMeta)
    app.component('TagCloud', TagCloud)
    app.component('ActivityCalendar', ActivityCalendar)
    app.component('HomeDashboard', HomeDashboard)
  },
} satisfies Theme
