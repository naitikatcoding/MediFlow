'use client';
import React, { useState, useEffect } from 'react';
import { TrendingUp, AlertCircle, CheckCircle, BarChart3, Database } from 'lucide-react';
import { 
  ResponsiveContainer, 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  Tooltip, 
  CartesianGrid 
} from 'recharts';
import { api } from '../../lib/api';

export function ForecastView({ facilities = [], products = [] }) {
  const [selectedFacility, setSelectedFacility] = useState(facilities[0]?.id || '');
  const [selectedProduct, setSelectedProduct] = useState(products[0]?.id || '');
  const [forecast, setForecast] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (facilities.length > 0 && !selectedFacility) setSelectedFacility(facilities[0].id);
    if (products.length > 0 && !selectedProduct) setSelectedProduct(products[0].id);
  }, [facilities, products]);

  useEffect(() => {
    if (selectedFacility && selectedProduct) {
      setIsLoading(true);
      api.getForecast(selectedFacility, selectedProduct, 30)
        .then(res => setForecast(res))
        .catch(err => console.error(err))
        .finally(() => setIsLoading(false));
    }
  }, [selectedFacility, selectedProduct]);

  const chartData = forecast?.daily_estimates?.map(d => ({
    date: d.date.substring(5), // MM-DD
    demand: d.estimated_demand,
    upper: d.confidence_upper,
    lower: d.confidence_lower,
  })) || [];

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Demand Intelligence & Baseline Forecasts</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Statistical rolling baseline with historical consumption signals, uncertainty bounds, and data freshness validation.
          </p>
        </div>

        {/* Selectors */}
        <div className="flex items-center space-x-2">
          <select
            className="text-xs bg-white border border-slate-200 rounded-md px-2.5 py-1.5 text-slate-700 font-medium"
            value={selectedFacility}
            onChange={(e) => setSelectedFacility(e.target.value)}
          >
            {facilities.map(f => (
              <option key={f.id} value={f.id}>{f.name}</option>
            ))}
          </select>

          <select
            className="text-xs bg-white border border-slate-200 rounded-md px-2.5 py-1.5 text-slate-700 font-medium"
            value={selectedProduct}
            onChange={(e) => setSelectedProduct(e.target.value)}
          >
            {products.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm">
          <div className="text-[11px] font-medium text-slate-500">Model Algorithm</div>
          <div className="text-sm font-bold text-slate-900 mt-1 font-mono">
            {forecast?.model_name || 'WEIGHTED_MOVING_AVG'}
          </div>
          <div className="text-[10px] text-slate-400 mt-1">Explainable baseline</div>
        </div>

        <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm">
          <div className="text-[11px] font-medium text-slate-500">Daily Average Demand</div>
          <div className="text-xl font-bold text-slate-900 mt-1">
            {forecast?.daily_average_demand ?? 0} <span className="text-xs font-normal text-slate-500">units/day</span>
          </div>
          <div className="text-[10px] text-slate-400 mt-1">Weighted consumption</div>
        </div>

        <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm">
          <div className="text-[11px] font-medium text-slate-500">30-Day Projected Need</div>
          <div className="text-xl font-bold text-emerald-700 mt-1">
            {forecast?.projected_total_demand ?? 0} <span className="text-xs font-normal text-slate-500">units</span>
          </div>
          <div className="text-[10px] text-slate-400 mt-1">Horizon demand buffer</div>
        </div>

        <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm">
          <div className="text-[11px] font-medium text-slate-500">Confidence & Data Quality</div>
          <div className="text-xl font-bold text-slate-900 mt-1">
            {forecast ? Math.round(forecast.confidence_score * 100) : 0}%
          </div>
          <div className="text-[10px] text-slate-400 mt-1">Quality: {forecast?.data_quality_score ?? 1.0}</div>
        </div>
      </div>

      {/* Warnings Banner */}
      {forecast?.warnings?.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-900 flex items-start space-x-2">
          <AlertCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            {forecast.warnings.map((w, i) => (
              <div key={i}>{w}</div>
            ))}
          </div>
        </div>
      )}

      {/* Forecast Chart */}
      <div className="bg-white rounded-lg border border-slate-200 p-5 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wide">
            30-Day Demand Trajectory & Confidence Intervals (90%)
          </h2>
          <span className="text-[11px] text-slate-500">Simulated Daily Horizon</span>
        </div>

        <div className="h-72 w-full">
          {isLoading ? (
            <div className="h-full flex items-center justify-center text-xs text-slate-400">
              Computing statistical forecast...
            </div>
          ) : chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="demandGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.4}/>
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0.0}/>
                  </linearGradient>
                  <linearGradient id="upperGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#cbd5e1" stopOpacity={0.2}/>
                    <stop offset="95%" stopColor="#cbd5e1" stopOpacity={0.0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="#94a3b8" />
                <YAxis tick={{ fontSize: 10 }} stroke="#94a3b8" />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#ffffff', borderColor: '#e2e8f0', borderRadius: '8px', fontSize: '11px' }} 
                />
                <Area type="monotone" dataKey="upper" stroke="#94a3b8" strokeDasharray="3 3" fill="url(#upperGrad)" name="Upper Bound" />
                <Area type="monotone" dataKey="demand" stroke="#10b981" strokeWidth={2} fill="url(#demandGrad)" name="Expected Demand" />
                <Area type="monotone" dataKey="lower" stroke="#94a3b8" strokeDasharray="3 3" fill="none" name="Lower Bound" />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full flex items-center justify-center text-xs text-slate-400">
              No consumption data available for this selection.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

