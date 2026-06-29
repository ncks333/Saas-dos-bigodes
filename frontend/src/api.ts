import axios from "axios";

const api = axios.create({baseURL: import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1"});
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
api.interceptors.response.use(undefined, async (error) => {
  const original = error.config;
  const refresh = localStorage.getItem("refresh");
  if (error.response?.status === 401 && refresh && !original._retry) {
    original._retry = true;
    const {data} = await axios.post(`${api.defaults.baseURL}/auth/refresh/`, {refresh});
    localStorage.setItem("access", data.access);
    if (data.refresh) localStorage.setItem("refresh", data.refresh);
    original.headers.Authorization = `Bearer ${data.access}`;
    return api(original);
  }
  return Promise.reject(error);
});
export default api;
