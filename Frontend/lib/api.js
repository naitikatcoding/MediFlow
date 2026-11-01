const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

async function request(endpoint, options = {}) {
  // Use /api/v1 as canonical API version prefix
  const url = `${API_BASE}/api/v1${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {})
  };

  try {
    const res = await fetch(url, { ...options, headers });
    if (!res.ok) {
      const errorBody = await res.json().catch(() => ({ detail: res.statusText }));
      let errorMsg = `API request failed with status ${res.status}`;
      if (typeof errorBody.detail === 'string') {
        errorMsg = errorBody.detail;
      } else if (errorBody.detail?.message) {
        errorMsg = errorBody.detail.message;
      } else if (errorBody.error?.message) {
        errorMsg = errorBody.error.message;
      } else if (errorBody.detail) {
        errorMsg = JSON.stringify(errorBody.detail);
      }
      const err = new Error(errorMsg);
      err.data = errorBody;
      throw err;
    }
    return await res.json();
  } catch (err) {
    console.error(`API Error on ${endpoint}:`, err);
    throw err;
  }

}

export const api = {
  // System Health & Connectivity
  getHealth: () => request('/health'),
  getOverview: () => request('/dashboard/overview'),
  
  // Facilities & Products Catalogue
  getFacilities: () => request('/facilities'),
  getProducts: (storage, search) => {
    const params = new URLSearchParams();
    if (storage) params.append('storage', storage);
    if (search) params.append('search', search);
    const qs = params.toString();
    return request(`/products${qs ? `?${qs}` : ''}`);
  },
  getProductBatches: (productId) => request(`/products/${productId}/batches`),
  getBatchDetail: (batchId) => request(`/batches/${batchId}`),
  checkBatchEligibility: (batchId, destinationFacilityId) => {
    const qs = destinationFacilityId ? `?destination_facility_id=${destinationFacilityId}` : '';
    return request(`/batches/${batchId}/eligibility${qs}`);
  },
  
  // Inventory & Ledger Management
  getInventory: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/inventory${qs ? `?${qs}` : ''}`);
  },
  getInventorySummary: (facilityId) => 
    request(`/inventory/summary${facilityId ? `?facility_id=${facilityId}` : ''}`),
  getFacilityProductDetail: (facilityId, productId) => 
    request(`/inventory/${facilityId}/${productId}`),
  recordAdjustment: (data) => 
    request('/inventory/adjustments', { method: 'POST', body: JSON.stringify(data) }),
  allocateFefo: (data) => 
    request('/inventory/fefo-allocate', { method: 'POST', body: JSON.stringify(data) }),
  reconcileFacility: (facilityId) => 
    request(`/inventory/reconciliation/${facilityId}`),
  getLedger: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/inventory/ledger${qs ? `?${qs}` : ''}`);
  },

  // CSV Import Jobs
  importInventoryCsv: async (formData) => {
    const url = `${API_BASE}/api/v1/imports`;
    const res = await fetch(url, {
      method: 'POST',
      body: formData
    });
    if (!res.ok) {
      const errorBody = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(errorBody.error?.message || errorBody.detail || 'Import failed');
    }
    return await res.json();
  },
  getImportJobs: (facilityId) => 
    request(`/imports${facilityId ? `?facility_id=${facilityId}` : ''}`),
  getImportJobErrors: (jobId) => 
    request(`/imports/${jobId}/errors`),

  // Forecasts & Risks
  getForecast: (facilityId, productId, horizonDays = 30) => 
    request(`/forecasts?facility_id=${facilityId}&product_id=${productId}&horizon_days=${horizonDays}`),
  runForecast: (data = {}) => 
    request('/forecasts/run', { method: 'POST', body: JSON.stringify(data) }),
  getRisks: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/risks${qs ? `?${qs}` : ''}`);
  },
  getRiskDetail: (riskId) => 
    request(`/risks/${riskId}`),
  getRisksSummary: () => 
    request('/risks/summary'),
  getDashboardRisksSummary: () => 
    request('/dashboard/risks-summary'),

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
  cancelTransfer: (transferId, data) => 
    request(`/transfers/${transferId}/cancel`, { method: 'POST', body: JSON.stringify(data) }),
  expireTransfer: (transferId, data = {}) => 
    request(`/transfers/${transferId}/expire`, { method: 'POST', body: JSON.stringify(data) }),
  generateTransferLabels: (transferId, actorUserId) => 
    request(`/qr/transfers/${transferId}/generate-labels`, { method: 'POST', body: JSON.stringify({ actor_user_id: actorUserId }) }),
  getTransferLabels: (transferId) => request(`/qr/transfers/${transferId}/labels`),
  updateTransferState: (transferId, data) => 
    request(`/transfers/${transferId}/state`, { method: 'POST', body: JSON.stringify(data) }),
  generateQRImage: (token) => request(`/qr/generate-image?token=${encodeURIComponent(token)}`),
  submitQRScan: (data) => request('/qr/scan', { method: 'POST', body: JSON.stringify(data) }),
  getDemoTokens: () => request('/qr/demo-tokens'),

  // Multi-Agent Workflow & Memory
  runAgentCycle: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/agent/run-cycle${qs ? `?${qs}` : ''}`, { method: 'POST' });
  },
  getAgentRuns: (limit = 20) => request(`/agent/runs?limit=${limit}`),
  getAgentRunDetail: (workflowId) => request(`/agent/runs/${workflowId}`),
  resumeWorkflow: (workflowId) => request(`/agent/resume/${workflowId}`, { method: 'POST' }),
  getAgentSystemStatus: () => request('/agent/status'),
  getAgentTraces: (facilityId) => 
    request(`/agent/traces${facilityId ? `?facility_id=${facilityId}` : ''}`),

  // Inventory operations assistant
  askInventoryAssistant: (data) =>
    request('/chat', { method: 'POST', body: JSON.stringify(data) }),

  // Demo Control & Audit
  resetDemo: () => request('/demo/reset', { method: 'POST' }),
  simulateStockChange: (data) => request('/demo/simulate-stock-change', { method: 'POST', body: JSON.stringify(data) }),
  getDemoContext: () => request('/demo/context'),
  getAuditEvents: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/audit/events${qs ? `?${qs}` : ''}`);
  }
};
