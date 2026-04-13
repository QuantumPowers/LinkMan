<script setup lang="ts">
import { ref } from 'vue'

const settings = ref({
  serverPort: 8388,
  managementPort: 8389,
  maxConnections: 1024,
  maxDevices: 5,
  trafficLimit: 0,
  warningThreshold: 1000,
})

const saving = ref(false)

const saveSettings = async () => {
  saving.value = true
  try {
    await new Promise(resolve => setTimeout(resolve, 1000))
    alert('Settings saved successfully!')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="settings">
    <h1 class="page-title">Settings</h1>
    
    <div class="card">
      <h2 class="card-title">Server Configuration</h2>
      
      <div class="form-group">
        <label>Server Port</label>
        <input type="number" v-model="settings.serverPort" class="input" />
      </div>
      
      <div class="form-group">
        <label>Management API Port</label>
        <input type="number" v-model="settings.managementPort" class="input" />
      </div>
      
      <div class="form-group">
        <label>Max Connections</label>
        <input type="number" v-model="settings.maxConnections" class="input" />
      </div>
    </div>
    
    <div class="card">
      <h2 class="card-title">Device Management</h2>
      
      <div class="form-group">
        <label>Max Devices</label>
        <input type="number" v-model="settings.maxDevices" class="input" />
        <span class="hint">Maximum number of devices that can connect</span>
      </div>
    </div>
    
    <div class="card">
      <h2 class="card-title">Traffic Management</h2>
      
      <div class="form-group">
        <label>Monthly Traffic Limit (MB)</label>
        <input type="number" v-model="settings.trafficLimit" class="input" />
        <span class="hint">Set to 0 for unlimited</span>
      </div>
      
      <div class="form-group">
        <label>Warning Threshold (MB)</label>
        <input type="number" v-model="settings.warningThreshold" class="input" />
        <span class="hint">Send warning when traffic reaches this threshold</span>
      </div>
    </div>
    
    <div class="actions">
      <button class="btn btn-primary" @click="saveSettings" :disabled="saving">
        {{ saving ? 'Saving...' : 'Save Settings' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.settings {
  max-width: 600px;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  margin-bottom: 24px;
}

.card {
  margin-bottom: 24px;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-color);
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 6px;
  color: var(--text-primary);
}

.input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  font-size: 14px;
  transition: border-color 0.2s;
}

.input:focus {
  outline: none;
  border-color: var(--primary-color);
}

.hint {
  display: block;
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 4px;
}

.actions {
  display: flex;
  justify-content: flex-end;
}
</style>
