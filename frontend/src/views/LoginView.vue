<template>
  <div class="d-flex min-vh-100 align-items-center justify-content-center" style="background:linear-gradient(135deg,#1e3a5f,#2563eb)">
    <div class="card p-4" style="width:380px">
      <h4 class="text-center fw-bold mb-3">Placement Portal</h4>
      <input v-model="username" class="form-control mb-2" placeholder="Username">
      <input v-model="password" type="password" class="form-control mb-3" placeholder="Password">
      <div v-if="error" class="alert alert-danger py-2 small">{{ error }}</div>
      <button class="btn btn-primary w-100" @click="login" :disabled="loading">Login</button>
      <p class="text-center mt-3 small">No account? <a href="/register">Register</a></p>
    </div>
  </div>
</template>
<script setup>
import { ref } from 'vue'
const username = ref('admin'), password = ref(''), error = ref(''), loading = ref(false)
async function login() {
  loading.value = true; error.value = ''
  try {
    const r = await fetch('/api/auth/login', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({username: username.value, password: password.value}) })
    const data = await r.json()
    if (!r.ok) throw new Error(data.error)
    localStorage.setItem('pp_token', data.token)
    window.location.href = '/'
  } catch(e) { error.value = e.message }
  loading.value = false
}
</script>
