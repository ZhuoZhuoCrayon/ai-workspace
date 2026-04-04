import { defineConfig } from 'vitepress'
import fs from 'node:fs'
import path from 'node:path'

const sidebarPath = path.resolve(import.meta.dirname, 'sidebar.generated.json')
const sidebar = fs.existsSync(sidebarPath) ? JSON.parse(fs.readFileSync(sidebarPath, 'utf-8')) : {}

const basePath = process.env.VITE_BASE_PATH || '/'

export default defineConfig({
  title: 'Knowledge Portal',
  description: 'AI 工作区知识资产可视化',
  base: basePath,
  lang: 'zh-CN',

  head: [
    ['link', { rel: 'icon', type: 'image/svg+xml', href: `${basePath}favicon.svg` }],
  ],

  themeConfig: {
    logo: '/favicon.svg',
    siteTitle: 'Knowledge',

    nav: [
      { text: '首页', link: '/' },
      { text: '项目', link: '/projects' },
      { text: '标签', link: '/tags' },
    ],

    sidebar,

    outline: {
      level: [2, 3],
      label: '目录',
    },

    search: {
      provider: 'local',
      options: {
        translations: {
          button: { buttonText: '搜索文档', buttonAriaLabel: '搜索' },
          modal: {
            noResultsText: '没有找到结果',
            resetButtonTitle: '重置搜索',
            footer: { selectText: '选择', navigateText: '切换', closeText: '关闭' },
          },
        },
      },
    },

    docFooter: { prev: '上一篇', next: '下一篇' },
    darkModeSwitchLabel: '主题',
    sidebarMenuLabel: '菜单',
    returnToTopLabel: '回到顶部',
    lastUpdated: { text: '最后更新' },

    socialLinks: [
      { icon: 'github', link: 'https://github.com/ZhuoZhuoCrayon/ai-workspace' },
    ],
  },

  markdown: {
    lineNumbers: true,
  },

  vite: {
    resolve: {
      preserveSymlinks: true,
    },
  },

  ignoreDeadLinks: true,
})
