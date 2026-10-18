import axios from 'axios';

const service = axios.create({
  baseURL: process.env.VUE_APP_API_BASE || '/api',
  timeout: 10000,
});

service.interceptors.request.use(
  (config) => {
    config.headers.Authorization = `Bearer ${localStorage.getItem('token') || ''}`;
    return config;
  },
  (error) => Promise.reject(error)
);

service.interceptors.response.use(
  (response) => response.data,
  (error) => Promise.reject(error)
);

export default service;
