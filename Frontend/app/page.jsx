'use client';
import React, { useState, useEffect, useCallback } from 'react';
import { MessageCircle, X } from 'lucide-react';
import { Navbar } from '../components/Navbar';
import { Sidebar } from '../components/Sidebar';
import { OverviewView } from '../components/views/OverviewView';
import { RisksView } from '../components/views/RisksView';
import { OpportunitiesView } from '../components/views/OpportunitiesView';
import { ApprovalsView } from '../components/views/ApprovalsView';
import { TransfersView } from '../components/views/TransfersView';
import { ScannerView } from '../components/views/ScannerView';
import { InventoryView } from '../components/views/InventoryView';
import { ForecastView } from '../components/views/ForecastView';
import { AuditView } from '../components/views/AuditView';
import { AgentView } from '../components/views/AgentView';
import { FacilitiesView } from '../components/views/FacilitiesView';
import { DataQualityView } from '../components/views/DataQualityView';
import { SettingsView } from '../components/views/SettingsView';
import { ChatView } from '../components/views/ChatView';
import { api } from '../lib/api';

export default function DashboardPage() {
  const [currentTab, setCurrentTab] = useState('overview');
  const [facilities, setFacilities] = useState([]);
  const [users, setUsers] = useState([]);
  const [products, setProducts] = useState([]);
  const [activeFacility, setActiveFacility] = useState(null);
  const [activeUser, setActiveUser] = useState(null);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);

  // Operational Data States
  const [overview, setOverview] = useState(null);
  const [risks, setRisks] = useState([]);
  const [opportunitiesData, setOpportunitiesData] = useState({ accepted_opportunities: [], rejected_candidates: [] });
  const [proposals, setProposals] = useState([]);
  const [transfers, setTransfers] = useState([]);
  const [inventory, setInventory] = useState([]);

  // Agent State
  const [isAgentRunning, setIsAgentRunning] = useState(false);
  const [agentResult, setAgentResult] = useState(null);

  // Status flags
  const [isLoading, setIsLoading] = useState(true);
  const [isResetting, setIsResetting] = useState(false);
  const [isCreatingProposal, setIsCreatingProposal] = useState(false);

  // Fetch initial demo context & metadata
  const loadContext = useCallback(async () => {
    try {
      const ctx = await api.getDemoContext();
      setFacilities(ctx.facilities || []);
      setUsers(ctx.users || []);
      setActiveFacility(current =>
        ctx.facilities?.find(facility => facility.id === current?.id) ||
        ctx.facilities?.[0] ||
        null
      );
      setActiveUser(current =>
        ctx.users?.find(user => user.id === current?.id) ||
        ctx.users?.[0] ||
        null
      );
      const prods = await api.getProducts();
      setProducts(prods || []);
    } catch (err) {
      console.error('Error loading context:', err);
    }
  }, []);

  // Refresh operational state
  const refreshData = useCallback(async () => {
    try {
      const [ov, rsk, opp, prp, trn, inv] = await Promise.all([
        api.getOverview().catch(() => null),
        api.getRisks().catch(() => []),
        api.getOpportunities().catch(() => ({ accepted_opportunities: [], rejected_candidates: [] })),
        api.getProposals().catch(() => []),
        api.getTransfers().catch(() => []),
        api.getInventory().catch(() => [])
      ]);

      if (ov) setOverview(ov);
      setRisks(rsk || []);
      setOpportunitiesData(opp || { accepted_opportunities: [], rejected_candidates: [] });
      setProposals(prp || []);
      setTransfers(trn || []);
      setInventory(inv || []);
    } catch (err) {
      console.error('Error refreshing dashboard data:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadContext().then(() => refreshData());
  }, [loadContext, refreshData]);

  useEffect(() => {
    if (currentTab === 'chat') setAssistantOpen(false);
  }, [currentTab]);

  // Trigger Multi-Agent LangGraph cycle
  const handleRunAgentCycle = async () => {
    setIsAgentRunning(true);
    try {
      const res = await api.runAgentCycle({
        facility_id: activeFacility?.id
      });
      setAgentResult(res);
      await refreshData();
    } catch (err) {
      alert(`Multi-agent cycle error: ${err.message}`);
    } finally {
      setIsAgentRunning(false);
    }
  };

  // Create proposal from accepted opportunity
  const handleCreateProposal = async (opp) => {
    setIsCreatingProposal(true);
    try {
      await api.createProposal(opp);
      setProposals(await api.getProposals());
      setCurrentTab('approvals');
    } finally {
      setIsCreatingProposal(false);
    }
  };

  // Submit Human Approval
  const handleApprove = async (payload) => {
    await api.recordApproval(payload.proposal_id, payload);
    await refreshData();
  };

  // Reset demo
  const handleResetDemo = async () => {
    if (!confirm('Reset demo to initial deterministic baseline?')) return;
    setIsResetting(true);
    try {
      await api.resetDemo();
      await loadContext();
      await refreshData();
      setAgentResult(null);
    } catch (err) {
      alert(`Reset error: ${err.message}`);
    } finally {
      setIsResetting(false);
    }
  };

  // Simulate Stock Shock before reservation
  const handleSimulateStockChange = async () => {
    try {
      const res = await api.simulateStockChange({
        product_code: 'MED-003',
        facility_key: 'apex',
        new_usable_quantity: 5
      });
      alert(res.message);
      await refreshData();
    } catch (err) {
      alert(`Stock shock simulation error: ${err.message}`);
    }
  };

  const badgeCounts = {
    risks: risks.length,
    opportunities: opportunitiesData.accepted_opportunities?.length || 0,
    approvals: proposals.filter(p => p.status.includes('PENDING') || p.status === 'PROPOSED').length,
    transfers: transfers.filter(t => t.status === 'IN_TRANSIT' || t.status === 'READY_FOR_DISPATCH').length
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <Navbar
        facilities={facilities}
        users={users}
        activeFacility={activeFacility}
        activeUser={activeUser}
        onFacilityChange={setActiveFacility}
        onUserChange={setActiveUser}
        onResetDemo={handleResetDemo}
        isResetting={isResetting}
        onOpenMenu={() => setMobileNavOpen(true)}
      />

      <div className="flex min-h-0 flex-1">
        <Sidebar
          currentTab={currentTab}
          onSelectTab={setCurrentTab}
          counts={badgeCounts}
          mobileOpen={mobileNavOpen}
          onCloseMobile={() => setMobileNavOpen(false)}
        />

        <main className="mx-auto w-full min-w-0 max-w-7xl flex-1 p-4 sm:p-6 lg:p-8">
          {isLoading ? (
            <div className="h-96 flex flex-col items-center justify-center space-y-3 text-slate-400">
              <div className="w-8 h-8 border-2 border-emerald-600 border-t-transparent rounded-full animate-spin"></div>
              <p className="text-xs">Connecting to operational inventory ledger...</p>
            </div>
          ) : (
            <>
              {currentTab === 'overview' && (
                <OverviewView
                  overview={overview}
                  risks={risks}
                  opportunities={opportunitiesData.accepted_opportunities}
                  proposals={proposals}
                  onRunAgentCycle={handleRunAgentCycle}
                  isAgentRunning={isAgentRunning}
                  agentResult={agentResult}
                  onNavigateTab={setCurrentTab}
                />
              )}

              {currentTab === 'facilities' && (
                <FacilitiesView
                  facilities={facilities}
                  inventory={inventory}
                  risks={risks}
                  onNavigateTab={setCurrentTab}
                  onSelectFacility={setActiveFacility}
                />
              )}

              {currentTab === 'risks' && (
                <RisksView risks={risks} facilities={facilities} />
              )}

              {currentTab === 'opportunities' && (
                <OpportunitiesView
                  opportunitiesData={opportunitiesData}
                  onCreateProposal={handleCreateProposal}
                  isCreating={isCreatingProposal}
                />
              )}

              {currentTab === 'approvals' && (
                <ApprovalsView
                  proposals={proposals}
                  activeFacility={activeFacility}
                  activeUser={activeUser}
                  onApprove={handleApprove}
                  onSimulateStockChange={handleSimulateStockChange}
                  onNavigateTab={setCurrentTab}
                />
              )}

              {currentTab === 'transfers' && (
                <TransfersView
                  transfers={transfers}
                  onNavigateTab={setCurrentTab}
                  activeUser={activeUser}
                  onRefreshTransfers={refreshData}
                />
              )}

              {currentTab === 'scanner' && (
                <ScannerView
                  activeFacility={activeFacility}
                  activeUser={activeUser}
                  onScanSuccess={refreshData}
                />
              )}

              {currentTab === 'inventory' && (
                <InventoryView
                  inventory={inventory}
                  facilities={facilities}
                  activeFacility={activeFacility}
                  activeUser={activeUser}
                  onRefresh={refreshData}
                />
              )}

              {currentTab === 'forecasts' && (
                <ForecastView facilities={facilities} products={products} />
              )}

              {currentTab === 'agents' && (
                <AgentView
                  facilities={facilities}
                  products={products}
                  onNavigateTab={setCurrentTab}
                />
              )}

              {currentTab === 'chat' && (
                <ChatView activeFacility={activeFacility} />
              )}

              {currentTab === 'data-quality' && (
                <DataQualityView
                  facilities={facilities}
                  onNavigateTab={setCurrentTab}
                />
              )}

              {currentTab === 'audit' && (
                <AuditView />
              )}

              {currentTab === 'settings' && (
                <SettingsView
                  activeFacility={activeFacility}
                  activeUser={activeUser}
                  facilities={facilities}
                  users={users}
                  onFacilityChange={setActiveFacility}
                  onUserChange={setActiveUser}
                  onResetDemo={handleResetDemo}
                  isResetting={isResetting}
                  onRefreshData={refreshData}
                />
              )}
            </>
          )}
        </main>
      </div>

      {currentTab !== 'chat' && (
        <div className="fixed bottom-5 right-5 z-40 flex flex-col items-end gap-3 sm:bottom-7 sm:right-7">
          {assistantOpen && (
            <div className="h-[min(42rem,calc(100dvh-7rem))] w-[min(27rem,calc(100vw-2.5rem))] animate-in slide-in-from-bottom-3 fade-in duration-200">
              <ChatView
                activeFacility={activeFacility}
                compact
                onClose={() => setAssistantOpen(false)}
              />
            </div>
          )}
          <button
            type="button"
            onClick={() => setAssistantOpen((open) => !open)}
            aria-label={assistantOpen ? 'Close MediFlow assistant' : 'Open MediFlow assistant'}
            aria-expanded={assistantOpen}
            className="flex h-14 w-14 items-center justify-center rounded-full bg-emerald-800 text-white shadow-lg shadow-emerald-950/20 transition duration-200 hover:scale-105 hover:bg-emerald-900 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-emerald-300 motion-reduce:transition-none"
          >
            {assistantOpen ? <X className="h-6 w-6" /> : <MessageCircle className="h-6 w-6" />}
          </button>
        </div>
      )}
    </div>
  );
}
