<script setup lang="ts">
import DefaultTheme from 'vitepress/theme'
import { useData } from 'vitepress'
import DocMeta from './DocMeta.vue'

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
    </template>
  </Layout>
</template>
