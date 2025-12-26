"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";

export default function NewEpisodePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const preselectedEnv = searchParams.get("env") || "";

  const [envId, setEnvId] = useState(preselectedEnv);
  const [maxSolverAttempts, setMaxSolverAttempts] = useState(3);
  const [injectorModel, setInjectorModel] = useState("gpt-4-turbo");
  const [solverModel, setSolverModel] = useState("gpt-4-turbo");

  const { data: environments, isLoading: envsLoading } = useQuery({
    queryKey: ["environments"],
    queryFn: api.listEnvironments,
  });

  const createMutation = useMutation({
    mutationFn: api.createEpisode,
    onSuccess: (episode) => {
      router.push(`/episodes/${episode.episode_id}`);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createMutation.mutate({
      env_id: envId,
      max_solver_attempts: maxSolverAttempts,
      injector_model_id: injectorModel,
      solver_model_id: solverModel,
    });
  };

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">
        Create New Episode
      </h1>

      <form
        onSubmit={handleSubmit}
        className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6 space-y-6"
      >
        {/* Environment Selection */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Target Environment
          </label>
          {envsLoading ? (
            <p className="text-gray-500">Loading environments...</p>
          ) : environments && environments.length > 0 ? (
            <select
              value={envId}
              onChange={(e) => setEnvId(e.target.value)}
              className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
              required
            >
              <option value="">Select an environment</option>
              {environments.map((env) => (
                <option key={env.env_id} value={env.env_id}>
                  {env.name} ({env.language_hint})
                </option>
              ))}
            </select>
          ) : (
            <div className="text-center py-4 bg-gray-50 dark:bg-gray-700 rounded-lg">
              <p className="text-gray-500 mb-2">No environments available.</p>
              <a
                href="/environments"
                className="text-primary-600 hover:text-primary-800"
              >
                Add an environment first
              </a>
            </div>
          )}
        </div>

        {/* Max Solver Attempts */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Max Solver Attempts
          </label>
          <input
            type="number"
            min={1}
            max={10}
            value={maxSolverAttempts}
            onChange={(e) => setMaxSolverAttempts(parseInt(e.target.value, 10))}
            className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
          />
          <p className="text-xs text-gray-500 mt-1">
            Number of times the solver agent can attempt to fix the bug
          </p>
        </div>

        {/* Model Selection */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Injector Model
            </label>
            <select
              value={injectorModel}
              onChange={(e) => setInjectorModel(e.target.value)}
              className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
            >
              <optgroup label="OpenAI">
                <option value="gpt-4-turbo">GPT-4 Turbo</option>
                <option value="gpt-4o">GPT-4o</option>
                <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
              </optgroup>
              <optgroup label="Anthropic">
                <option value="claude-3-opus">Claude 3 Opus</option>
                <option value="claude-3-sonnet">Claude 3 Sonnet</option>
                <option value="claude-3-haiku">Claude 3 Haiku</option>
              </optgroup>
              <optgroup label="Local">
                <option value="local">Local Model (vLLM)</option>
              </optgroup>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Solver Model
            </label>
            <select
              value={solverModel}
              onChange={(e) => setSolverModel(e.target.value)}
              className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
            >
              <optgroup label="OpenAI">
                <option value="gpt-4-turbo">GPT-4 Turbo</option>
                <option value="gpt-4o">GPT-4o</option>
                <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
              </optgroup>
              <optgroup label="Anthropic">
                <option value="claude-3-opus">Claude 3 Opus</option>
                <option value="claude-3-sonnet">Claude 3 Sonnet</option>
                <option value="claude-3-haiku">Claude 3 Haiku</option>
              </optgroup>
              <optgroup label="Local">
                <option value="local">Local Model (vLLM)</option>
              </optgroup>
            </select>
          </div>
        </div>

        {/* Pipeline Overview */}
        <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
            Episode Pipeline
          </h3>
          <div className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400">
            <div className="flex flex-col items-center">
              <div className="w-8 h-8 rounded-full bg-orange-100 text-orange-600 flex items-center justify-center mb-1">
                1
              </div>
              <span>Inject</span>
            </div>
            <div className="flex-1 h-px bg-gray-300 mx-2" />
            <div className="flex flex-col items-center">
              <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center mb-1">
                2
              </div>
              <span>Validate</span>
            </div>
            <div className="flex-1 h-px bg-gray-300 mx-2" />
            <div className="flex flex-col items-center">
              <div className="w-8 h-8 rounded-full bg-purple-100 text-purple-600 flex items-center justify-center mb-1">
                3
              </div>
              <span>Solve</span>
            </div>
            <div className="flex-1 h-px bg-gray-300 mx-2" />
            <div className="flex flex-col items-center">
              <div className="w-8 h-8 rounded-full bg-green-100 text-green-600 flex items-center justify-center mb-1">
                4
              </div>
              <span>Evaluate</span>
            </div>
          </div>
        </div>

        {/* Error Display */}
        {createMutation.isError && (
          <div className="bg-red-50 text-red-600 px-4 py-3 rounded-lg text-sm">
            Error creating episode: {(createMutation.error as Error).message}
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end space-x-3">
          <button
            type="button"
            onClick={() => router.back()}
            className="px-4 py-2 text-gray-600 hover:text-gray-800"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!envId || createMutation.isPending}
            className="bg-primary-600 text-white px-6 py-2 rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition"
          >
            {createMutation.isPending ? "Creating..." : "Create Episode"}
          </button>
        </div>
      </form>
    </div>
  );
}
