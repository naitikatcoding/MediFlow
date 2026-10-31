'use client';
import React, { useState, useEffect, useCallback } from 'react';
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
import { api } from '../lib/api';

export default function DashboardPage() {
  const [currentTab, setCurrentTab] = useState('overview');
  const [facilities, setFacilities] = useState([]);
  const [users, setUsers] = useState([]);
  const [products, setProducts] = useState([]);
  const [activeFacility, setActiveFacility] = useState(null);
  const [activeUser, setActiveUser] = useState(null);

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
      if (ctx.facilities?.length > 0 && !activeFacility) {
        setActiveFacility(ctx.facilities[0]);
      }
      if (ctx.users?.length > 0 && !activeUser) {
        setActiveUser(ctx.users[0]);
      }
      const prods = await api.getProducts();
      setProducts(prods || []);
    } catch (err) {
      console.error('Error loading context:', err);
    }
  }, [activeFacility, activeUser]);

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
      await refreshData();
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
      />

      <div className="flex-1 flex">
        <Sidebar
          currentTab={currentTab}
          onSelectTab={setCurrentTab}
          counts={badgeCounts}
        />

        <main className="flex-1 p-6 lg:p-8 max-w-7xl mx-auto w-full">
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
                <TransfersView transfers={transfers} onNavigateTab={setCurrentTab} />
              )}

              {currentTab === 'scanner' && (
                <ScannerView
                  activeFacility={activeFacility}
                  activeUser={activeUser}
                  onScanSuccess={refreshData}
                />
              )}

              {currentTab === 'inventory' && (
                <InventoryView inventory={inventory} facilities={facilities} />
              )}

              {currentTab === 'forecasts' && (
                <ForecastView facilities={facilities} products={products} />
              )}

              {currentTab === 'audit' && (
                <AuditView />
              )}
            </>
          )}
        </main>
      </div>
    </div>
  );
}

