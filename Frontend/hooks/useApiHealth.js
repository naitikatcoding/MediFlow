'use client';
import { useState, useEffect, useCallback } from 'react';
import { api } from '../lib/api';

export function useApiHealth(pollIntervalMs = 15000) {
  const [health, setHealth] = useState(null);
  const [status, setStatus] = useState('checking'); // 'checking' | 'healthy' | 'degraded' | 'offline'
  const [error, setError] = useState(null);
  const [lastChecked, setLastChecked] = useState(null);

  const checkHealth = useCallback(async () => {
    try {
      const data = await api.getHealth();
      setHealth(data);
      setStatus(data.status === 'healthy' ? 'healthy' : 'degraded');
      setError(null);
      setLastChecked(new Date());
    } catch (err) {
      console.warn('API health check failed:', err.message);
      setStatus('offline');
      setError(err.message || 'Cannot connect to backend API');
      setLastChecked(new Date());
    }
  }, []);

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, pollIntervalMs);
    return () => clearInterval(interval);
  }, [checkHealth, pollIntervalMs]);

  return { health, status, error, lastChecked, refetch: checkHealth };
}
