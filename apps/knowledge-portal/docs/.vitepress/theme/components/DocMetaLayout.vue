<script setup lang="ts">
import DefaultTheme from 'vitepress/theme'
import { useData } from 'vitepress'
import DocMeta from './DocMeta.vue'
import IssueSwitch from './IssueSwitch.vue'

const { Layout } = DefaultTheme
const { frontmatter, page } = useData()
</script>

<template>
  <Layout>
    <template #doc-before>
      <DocMeta
        v-if="page.relativePath.startsWith('knowledge/')"
        :tags="frontmatter.tags"
        :project="page.relativePath.split('/')[1]"
        :created="frontmatter.created"
        :updated="frontmatter.updated"
      />
      <IssueSwitch
        v-if="frontmatter.issue_readme_route || frontmatter.issue_plan_route"
        :readme-route="frontmatter.issue_readme_route"
        :plan-route="frontmatter.issue_plan_route"
      />
    </template>
  </Layout>
</template>
