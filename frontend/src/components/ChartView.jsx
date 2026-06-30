import { useState, useEffect, useMemo } from 'react';
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Legend, ResponsiveContainer } from 'recharts';
import { BarChart3, LineChart as LineIcon, Settings } from 'lucide-react';

export const ChartView = ({ data }) => {
  const [chartType, setChartType] = useState('bar');
  const [xAxisKey, setXAxisKey] = useState('');
  const [yAxisKey, setYAxisKey] = useState('');

  const { numericKeys, stringKeys } = useMemo(() => {
    if (!data || data.length === 0) return { numericKeys: [], stringKeys: [] };
    const sample = data[0];
    const keys = Object.keys(sample);
    const numKeys = keys.filter((key) =>
      data.slice(0, 5).some((row) => {
        const val = row[key];
        if (typeof val === 'number') return true;
        if (typeof val === 'string') return val.trim() !== '' && !isNaN(Number(val));
        return false;
      })
    );
    const strKeys = keys.filter((key) => !numKeys.includes(key));
    return { numericKeys: numKeys, stringKeys: strKeys };
  }, [data]);

  useEffect(() => {
    if (!data || data.length === 0) return;
    const keys = Object.keys(data[0]);
    if (stringKeys.length > 0) {
      setXAxisKey(prev => (stringKeys.includes(prev) ? prev : stringKeys[0]));
    } else if (keys.length > 0) {
      setXAxisKey(prev => (keys.includes(prev) ? prev : keys[0]));
    }
    if (numericKeys.length > 0) {
      setYAxisKey(prev => (numericKeys.includes(prev) ? prev : numericKeys[0]));
    }
  }, [data, numericKeys, stringKeys]);

  const chartData = useMemo(() => {
    if (!data) return [];
    return data.map((row) => ({ ...row, [yAxisKey]: Number(row[yAxisKey]) }));
  }, [data, yAxisKey]);

  if (!data || data.length === 0) return null;

  if (numericKeys.length === 0) {
    return (
      <div className="p-8 text-center border border-slate-800 rounded-xl bg-slate-900/10">
        <p className="text-xs text-slate-500">No numeric data columns found in results to plot a chart.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Chart Configuration Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 bg-slate-900/40 border border-slate-800 rounded-xl">
        <div className="flex items-center gap-3">
          <Settings size={16} className="text-indigo-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Chart Settings</span>
        </div>

        <div className="flex flex-wrap items-center gap-4 text-sm">
          {/* X Axis Selector */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500">Label (X-Axis):</span>
            <select
              value={xAxisKey}
              onChange={(e) => setXAxisKey(e.target.value)}
              className="bg-slate-950 border border-slate-800 text-slate-300 rounded px-2.5 py-1 text-xs outline-none focus:border-indigo-500"
            >
              {stringKeys.map((k) => (
                <option key={k} value={k}>{k}</option>
              ))}
              {numericKeys.map((k) => (
                <option key={k} value={k}>{k} (num)</option>
              ))}
            </select>
          </div>

          {/* Y Axis Selector */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500">Value (Y-Axis):</span>
            <select
              value={yAxisKey}
              onChange={(e) => setYAxisKey(e.target.value)}
              className="bg-slate-950 border border-slate-800 text-slate-300 rounded px-2.5 py-1 text-xs outline-none focus:border-indigo-500"
            >
              {numericKeys.map((k) => (
                <option key={k} value={k}>{k}</option>
              ))}
            </select>
          </div>

          {/* Chart Type Toggle */}
          <div className="flex items-center bg-slate-950 rounded-lg p-0.5 border border-slate-800">
            <button
              onClick={() => setChartType('bar')}
              className={`p-1.5 rounded-md transition ${chartType === 'bar' ? 'bg-indigo-500/20 text-indigo-400' : 'text-slate-500 hover:text-slate-300'}`}
              title="Bar Chart"
            >
              <BarChart3 size={15} />
            </button>
            <button
              onClick={() => setChartType('line')}
              className={`p-1.5 rounded-md transition ${chartType === 'line' ? 'bg-indigo-500/20 text-indigo-400' : 'text-slate-500 hover:text-slate-300'}`}
              title="Line Chart"
            >
              <LineIcon size={15} />
            </button>
          </div>
        </div>
      </div>

      {/* Chart Canvas */}
      <div className="h-80 w-full p-4 bg-slate-950/40 border border-slate-800/80 rounded-2xl">
        <ResponsiveContainer width="100%" height="100%">
          {chartType === 'bar' ? (
            <BarChart data={chartData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis 
                dataKey={xAxisKey} 
                stroke="#64748b" 
                fontSize={11} 
                tickLine={false} 
              />
              <YAxis 
                stroke="#64748b" 
                fontSize={11} 
                tickLine={false} 
                axisLine={false} 
              />
              <Tooltip 
                contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: 8, color: '#fff' }} 
                itemStyle={{ color: '#818cf8' }} 
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar 
                dataKey={yAxisKey} 
                fill="url(#barGradient)" 
                radius={[4, 4, 0, 0]} 
                maxBarSize={50} 
              />
              <defs>
                <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#818cf8" stopOpacity={0.8} />
                  <stop offset="100%" stopColor="#c084fc" stopOpacity={0.3} />
                </linearGradient>
              </defs>
            </BarChart>
          ) : (
            <LineChart data={chartData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis 
                dataKey={xAxisKey} 
                stroke="#64748b" 
                fontSize={11} 
                tickLine={false} 
              />
              <YAxis 
                stroke="#64748b" 
                fontSize={11} 
                tickLine={false} 
                axisLine={false} 
              />
              <Tooltip 
                contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: 8, color: '#fff' }} 
                itemStyle={{ color: '#818cf8' }} 
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line 
                type="monotone" 
                dataKey={yAxisKey} 
                stroke="#818cf8" 
                strokeWidth={3} 
                dot={{ r: 4, strokeWidth: 2, fill: '#0a0b10' }} 
                activeDot={{ r: 6 }} 
              />
            </LineChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
};
