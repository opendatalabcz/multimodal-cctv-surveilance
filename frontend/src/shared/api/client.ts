import axios from 'axios'

export const apiClient = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (!axios.isAxiosError(error)) {
      return Promise.reject(error)
    }
    if (!error.response) {
      return Promise.reject(new Error('Cannot reach the agent API. Is it running on port 8000?'))
    }
    const detail = (error.response.data as { detail?: unknown } | undefined)?.detail
    if (typeof detail === 'string' && detail.length > 0) {
      return Promise.reject(new Error(detail))
    }
    return Promise.reject(error)
  },
)
