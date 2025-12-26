"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { StatsCard } from "@/components/StatsCard";

export default function Home() {
  const { data: metrics } = useQuery({
    queryKey: ["metrics"],
    queryFn: api.getMetrics,
  });

  const { data: recentEpisodes } = useQuery({
    queryKey: ["episodes", { limit: 5 }],
    queryFn: () => api.listEpisodes({ limit: 5 }),
  });

  return (
    <div className="space-y-8">
      {/* Hero Section */}
      <div className="bg-gradient-to-r from-primary-600 to-primary-800 rounded-2xl p-8 text-white">
        <h1 className="text-4xl font-bold mb-4">SSR Studio</h1>
        <p className="text-xl opacity-90 mb-6">
          Self-Play SWE-RL Demo & Research Platform
        </p>
        <p className="text-sm opacity-75 max-w-2xl">
          A platform that demonstrates SSR-style self-play in sandboxed codebases: 
          an agent that creates its own training tasks (bugs + oracle tests) and learns 
          to solve them, forming a step toward self-evolving autonomous SDLC.
        </p>
        <div className="mt-6 flex space-x-4">
          <Link
            href="/episodes/new"
            className="bg-white text-primary-600 px-6 py-2 rounded-lg font-semibold hover:bg-gray-100 transition"
          >
            Run Self-Play
          </Link>
          <Link
            href="/environments"
            className="bg-primary-700 text-white px-6 py-2 rounded-lg font-semibold hover:bg-primary-800 transition"
          >
            Manage Environments
          </Link>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatsCard
          title="Total Episodes"
          value={metrics?.total_episodes ?? 0}
          icon="📊"
        />
        <StatsCard
          title="Artifact Validity"
          value={`${((metrics?.artifact_validity_rate ?? 0) * 100).toFixed(1)}%`}
          icon="✓"
          color="green"
        />
        <StatsCard
          title="Solve Rate"
          value={`${((metrics?.overall_solve_rate ?? 0) * 100).toFixed(1)}%`}
          icon="🎯"
          color="blue"
        />
        <StatsCard
          title="Avg Injector Reward"
          value={metrics?.avg_r_inject?.toFixed(3) ?? "N/A"}
          icon="💰"
          color="yellow"
        />
      </div>

      {/* Recent Episodes */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
        <div className="p-6 border-b border-gray-200 dark:border-gray-700">
          <div className="flex justify-between items-center">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
              Recent Episodes
            </h2>
            <Link
              href="/episodes"
              className="text-primary-600 hover:text-primary-700 text-sm font-medium"
            >
              View All →
            </Link>
          </div>
        </div>
        <div className="divide-y divide-gray-200 dark:divide-gray-700">
          {recentEpisodes?.map((episode) => (
            <Link
              key={episode.episode_id}
              href={`/episodes/${episode.episode_id}`}
              className="block p-4 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-4">
                  <StatusBadge status={episode.status} />
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">
                      {episode.env_name || "Unknown Environment"}
                    </p>
                    <p className="text-sm text-gray-500">
                      {episode.injection_strategy} • {new Date(episode.created_at).toLocaleString()}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  {episode.solve_rate !== null && (
                    <p className="text-sm font-medium text-gray-900 dark:text-white">
                      Solve: {(episode.solve_rate * 100).toFixed(0)}%
                    </p>
                  )}
                  {episode.r_inject !== null && (
                    <p className="text-xs text-gray-500">
                      r_inject: {episode.r_inject.toFixed(2)}
                    </p>
                  )}
                </div>
              </div>
            </Link>
          ))}
          {(!recentEpisodes || recentEpisodes.length === 0) && (
            <div className="p-8 text-center text-gray-500">
              No episodes yet. Start by creating an environment and running self-play.
            </div>
          )}
        </div>
      </div>

      {/* SSR Pipeline Overview */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-6">
          SSR Pipeline Overview
        </h2>
        <div className="flex flex-col md:flex-row items-center justify-between space-y-4 md:space-y-0 md:space-x-4">
          <PipelineStep
            step={1}
            title="Inject"
            description="Agent explores repo, discovers tests, and injects a bug"
            icon="🔧"
          />
          <Arrow />
          <PipelineStep
            step={2}
            title="Validate"
            description="Artifact checked for consistency (7 validation steps)"
            icon="✓"
          />
          <Arrow />
          <PipelineStep
            step={3}
            title="Solve"
            description="N solver attempts to fix the bug using oracle tests"
            icon="🎯"
          />
          <Arrow />
          <PipelineStep
            step={4}
            title="Evaluate"
            description="Compute solve rate and rewards for training"
            icon="📊"
          />
        </div>
      </div>
    </div>
  );
}

function PipelineStep({
  step,
  title,
  description,
  icon,
}: {
  step: number;
  title: string;
  description: string;
  icon: string;
}) {
  return (
    <div className="flex-1 text-center p-4">
      <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-primary-100 dark:bg-primary-900 text-2xl mb-3">
        {icon}
      </div>
      <h3 className="font-semibold text-gray-900 dark:text-white">
        {step}. {title}
      </h3>
      <p className="text-sm text-gray-500 mt-1">{description}</p>
    </div>
  );
}

function Arrow() {
  return (
    <div className="hidden md:block text-gray-300 dark:text-gray-600">
      <svg
        className="w-8 h-8"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M9 5l7 7-7 7"
        />
      </svg>
    </div>
  );
}
