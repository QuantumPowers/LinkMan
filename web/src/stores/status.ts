import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

export interface ServerStatus {
  status: string
  uptime: number
  uptime_str: string
  connections: number
  total_connections: number
  cpu_percent: number
  memory_percent: number
}

export interface TrafficStats {
  total_mb: number
  total_gb: number
  limit_mb: number
  remaining_mb: number
  client_count: number
}

export interface Device {
  device_id: string
  name: string
  status: string
  last_seen: number
  total_bytes: number
}

export const useStatusStore = defineStore('status', () => {
  const status = ref<ServerStatus | null>(null)
  const traffic = ref<TrafficStats | null>(null)
  const devices = ref<Device[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  let pollingInterval: number | null = null

  const isConnected = computed(() => status.value?.status === 'running')

  async function fetchStatus() {
    try {
      const [statusRes, trafficRes, devicesRes] = await Promise.all([
        axios.get('/api/status'),
        axios.get('/api/traffic'),
        axios.get('/api/devices'),
      ])
      
      status.value = statusRes.data
      traffic.value = trafficRes.data
      devices.value = devicesRes.data.devices
      error.value = null
    } catch (e: any) {
      error.value = e.message
    }
  }

  function startPolling(interval = 5000) {
    if (pollingInterval) {
      clearInterval(pollingInterval)
    }
    
    fetchStatus()
    pollingInterval = window.setInterval(fetchStatus, interval)
  }

  function stopPolling() {
    if (pollingInterval) {
      clearInterval(pollingInterval)
      pollingInterval = null
    }
  }

  async function removeDevice(deviceId: string) {
    try {
      await axios.delete(`/api/devices/${deviceId}`)
      devices.value = devices.value.filter(d => d.device_id !== deviceId)
    } catch (e: any) {
      error.value = e.message
    }
  }

  return {
    status,
    traffic,
    devices,
    loading,
    error,
    isConnected,
    fetchStatus,
    startPolling,
    stopPolling,
    removeDevice,
  }
})
