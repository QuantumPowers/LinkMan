<script setup lang="ts">
import { useStatusStore } from '@/stores/status'

const statusStore = useStatusStore()

const formatBytes = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

const removeDevice = async (deviceId: string) => {
  if (confirm('Are you sure you want to remove this device?')) {
    await statusStore.removeDevice(deviceId)
  }
}
</script>

<template>
  <div class="devices">
    <div class="page-header">
      <h1 class="page-title">Devices</h1>
      <div class="header-stats">
        <span class="stat">{{ statusStore.devices?.length || 0 }} Total</span>
        <span class="stat">{{ statusStore.devices?.filter(d => d.status === 'online').length || 0 }} Online</span>
      </div>
    </div>
    
    <div class="card">
      <table class="table">
        <thead>
          <tr>
            <th>Device ID</th>
            <th>Name</th>
            <th>Status</th>
            <th>Traffic</th>
            <th>Last Seen</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="device in statusStore.devices" :key="device.device_id">
            <td><code>{{ device.device_id.slice(0, 8) }}...</code></td>
            <td>{{ device.name }}</td>
            <td>
              <span class="badge" :class="device.status === 'online' ? 'badge-success' : 'badge-warning'">
                {{ device.status }}
              </span>
            </td>
            <td>{{ formatBytes(device.total_bytes) }}</td>
            <td>{{ new Date(device.last_seen * 1000).toLocaleString() }}</td>
            <td>
              <button class="btn btn-danger" @click="removeDevice(device.device_id)">
                Remove
              </button>
            </td>
          </tr>
          <tr v-if="!statusStore.devices?.length">
            <td colspan="6" style="text-align: center; color: var(--text-secondary); padding: 40px;">
              No devices registered
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.devices {
  max-width: 1000px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
}

.header-stats {
  display: flex;
  gap: 16px;
}

.stat {
  padding: 6px 12px;
  background: var(--bg-secondary);
  border-radius: 6px;
  font-size: 14px;
  color: var(--text-secondary);
}

code {
  background: var(--bg-secondary);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
}
</style>
