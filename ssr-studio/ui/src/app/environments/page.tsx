"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, Environment } from "@/lib/api";
import { formatDate } from "@/lib/utils";

export default function EnvironmentsPage() {
  const queryClient = useQueryClient();
  const [isCreating, setIsCreating] = useState(false);
  const [newEnv, setNewEnv] = useState({
    name: "",
    docker_image_ref: "",
    language_hint: "unknown",
    notes: "",
  });

  const { data: environments, isLoading } = useQuery({
    queryKey: ["environments"],
    queryFn: api.listEnvironments,
  });

  const createMutation = useMutation({
    mutationFn: api.createEnvironment,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["environments"] });
      setIsCreating(false);
      setNewEnv({ name: "", docker_image_ref: "", language_hint: "unknown", notes: "" });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: api.deleteEnvironment,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["environments"] });
    },
  });

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Environments
        </h1>
        <button
          onClick={() => setIsCreating(true)}
          className="bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 transition"
        >
          Add Environment
        </button>
      </div>

      {/* Create Modal */}
      {isCreating && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-xl p-6 w-full max-w-md">
            <h2 className="text-xl font-semibold mb-4">Add Environment</h2>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                createMutation.mutate(newEnv);
              }}
              className="space-y-4"
            >
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Name
                </label>
                <input
                  type="text"
                  value={newEnv.name}
                  onChange={(e) => setNewEnv({ ...newEnv, name: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                  placeholder="e.g., requests-2.31.0"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Docker Image
                </label>
                <input
                  type="text"
                  value={newEnv.docker_image_ref}
                  onChange={(e) =>
                    setNewEnv({ ...newEnv, docker_image_ref: e.target.value })
                  }
                  className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                  placeholder="e.g., python:3.11-slim"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Language
                </label>
                <select
                  value={newEnv.language_hint}
                  onChange={(e) =>
                    setNewEnv({ ...newEnv, language_hint: e.target.value })
                  }
                  className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                >
                  <option value="unknown">Unknown</option>
                  <option value="python">Python</option>
                  <option value="javascript">JavaScript</option>
                  <option value="typescript">TypeScript</option>
                  <option value="go">Go</option>
                  <option value="rust">Rust</option>
                  <option value="java">Java</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Notes (optional)
                </label>
                <textarea
                  value={newEnv.notes}
                  onChange={(e) => setNewEnv({ ...newEnv, notes: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                  rows={2}
                />
              </div>
              <div className="flex justify-end space-x-3 mt-6">
                <button
                  type="button"
                  onClick={() => setIsCreating(false)}
                  className="px-4 py-2 text-gray-600 hover:text-gray-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 disabled:opacity-50"
                >
                  {createMutation.isPending ? "Creating..." : "Create"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Environments List */}
      {isLoading ? (
        <div className="text-center py-12 text-gray-500">Loading...</div>
      ) : environments && environments.length > 0 ? (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50 dark:bg-gray-700/50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Name
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Docker Image
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Language
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Created
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {environments.map((env) => (
                <tr key={env.env_id} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="font-medium text-gray-900 dark:text-white">
                      {env.name}
                    </div>
                    <div className="text-sm text-gray-500">{env.env_id.slice(0, 8)}</div>
                  </td>
                  <td className="px-6 py-4">
                    <code className="text-sm bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded">
                      {env.docker_image_ref.length > 50
                        ? env.docker_image_ref.slice(0, 50) + "..."
                        : env.docker_image_ref}
                    </code>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-primary-100 text-primary-800">
                      {env.language_hint}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {formatDate(env.created_at)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm">
                    <a
                      href={`/episodes/new?env=${env.env_id}`}
                      className="text-primary-600 hover:text-primary-800 mr-4"
                    >
                      Run
                    </a>
                    <button
                      onClick={() => {
                        if (confirm("Delete this environment?")) {
                          deleteMutation.mutate(env.env_id);
                        }
                      }}
                      className="text-red-600 hover:text-red-800"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="text-center py-12 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
          <p className="text-gray-500 mb-4">No environments registered yet.</p>
          <button
            onClick={() => setIsCreating(true)}
            className="text-primary-600 hover:text-primary-800"
          >
            Add your first environment
          </button>
        </div>
      )}
    </div>
  );
}
