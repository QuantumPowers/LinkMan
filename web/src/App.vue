<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useStatusStore } from './stores/status'
import Sidebar from './components/Sidebar.vue'

const statusStore = useStatusStore()
const sidebarCollapsed = ref(false)

onMounted(() => {
  statusStore.startPolling()
})
</script>

<template>
  <div class="app-container">
    <Sidebar :collapsed="sidebarCollapsed" @toggle="sidebarCollapsed = !sidebarCollapsed" />
    <main class="main-content" :class="{ collapsed: sidebarCollapsed }">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.app-container {
  display: flex;
  min-height: 100vh;
}

.main-content {
  flex: 1;
  margin-left: 240px;
  padding: 24px;
  transition: margin-left 0.3s ease;
  background: #f5f7fa;
}

.main-content.collapsed {
  margin-left: 64px;
}
</style>
