"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api, Episode } from "@/lib/api";
import { formatDate, formatDuration } from "@/lib/utils";
import StatusBadge from "@/components/StatusBadge";

export default function EpisodesPage() {
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [page, setPage] = useState(0);
  const pageSize = 20;

  const { data: episodes, isLoading } = useQuery({
    queryKey: ["episodes", page, pageSize, statusFilter],
    queryFn: () =>
      api.listEpisodes(
        page * pageSize,
        pageSize,
        statusFilter !== "all" ? statusFilter : undefined
      ),
  });

  const filteredEpisodes = episodes || [];

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Episodes
        </h1>
        <Link
          href="/episodes/new"
          className="bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 transition"
        >
          New Episode
        </Link>
      </div>

      {/* Filters */}
      <div className="flex space-x-2">
        {["all", "pending", "injecting", "validating", "solving", "completed", "failed"].map(
          (status) => (
            <button
              key={status}
              onClick={() => {
                setStatusFilter(status);
                setPage(0);
              }}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${
                statusFilter === status
                  ? "bg-primary-600 text-white"
                  : "bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300"
              }`}
            >
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </button>
          )
        )}
      </div>

      {/* Episodes List */}
      {isLoading ? (
        <div className="text-center py-12 text-gray-500">Loading...</div>
      ) : filteredEpisodes.length > 0 ? (
        <>
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-50 dark:bg-gray-700/50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Episode
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Environment
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Phase
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Solve Attempts
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Reward
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Created
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {filteredEpisodes.map((ep) => (
                  <tr
                    key={ep.episode_id}
                    className="hover:bg-gray-50 dark:hover:bg-gray-700/30"
                  >
                    <td className="px-6 py-4 whitespace-nowrap">
                      <Link
                        href={`/episodes/${ep.episode_id}`}
                        className="text-primary-600 hover:text-primary-800 font-medium"
                      >
                        {ep.episode_id.slice(0, 8)}
                      </Link>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {ep.env_id.slice(0, 8)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <StatusBadge status={ep.status} />
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600 dark:text-gray-400">
                      {ep.current_phase || "-"}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      <span className="font-medium">
                        {ep.solver_attempts?.length || 0}
                      </span>
                      <span className="text-gray-500"> / {ep.max_solver_attempts}</span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {ep.final_reward !== undefined && ep.final_reward !== null ? (
                        <span
                          className={`font-mono font-medium ${
                            ep.final_reward > 0
                              ? "text-green-600"
                              : ep.final_reward < 0
                              ? "text-red-600"
                              : "text-gray-500"
                          }`}
                        >
                          {ep.final_reward > 0 ? "+" : ""}
                          {ep.final_reward.toFixed(2)}
                        </span>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {formatDate(ep.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex justify-between items-center">
            <p className="text-sm text-gray-500">
              Showing {page * pageSize + 1} - {page * pageSize + filteredEpisodes.length}
            </p>
            <div className="flex space-x-2">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="px-3 py-1.5 rounded-lg text-sm bg-gray-100 text-gray-700 hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Previous
              </button>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={filteredEpisodes.length < pageSize}
                className="px-3 py-1.5 rounded-lg text-sm bg-gray-100 text-gray-700 hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </div>
        </>
      ) : (
        <div className="text-center py-12 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
          <p className="text-gray-500 mb-4">No episodes found.</p>
          <Link href="/episodes/new" className="text-primary-600 hover:text-primary-800">
            Create your first episode
          </Link>
        </div>
      )}
    </div>
  );
}
