<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, withBase } from 'vitepress'

const props = defineProps<{
  readmeRoute?: string
  planRoute?: string
}>()

const route = useRoute()

const tabs = computed(() => {
  const items = []
  if (props.readmeRoute) items.push({ key: 'readme', text: '需求概述', route: props.readmeRoute })
  if (props.planRoute) items.push({ key: 'plan', text: '方案', route: props.planRoute })
  return items
})

function normalizePath(value: string): string {
  if (!value) return ''
  const noQuery = value.split(/[?#]/)[0] || ''
  const noHtml = noQuery.replace(/\.html$/i, '')
  if (noHtml.endsWith('/')) return noHtml.slice(0, -1)
  return noHtml
}

function isActive(targetRoute: string): boolean {
  const current = normalizePath(route.path)
  const rawTarget = normalizePath(targetRoute)
  const basedTarget = normalizePath(withBase(targetRoute))
  return current === rawTarget || current === basedTarget
}
</script>

<template>
  <div v-if="tabs.length > 1" class="issue-switch">
    <a
      v-for="tab in tabs"
      :key="tab.key"
      :href="withBase(tab.route)"
      :aria-current="isActive(tab.route) ? 'page' : undefined"
      :class="['switch-tab', { active: isActive(tab.route) }]"
    >
      {{ tab.text }}
    </a>
  </div>
</template>

<style scoped>
.issue-switch {
  display: inline-flex;
  gap: 0.3rem;
  margin: 0 0 1rem;
  padding: 0.2rem;
  border-radius: 999px;
  background: var(--vp-c-bg-soft);
  border: 1px solid var(--vp-c-divider);
}

.switch-tab {
  border-radius: 999px;
  padding: 0.22rem 0.7rem;
  text-decoration: none;
  font-size: 0.78rem;
  color: var(--vp-c-text-2);
  transition: all 0.15s;
}

.switch-tab.active {
  color: var(--vp-c-brand-1);
  background: var(--vp-c-bg);
  border: 1px solid var(--vp-c-brand-1);
}
</style>
