const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

async function request(endpoint, options = {}) {
  const url = `${API_BASE}/api${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {})
  };

  try {
    const res = await fetch(url, { ...options, headers });
    if (!res.ok) {
      const errorBody = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(errorBody.detail || `API request failed with status ${res.status}`);
    }
    return await res.json();
  } catch (err) {
    console.error(`API Error on ${endpoint}:`, err);
    throw err;
  }
}

export const api = {
  // Dashboard & Health
  getHealth: () => request('/health'),
  getOverview: () => request('/dashboard/overview'),
  
  // Facilities & Products
  getFacilities: () => request('/facilities'),
  getProducts: (storage) => request(`/products${storage ? `?storage=${storage}` : ''}`),
  getProductBatches: (productId) => request(`/products/${productId}/batches`),
  
  // Inventory & Ledger
  getInventory: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/inventory${qs ? `?${qs}` : ''}`);
  },
  getLedger: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/inventory/ledger${qs ? `?${qs}` : ''}`);
  },

  // Forecasts & Risks
  getForecast: (facilityId, productId, horizonDays = 30) => 
    request(`/forecasts?facility_id=${facilityId}&product_id=${productId}&horizon_days=${horizonDays}`),
  getRisks: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/risks${qs ? `?${qs}` : ''}`);
  },

  // Opportunities, Proposals & Approvals
  getOpportunities: (productId) => 
    request(`/proposals/opportunities${productId ? `?product_id=${productId}` : ''}`),
  getProposals: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/proposals${qs ? `?${qs}` : ''}`);
  },
  createProposal: (data) => request('/proposals', { method: 'POST', body: JSON.stringify(data) }),
  recordApproval: (proposalId, data) => 
    request(`/approvals/${proposalId}`, { method: 'POST', body: JSON.stringify(data) }),

  // Transfers & QR Verification
  getTransfers: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/transfers${qs ? `?${qs}` : ''}`);
  },
  getTransferDetails: (transferId) => request(`/transfers/${transferId}`),
  generateQRImage: (token) => request(`/qr/generate-image?token=${encodeURIComponent(token)}`),
  submitQRScan: (data) => request('/qr/scan', { method: 'POST', body: JSON.stringify(data) }),
  getDemoTokens: () => request('/qr/demo-tokens'),

  // Multi-Agent Workflow & Memory
  runAgentCycle: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/agent/run-cycle${qs ? `?${qs}` : ''}`, { method: 'POST' });
  },
  getAgentTraces: (facilityId) => 
    request(`/agent/traces${facilityId ? `?facility_id=${facilityId}` : ''}`),

  // Demo Control & Audit
  resetDemo: () => request('/demo/reset', { method: 'POST' }),
  simulateStockChange: (data) => request('/demo/simulate-stock-change', { method: 'POST', body: JSON.stringify(data) }),
  getDemoContext: () => request('/demo/context'),
  getAuditEvents: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/audit/events${qs ? `?${qs}` : ''}`);
  }
};

