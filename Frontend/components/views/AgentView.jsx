'use client';
import React, { useState, useEffect } from 'react';
import { 
  Bot, 
  Play, 
  RefreshCw, 
  CheckCircle2, 
  AlertTriangle, 
  Clock, 
  Layers, 
  Cpu, 
  Database, 
  Sparkles, 
  ArrowRight, 
  ShieldCheck, 
  FileText, 
  ExternalLink,
  ChevronRight,
  Info
} from 'lucide-react';
import { api } from '../../lib/api';

export function AgentView({ facilities = [], products = [], onNavigateTab }) {
  const [runs, setRuns] = useState([]);
  const [selectedRun, setSelectedRun] = useState(null);
  const [systemStatus, setSystemStatus] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const [isResuming, setIsResuming] = useState(false);
  const [resumeMessage, setResumeMessage] = useState(null);
  const [selectedFacility, setSelectedFacility] = useState('ALL');
  const [selectedProduct, setSelectedProduct] = useState('ALL');

  const loadRunsAndStatus = async () => {
    setIsLoading(true);
    try {
      const [runsData, statusData] = await Promise.all([
        api.getAgentRuns(25).catch(() => []),
        api.getAgentSystemStatus().catch(() => null)
      ]);
      setRuns(runsData || []);
      setSystemStatus(statusData);

      if (runsData && runsData.length > 0 && !selectedRun) {
        // Load detail of the most recent run
        loadRunDetail(runsData[0].workflow_id);
      }
    } catch (err) {
      console.error('Error loading agent runs:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const loadRunDetail = async (workflowId) => {
    try {
      const detail = await api.getAgentRunDetail(workflowId);
      setSelectedRun(detail);
      setResumeMessage(null);
    } catch (err) {
      console.error('Error loading run detail:', err);
    }
  };

  useEffect(() => {
    loadRunsAndStatus();
  }, []);

  const handleTriggerCycle = async () => {
    setIsExecuting(true);
    try {
      const params = {};
      if (selectedFacility !== 'ALL') params.facility_id = selectedFacility;
      if (selectedProduct !== 'ALL') params.product_id = selectedProduct;
      params.trigger_type = 'MANUAL';

      const result = await api.runAgentCycle(params);
      await loadRunsAndStatus();
      if (result.workflow_id) {
        await loadRunDetail(result.workflow_id);
      }
    } catch (err) {
      console.error('Error triggering agent cycle:', err);
    } finally {
      setIsExecuting(false);
    }
  };

  const handleResumeWorkflow = async (workflowId) => {
    setIsResuming(true);
    setResumeMessage(null);
    try {
      const result = await api.resumeWorkflow(workflowId);
      setResumeMessage(result);
      await loadRunsAndStatus();
      await loadRunDetail(workflowId);
    } catch (err) {
      setResumeMessage({
        status: 'ERROR',
        message: err.message || 'Workflow resumption failed.'
      });
    } finally {
      setIsResuming(false);
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'PAUSED_FOR_APPROVAL':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-100 text-amber-800 border border-amber-300">
            <Clock className="w-3 h-3 mr-1" /> Paused: Awaiting Approval
          </span>
        );
      case 'COMPLETED':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-300">
            <CheckCircle2 className="w-3 h-3 mr-1" /> Completed
          </span>
        );
      case 'COMPLETED_NO_ACTIONS':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-slate-100 text-slate-700 border border-slate-300">
            <CheckCircle2 className="w-3 h-3 mr-1" /> Monitored: No Action Required
          </span>
        );
      case 'FAILED_REVALIDATION':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-rose-100 text-rose-800 border border-rose-300">
            <AlertTriangle className="w-3 h-3 mr-1" /> Pre-Reservation Conflict
          </span>
        );
      case 'FAILED':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-red-100 text-red-800 border border-red-300">
            <AlertTriangle className="w-3 h-3 mr-1" /> Failed
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-blue-100 text-blue-800 border border-blue-300">
            <RefreshCw className="w-3 h-3 mr-1 animate-spin" /> {status}
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 bg-gradient-to-r from-slate-900 via-slate-800 to-indigo-950 p-6 rounded-xl text-white shadow-sm border border-slate-700">
        <div className="space-y-1">
          <div className="flex items-center space-x-2">
            <Bot className="w-6 h-6 text-emerald-400" />
            <h1 className="text-xl font-bold tracking-tight">Supply workflows</h1>
          </div>
          <p className="text-xs text-slate-300 max-w-2xl">
            Bounded multi-agent LangGraph orchestration with deterministic backend authority. 
            Specialist agents review inventory quality, demand baselines, and surplus matching, then pause for dual clinical approval.
          </p>
          <div className="flex flex-wrap items-center gap-2 pt-2">
            <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-slate-800 text-slate-300 border border-slate-700">
              <Sparkles className="w-3 h-3 mr-1 text-emerald-400" />
              Gemini Reasoning: {systemStatus?.gemini?.mode === 'LIVE_GEMINI' ? 'Live Gemini 2.5' : 'Deterministic Template Fallback'}
            </span>
            <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-slate-800 text-slate-300 border border-slate-700">
              <Database className="w-3 h-3 mr-1 text-blue-400" />
              MEKO Context: {systemStatus?.meko?.mode === 'LIVE_MEKO' ? 'MEKO Cloud' : 'Local Memory Fallback'}
            </span>
            <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-slate-800 text-slate-300 border border-slate-700">
              <ShieldCheck className="w-3 h-3 mr-1 text-amber-400" />
              Authority: Deterministic Backend Enforced
            </span>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
          <select
            className="text-xs bg-slate-800 border border-slate-700 text-slate-200 rounded px-2.5 py-2 font-medium"
            value={selectedFacility}
            onChange={(e) => setSelectedFacility(e.target.value)}
          >
            <option value="ALL">All Facilities</option>
            {facilities.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>

          <select
            className="text-xs bg-slate-800 border border-slate-700 text-slate-200 rounded px-2.5 py-2 font-medium"
            value={selectedProduct}
            onChange={(e) => setSelectedProduct(e.target.value)}
          >
            <option value="ALL">All Products</option>
            {products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>

          <button
            onClick={handleTriggerCycle}
            disabled={isExecuting}
            className="flex items-center justify-center space-x-1.5 px-4 py-2 bg-emerald-500 hover:bg-emerald-600 disabled:opacity-50 text-white rounded font-medium text-xs transition shadow-sm"
          >
            {isExecuting ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>Running Graph...</span>
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Trigger Agent Cycle</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Main Grid: Runs List + Detailed Trace Inspector */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Left Column: Recent Runs (4 cols) */}
        <div className="lg:col-span-4 space-y-3">
          <div className="flex items-center justify-between pb-1 border-b border-slate-200">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center">
              <Layers className="w-3.5 h-3.5 mr-1 text-slate-500" />
              Workflow Runs ({runs.length})
            </h2>
            <button
              onClick={loadRunsAndStatus}
              className="text-[11px] text-slate-500 hover:text-slate-800 flex items-center"
            >
              <RefreshCw className="w-3 h-3 mr-1" /> Refresh
            </button>
          </div>

          <div className="space-y-2 max-h-[700px] overflow-y-auto pr-1">
            {runs.length === 0 ? (
              <div className="p-6 text-center bg-white rounded-lg border border-slate-200 text-slate-400 text-xs">
                No workflow runs recorded yet. Click "Trigger Agent Cycle" to execute.
              </div>
            ) : (
              runs.map((r) => {
                const isSelected = selectedRun?.workflow_id === r.workflow_id;
                return (
                  <div
                    key={r.workflow_id}
                    onClick={() => loadRunDetail(r.workflow_id)}
                    className={`p-3 rounded-lg border text-left cursor-pointer transition ${
                      isSelected
                        ? 'bg-emerald-50/50 border-emerald-400 ring-1 ring-emerald-400 shadow-sm'
                        : 'bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-1">
                      <span className="text-[11px] font-mono font-bold text-slate-800">
                        run_{r.workflow_id.slice(0, 8)}
                      </span>
                      {getStatusBadge(r.workflow_status)}
                    </div>

                    <div className="mt-2 text-[11px] text-slate-600 flex items-center justify-between">
                      <span>Trigger: {r.trigger_event_type}</span>
                      <span className="text-slate-400">
                        {r.created_at ? new Date(r.created_at).toLocaleTimeString() : ''}
                      </span>
                    </div>

                    <div className="mt-1 flex items-center space-x-2 text-[10px] text-slate-500">
                      <span>{r.node_count || 5} nodes executed</span>
                      <span>•</span>
                      <span>{r.proposal_id ? 'Proposal Created' : 'No Proposal'}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column: Execution Trace Inspector (8 cols) */}
        <div className="lg:col-span-8 space-y-4">
          {selectedRun ? (
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-5">
              
              {/* Trace Header */}
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-4 border-b border-slate-100">
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="text-sm font-bold text-slate-900 font-mono">
                      Workflow Run: {selectedRun.workflow_id}
                    </span>
                    {getStatusBadge(selectedRun.workflow_status)}
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Triggered at {selectedRun.created_at ? new Date(selectedRun.created_at).toLocaleString() : 'N/A'}
                  </p>
                </div>

                {/* Resumption Card if Paused */}
                {selectedRun.workflow_status === 'PAUSED_FOR_APPROVAL' && (
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleResumeWorkflow(selectedRun.workflow_id)}
                      disabled={isResuming}
                      className="px-3 py-1.5 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white rounded font-medium text-xs flex items-center shadow-sm"
                    >
                      {isResuming ? (
                        <>
                          <RefreshCw className="w-3.5 h-3.5 mr-1 animate-spin" />
                          <span>Checking Approvals...</span>
                        </>
                      ) : (
                        <>
                          <CheckCircle2 className="w-3.5 h-3.5 mr-1" />
                          <span>Resume & Verify Approvals</span>
                        </>
                      )}
                    </button>
                    {onNavigateTab && (
                      <button
                        onClick={() => onNavigateTab('approvals')}
                        className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded font-medium text-xs flex items-center"
                      >
                        <ExternalLink className="w-3 h-3 mr-1" /> Go to Approvals
                      </button>
                    )}
                  </div>
                )}
              </div>

              {/* Resume Result Alert */}
              {resumeMessage && (
                <div className={`p-3 rounded-lg text-xs border ${
                  resumeMessage.status === 'COMPLETED'
                    ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                    : resumeMessage.status === 'PAUSED_AWAITING_APPROVALS'
                    ? 'bg-amber-50 border-amber-200 text-amber-800'
                    : 'bg-rose-50 border-rose-200 text-rose-800'
                }`}>
                  <div className="font-semibold">{resumeMessage.message}</div>
                  {resumeMessage.approval_status && (
                    <div className="mt-1 text-[11px]">
                      Source Approved: {resumeMessage.approval_status.source_approval ? 'YES' : 'PENDING'} | 
                      Destination Approved: {resumeMessage.approval_status.destination_approval ? 'YES' : 'PENDING'}
                    </div>
                  )}
                </div>
              )}

              {/* Gemini Reasoning & MEKO Provenance Banner */}
              <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 space-y-3">
                <div className="flex items-center justify-between text-xs font-bold text-slate-800">
                  <div className="flex items-center space-x-1.5">
                    <Sparkles className="w-4 h-4 text-indigo-600" />
                    <span>Clinical Reasoning Synthesis</span>
                  </div>
                  <span className="text-[11px] font-mono text-slate-500">
                    Mode: {selectedRun.gemini_status || 'DETERMINISTIC_FALLBACK'} ({selectedRun.gemini_model || 'rule-grounded-synthesizer'})
                  </span>
                </div>

                {selectedRun.agent_observations?.orchestrator && (
                  <div className="text-xs text-slate-700 leading-relaxed bg-white p-3 rounded border border-slate-200">
                    {selectedRun.agent_observations.orchestrator.summary}
                  </div>
                )}

                {/* MEKO Context Provenance */}
                <div className="flex items-center space-x-2 text-[11px] text-slate-500 border-t border-slate-200 pt-2">
                  <Database className="w-3.5 h-3.5 text-blue-500" />
                  <span>MEKO Shared Context Retrieved: {selectedRun.meko_context_refs?.length || 0} records</span>
                  <span>•</span>
                  <span>Provenance: {selectedRun.meko_status || 'LOCAL_MEMORY_FALLBACK'}</span>
                </div>
              </div>

              {/* Sequential Node Execution Trace */}
              <div className="space-y-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center">
                  <Cpu className="w-3.5 h-3.5 mr-1 text-slate-500" />
                  LangGraph Specialist Node Execution Trail
                </h3>

                <div className="space-y-3">
                  {(selectedRun.node_trace || []).map((node, idx) => (
                    <div key={idx} className="border border-slate-200 rounded-lg p-3 bg-white space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-2">
                          <span className="w-5 h-5 rounded-full bg-slate-900 text-white text-[10px] font-bold flex items-center justify-center">
                            {idx + 1}
                          </span>
                          <span className="text-xs font-bold text-slate-900">{node.node_name}</span>
                        </div>
                        <span className="text-[10px] text-slate-400">
                          {node.completed_at ? new Date(node.completed_at).toLocaleTimeString() : ''}
                        </span>
                      </div>

                      {/* Observation Summary */}
                      {node.observation && (
                        <p className="text-xs text-slate-600 pl-7">
                          {node.observation.summary}
                        </p>
                      )}

                      {/* Tool Calls */}
                      {node.tool_calls && node.tool_calls.length > 0 && (
                        <div className="pl-7 space-y-1">
                          <span className="text-[10px] font-semibold uppercase text-slate-400 tracking-wider">
                            Deterministic Tool Executions:
                          </span>
                          <div className="space-y-1">
                            {node.tool_calls.map((tc, tcIdx) => (
                              <div
                                key={tcIdx}
                                className="bg-slate-50 border border-slate-200 rounded p-2 text-[11px] text-slate-700 flex items-start justify-between gap-2"
                              >
                                <div>
                                  <span className="font-mono font-bold text-emerald-700">{tc.tool}()</span>
                                  <p className="text-slate-600 mt-0.5">{tc.summary}</p>
                                </div>
                                <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-emerald-100 text-emerald-800">
                                  VERIFIED
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Proposal & Policy Result Banner */}
              {selectedRun.optimisation_result && (
                <div className="p-4 rounded-lg bg-emerald-50/50 border border-emerald-200 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-emerald-900 flex items-center">
                      <FileText className="w-4 h-4 mr-1 text-emerald-700" />
                      Deterministic Redistribution Proposal Generated
                    </span>
                    {selectedRun.proposal_id && (
                      <span className="text-[11px] font-mono text-emerald-800 font-bold">
                        ID: {selectedRun.proposal_id}
                      </span>
                    )}
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs pt-1">
                    <div>
                      <span className="text-[10px] text-slate-500 block">Source Facility</span>
                      <span className="font-semibold text-slate-800">{selectedRun.optimisation_result.source_facility_name}</span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 block">Destination Facility</span>
                      <span className="font-semibold text-slate-800">{selectedRun.optimisation_result.destination_facility_name}</span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 block">Proposed Quantity</span>
                      <span className="font-semibold text-emerald-700">{selectedRun.optimisation_result.proposed_quantity} units</span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 block">Policy Validation</span>
                      <span className="font-semibold text-emerald-700">
                        {selectedRun.policy_validation?.passed ? 'PASSED (100%)' : 'REJECTED'}
                      </span>
                    </div>
                  </div>
                </div>
              )}

            </div>
          ) : (
            <div className="bg-white rounded-xl border border-slate-200 p-12 text-center text-slate-400 text-xs">
              Select a workflow run from the left to inspect its multi-agent execution trace.
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
