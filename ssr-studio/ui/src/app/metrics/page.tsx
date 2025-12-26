"use client";

import { useQuery } from "@tanstack/react-query";
import { api, EpisodeMetrics } from "@/lib/api";
import { formatPercentage } from "@/lib/utils";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import StatsCard from "@/components/StatsCard";

export default function MetricsPage() {
  const { data: metrics, isLoading } = useQuery({
    queryKey: ["metrics"],
    queryFn: api.getMetrics,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-96">
        <div className="text-gray-500">Loading metrics...</div>
      </div>
    );
  }

  if (!metrics) {
    return (
      <div className="flex items-center justify-center min-h-96">
        <div className="text-gray-500">No metrics available yet.</div>
      </div>
    );
  }

  // Prepare chart data
  const rewardHistory = metrics.reward_history || [];
  const successRateHistory = metrics.success_rate_history || [];
  
  const statusDistribution = [
    { name: "Completed", value: metrics.completed_episodes || 0, color: "#10B981" },
    { name: "Failed", value: metrics.failed_episodes || 0, color: "#EF4444" },
    { name: "In Progress", value: metrics.pending_episodes || 0, color: "#3B82F6" },
  ].filter(item => item.value > 0);

  const validationStepStats = metrics.validation_step_stats || [];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
        Metrics Dashboard
      </h1>

      {/* Stats Overview */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatsCard
          title="Total Episodes"
          value={metrics.total_episodes || 0}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          }
        />
        <StatsCard
          title="Success Rate"
          value={formatPercentage(metrics.solve_rate || 0)}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
          trend={metrics.solve_rate_trend}
        />
        <StatsCard
          title="Avg Reward"
          value={(metrics.avg_reward || 0).toFixed(2)}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
          trend={metrics.reward_trend}
        />
        <StatsCard
          title="Validation Pass Rate"
          value={formatPercentage(metrics.validation_pass_rate || 0)}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          }
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Reward Over Time */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Average Reward Over Time
          </h3>
          {rewardHistory.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={rewardHistory}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                <XAxis dataKey="date" stroke="#9CA3AF" fontSize={12} />
                <YAxis stroke="#9CA3AF" fontSize={12} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#1F2937",
                    border: "none",
                    borderRadius: "8px",
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="reward"
                  stroke="#10B981"
                  strokeWidth={2}
                  dot={{ fill: "#10B981", strokeWidth: 2 }}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[300px] flex items-center justify-center text-gray-500">
              No reward history data yet
            </div>
          )}
        </div>

        {/* Success Rate Over Time */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Success Rate Over Time
          </h3>
          {successRateHistory.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={successRateHistory}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                <XAxis dataKey="date" stroke="#9CA3AF" fontSize={12} />
                <YAxis stroke="#9CA3AF" fontSize={12} domain={[0, 100]} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#1F2937",
                    border: "none",
                    borderRadius: "8px",
                  }}
                  formatter={(value: number) => [`${value.toFixed(1)}%`, "Success Rate"]}
                />
                <Line
                  type="monotone"
                  dataKey="rate"
                  stroke="#3B82F6"
                  strokeWidth={2}
                  dot={{ fill: "#3B82F6", strokeWidth: 2 }}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[300px] flex items-center justify-center text-gray-500">
              No success rate history yet
            </div>
          )}
        </div>

        {/* Episode Status Distribution */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Episode Status Distribution
          </h3>
          {statusDistribution.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={statusDistribution}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={5}
                  dataKey="value"
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                >
                  {statusDistribution.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#1F2937",
                    border: "none",
                    borderRadius: "8px",
                  }}
                />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[300px] flex items-center justify-center text-gray-500">
              No episode data yet
            </div>
          )}
        </div>

        {/* Validation Step Pass Rates */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Validation Step Pass Rates
          </h3>
          {validationStepStats.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={validationStepStats} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                <XAxis type="number" stroke="#9CA3AF" fontSize={12} domain={[0, 100]} />
                <YAxis
                  type="category"
                  dataKey="step"
                  stroke="#9CA3AF"
                  fontSize={11}
                  width={120}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#1F2937",
                    border: "none",
                    borderRadius: "8px",
                  }}
                  formatter={(value: number) => [`${value.toFixed(1)}%`, "Pass Rate"]}
                />
                <Bar dataKey="pass_rate" fill="#8B5CF6" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[300px] flex items-center justify-center text-gray-500">
              No validation data yet
            </div>
          )}
        </div>
      </div>

      {/* Additional Stats Table */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Detailed Statistics
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatItem label="Total Solve Attempts" value={metrics.total_attempts || 0} />
          <StatItem
            label="Avg Attempts per Episode"
            value={(metrics.avg_attempts_per_episode || 0).toFixed(2)}
          />
          <StatItem
            label="First Attempt Success"
            value={formatPercentage(metrics.first_attempt_success_rate || 0)}
          />
          <StatItem
            label="Avg Time to Solve"
            value={`${((metrics.avg_solve_time_ms || 0) / 1000).toFixed(1)}s`}
          />
          <StatItem label="Unique Environments" value={metrics.unique_environments || 0} />
          <StatItem label="Total Bugs Injected" value={metrics.total_bugs_injected || 0} />
          <StatItem
            label="Inverse Mutation Pass Rate"
            value={formatPercentage(metrics.inverse_mutation_pass_rate || 0)}
          />
          <StatItem
            label="Avg Validation Time"
            value={`${((metrics.avg_validation_time_ms || 0) / 1000).toFixed(1)}s`}
          />
        </div>
      </div>
    </div>
  );
}

function StatItem({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
      <div className="text-xs text-gray-500 uppercase tracking-wide">{label}</div>
      <div className="text-xl font-semibold text-gray-800 dark:text-gray-200 mt-1">
        {value}
      </div>
    </div>
  );
}
