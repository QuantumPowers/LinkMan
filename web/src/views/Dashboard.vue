<script setup lang="ts">
import { computed } from 'vue'
import { useStatusStore } from '@/stores/status'

const statusStore = useStatusStore()

const trafficPercent = computed(() => {
  if (!statusStore.traffic || statusStore.traffic.limit_mb === 0) return 0
  return Math.min(100, (statusStore.traffic.total_mb / statusStore.traffic.limit_mb) * 100)
})

const formatBytes = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}
</script>

<template>
  <div class="dashboard">
    <h1 class="page-title">Dashboard</h1>
    
    <div v-if="statusStore.error" class="error-banner">
      {{ statusStore.error }}
    </div>
    
    <div class="stats-grid">
      <div class="card stat-card">
        <div class="stat-icon" style="background: #dbeafe; color: #2563eb;">📊</div>
        <div class="stat-content">
          <h3>{{ statusStore.status?.connections || 0 }}</h3>
          <p>Active Connections</p>
        </div>
      </div>
      
      <div class="card stat-card">
        <div class="stat-icon" style="background: #dcfce7; color: #16a34a;">📱</div>
        <div class="stat-content">
          <h3>{{ statusStore.devices?.length || 0 }}</h3>
          <p>Connected Devices</p>
        </div>
      </div>
      
      <div class="card stat-card">
        <div class="stat-icon" style="background: #fef3c7; color: #d97706;">📈</div>
        <div class="stat-content">
          <h3>{{ statusStore.traffic?.total_gb?.toFixed(2) || 0 }} GB</h3>
          <p>Total Traffic</p>
        </div>
      </div>
      
      <div class="card stat-card">
        <div class="stat-icon" style="background: #f3e8ff; color: #9333ea;">⏱️</div>
        <div class="stat-content">
          <h3>{{ statusStore.status?.uptime_str || '0s' }}</h3>
          <p>Server Uptime</p>
        </div>
      </div>
    </div>
    
    <div class="content-grid">
      <div class="card">
        <div class="card-header">
          <h2 class="card-title">Traffic Usage</h2>
          <span class="badge" :class="trafficPercent > 80 ? 'badge-danger' : 'badge-success'">
            {{ trafficPercent.toFixed(1) }}%
          </span>
        </div>
        <div class="progress-bar">
          <div 
            class="progress-bar-fill" 
            :style="{ 
              width: trafficPercent + '%',
              background: trafficPercent > 80 ? '#ef4444' : '#22c55e'
            }"
          ></div>
        </div>
        <div class="traffic-info">
          <span>Used: {{ statusStore.traffic?.total_mb?.toFixed(2) || 0 }} MB</span>
          <span v-if="statusStore.traffic?.limit_mb">
            Limit: {{ statusStore.traffic.limit_mb }} MB
          </span>
          <span v-else>Unlimited</span>
        </div>
      </div>
      
      <div class="card">
        <div class="card-header">
          <h2 class="card-title">Server Resources</h2>
        </div>
        <div class="resource-list">
          <div class="resource-item">
            <span class="resource-label">CPU Usage</span>
            <div class="progress-bar">
              <div 
                class="progress-bar-fill" 
                :style="{ 
                  width: (statusStore.status?.cpu_percent || 0) + '%',
                  background: (statusStore.status?.cpu_percent || 0) > 80 ? '#ef4444' : '#3b82f6'
                }"
              ></div>
            </div>
            <span class="resource-value">{{ (statusStore.status?.cpu_percent || 0).toFixed(1) }}%</span>
          </div>
          <div class="resource-item">
            <span class="resource-label">Memory Usage</span>
            <div class="progress-bar">
              <div 
                class="progress-bar-fill" 
                :style="{ 
                  width: (statusStore.status?.memory_percent || 0) + '%',
                  background: (statusStore.status?.memory_percent || 0) > 80 ? '#ef4444' : '#3b82f6'
                }"
              ></div>
            </div>
            <span class="resource-value">{{ (statusStore.status?.memory_percent || 0).toFixed(1) }}%</span>
          </div>
        </div>
      </div>
    </div>
    
    <div class="card">
      <div class="card-header">
        <h2 class="card-title">Recent Devices</h2>
        <router-link to="/devices" class="btn btn-primary">View All</router-link>
      </div>
      <table class="table">
        <thead>
          <tr>
            <th>Device</th>
            <th>Status</th>
            <th>Traffic</th>
            <th>Last Seen</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="device in statusStore.devices?.slice(0, 5)" :key="device.device_id">
            <td>{{ device.name }}</td>
            <td>
              <span class="badge" :class="device.status === 'online' ? 'badge-success' : 'badge-warning'">
                {{ device.status }}
              </span>
            </td>
            <td>{{ formatBytes(device.total_bytes) }}</td>
            <td>{{ new Date(device.last_seen * 1000).toLocaleString() }}</td>
          </tr>
          <tr v-if="!statusStore.devices?.length">
            <td colspan="4" style="text-align: center; color: var(--text-secondary);">
              No devices connected
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.dashboard {
  max-width: 1200px;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  margin-bottom: 24px;
}

.error-banner {
  background: #fee2e2;
  color: #991b1b;
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 24px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.content-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.traffic-info {
  display: flex;
  justify-content: space-between;
  margin-top: 12px;
  font-size: 14px;
  color: var(--text-secondary);
}

.resource-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.resource-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.resource-label {
  width: 100px;
  font-size: 14px;
  color: var(--text-secondary);
}

.resource-value {
  width: 60px;
  text-align: right;
  font-size: 14px;
  font-weight: 500;
}

.resource-item .progress-bar {
  flex: 1;
}
</style>
