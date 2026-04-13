<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'

interface TopClient {
  client_id: string
  total_mb: number
  total_gb: number
}

const topClients = ref<TopClient[]>([])
const trafficStats = ref<any>(null)
const loading = ref(true)

onMounted(async () => {
  try {
    const [topRes, statsRes] = await Promise.all([
      axios.get('/api/traffic/top'),
      axios.get('/api/traffic/report'),
    ])
    topClients.value = topRes.data
    trafficStats.value = statsRes.data
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="traffic">
    <h1 class="page-title">Traffic Statistics</h1>
    
    <div class="stats-grid">
      <div class="card stat-card">
        <div class="stat-icon" style="background: #dbeafe; color: #2563eb;">📊</div>
        <div class="stat-content">
          <h3>{{ trafficStats?.total_gb?.toFixed(2) || 0 }} GB</h3>
          <p>Total Traffic</p>
        </div>
      </div>
      
      <div class="card stat-card">
        <div class="stat-icon" style="background: #dcfce7; color: #16a34a;">📱</div>
        <div class="stat-content">
          <h3>{{ trafficStats?.client_count || 0 }}</h3>
          <p>Active Clients</p>
        </div>
      </div>
      
      <div class="card stat-card">
        <div class="stat-icon" style="background: #fef3c7; color: #d97706;">⚡</div>
        <div class="stat-content">
          <h3>{{ trafficStats?.remaining_mb?.toFixed(0) || '∞' }} MB</h3>
          <p>Remaining</p>
        </div>
      </div>
    </div>
    
    <div class="card">
      <div class="card-header">
        <h2 class="card-title">Top Clients by Traffic</h2>
      </div>
      <table class="table">
        <thead>
          <tr>
            <th>Rank</th>
            <th>Client ID</th>
            <th>Traffic (MB)</th>
            <th>Traffic (GB)</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(client, index) in topClients" :key="client.client_id">
            <td>{{ index + 1 }}</td>
            <td><code>{{ client.client_id }}</code></td>
            <td>{{ client.total_mb.toFixed(2) }}</td>
            <td>{{ client.total_gb.toFixed(3) }}</td>
          </tr>
          <tr v-if="!topClients.length && !loading">
            <td colspan="4" style="text-align: center; color: var(--text-secondary); padding: 40px;">
              No traffic data available
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.traffic {
  max-width: 1000px;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  margin-bottom: 24px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

code {
  background: var(--bg-secondary);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
}
</style>
