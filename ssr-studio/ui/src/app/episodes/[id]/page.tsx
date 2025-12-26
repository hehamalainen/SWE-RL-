"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api, Episode, ValidationReport, SolverAttempt } from "@/lib/api";
import { formatDate, formatDuration } from "@/lib/utils";
import StatusBadge from "@/components/StatusBadge";

type TabType = "overview" | "artifact" | "validation" | "attempts";

export default function EpisodeDetailPage() {
  const params = useParams();
  const episodeId = params.id as string;
  const [activeTab, setActiveTab] = useState<TabType>("overview");

  const { data: episode, isLoading, error } = useQuery({
    queryKey: ["episode", episodeId],
    queryFn: () => api.getEpisode(episodeId),
    refetchInterval: (query) => {
      const ep = query.state.data as Episode | undefined;
      // Auto-refresh for active episodes
      if (ep && !["completed", "failed"].includes(ep.status)) {
        return 5000;
      }
      return false;
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-96">
        <div className="text-gray-500">Loading episode...</div>
      </div>
    );
  }

  if (error || !episode) {
    return (
      <div className="flex items-center justify-center min-h-96">
        <div className="text-red-500">
          Error loading episode: {(error as Error)?.message || "Not found"}
        </div>
      </div>
    );
  }

  const tabs = [
    { id: "overview", label: "Overview" },
    { id: "artifact", label: "Bug Artifact" },
    { id: "validation", label: "Validation" },
    { id: "attempts", label: `Attempts (${episode.solver_attempts?.length || 0})` },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <div className="flex items-center space-x-3">
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
              Episode {episodeId.slice(0, 8)}
            </h1>
            <StatusBadge status={episode.status} />
          </div>
          <p className="text-gray-500 mt-1">
            Environment: {episode.env_id.slice(0, 8)} • Created:{" "}
            {formatDate(episode.created_at)}
          </p>
        </div>
        {episode.final_reward !== undefined && episode.final_reward !== null && (
          <div className="text-right">
            <div className="text-sm text-gray-500">Final Reward</div>
            <div
              className={`text-3xl font-mono font-bold ${
                episode.final_reward > 0
                  ? "text-green-600"
                  : episode.final_reward < 0
                  ? "text-red-600"
                  : "text-gray-500"
              }`}
            >
              {episode.final_reward > 0 ? "+" : ""}
              {episode.final_reward.toFixed(2)}
            </div>
          </div>
        )}
      </div>

      {/* Current Phase Progress */}
      {episode.current_phase && !["completed", "failed"].includes(episode.status) && (
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
          <div className="flex items-center space-x-3">
            <div className="animate-spin rounded-full h-5 w-5 border-2 border-blue-600 border-t-transparent" />
            <span className="text-blue-700 dark:text-blue-300 font-medium">
              Currently: {episode.current_phase}
            </span>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="flex space-x-8">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as TabType)}
              className={`pb-3 px-1 text-sm font-medium border-b-2 transition ${
                activeTab === tab.id
                  ? "border-primary-600 text-primary-600"
                  : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        {activeTab === "overview" && <OverviewTab episode={episode} />}
        {activeTab === "artifact" && <ArtifactTab episode={episode} />}
        {activeTab === "validation" && <ValidationTab episode={episode} />}
        {activeTab === "attempts" && <AttemptsTab episode={episode} />}
      </div>
    </div>
  );
}

function OverviewTab({ episode }: { episode: Episode }) {
  return (
    <div className="space-y-6">
      {/* Pipeline Progress */}
      <div>
        <h3 className="text-sm font-medium text-gray-500 mb-4">Pipeline Progress</h3>
        <div className="flex items-center">
          <PipelineStep
            label="Inject"
            completed={!!episode.artifact}
            active={episode.current_phase === "injecting"}
          />
          <PipelineConnector completed={!!episode.validation_report} />
          <PipelineStep
            label="Validate"
            completed={!!episode.validation_report}
            active={episode.current_phase === "validating"}
            success={episode.validation_report?.passed}
          />
          <PipelineConnector completed={(episode.solver_attempts?.length || 0) > 0} />
          <PipelineStep
            label="Solve"
            completed={episode.status === "completed" || episode.status === "failed"}
            active={episode.current_phase === "solving"}
          />
          <PipelineConnector completed={episode.status === "completed"} />
          <PipelineStep
            label="Complete"
            completed={episode.status === "completed"}
            success={episode.final_reward !== undefined && episode.final_reward > 0}
          />
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-4 gap-4">
        <StatBox
          label="Max Attempts"
          value={episode.max_solver_attempts.toString()}
        />
        <StatBox
          label="Attempts Used"
          value={episode.solver_attempts?.length.toString() || "0"}
        />
        <StatBox
          label="Validation Steps"
          value={
            episode.validation_report
              ? `${episode.validation_report.step_results.filter((s: any) => s.passed).length}/${
                  episode.validation_report.step_results.length
                }`
              : "-"
          }
        />
        <StatBox
          label="Bug Resolved"
          value={
            episode.solver_attempts?.some((a: SolverAttempt) => a.solved)
              ? "Yes"
              : episode.status === "completed"
              ? "No"
              : "-"
          }
          success={episode.solver_attempts?.some((a: SolverAttempt) => a.solved)}
        />
      </div>

      {/* Error Display */}
      {episode.error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
          <h4 className="text-red-700 dark:text-red-300 font-medium mb-2">Error</h4>
          <pre className="text-sm text-red-600 dark:text-red-400 whitespace-pre-wrap">
            {episode.error}
          </pre>
        </div>
      )}
    </div>
  );
}

function ArtifactTab({ episode }: { episode: Episode }) {
  if (!episode.artifact) {
    return (
      <div className="text-center py-12 text-gray-500">
        No artifact generated yet. The injector agent is still working...
      </div>
    );
  }

  const artifact = episode.artifact;

  return (
    <div className="space-y-6">
      {/* Files Changed */}
      <div>
        <h3 className="text-sm font-medium text-gray-500 mb-3">Files Changed</h3>
        <div className="space-y-2">
          {artifact.source_file_path && (
            <div className="flex items-center space-x-2 text-sm">
              <span className="text-orange-600">M</span>
              <code className="bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded">
                {artifact.source_file_path}
              </code>
            </div>
          )}
          {artifact.test_file_path && (
            <div className="flex items-center space-x-2 text-sm">
              <span className="text-green-600">A</span>
              <code className="bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded">
                {artifact.test_file_path}
              </code>
            </div>
          )}
        </div>
      </div>

      {/* Bug Diff */}
      <div>
        <h3 className="text-sm font-medium text-gray-500 mb-3">Bug Diff (mutation)</h3>
        <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto text-sm">
          {artifact.bug_diff || "No diff available"}
        </pre>
      </div>

      {/* Oracle Test */}
      <div>
        <h3 className="text-sm font-medium text-gray-500 mb-3">Oracle Test</h3>
        <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto text-sm">
          {artifact.oracle_test_content || "No test content available"}
        </pre>
      </div>

      {/* Test Command */}
      {artifact.test_cmd && (
        <div>
          <h3 className="text-sm font-medium text-gray-500 mb-3">Test Command</h3>
          <code className="bg-gray-100 dark:bg-gray-700 px-3 py-2 rounded-lg block text-sm">
            {artifact.test_cmd}
          </code>
        </div>
      )}
    </div>
  );
}

function ValidationTab({ episode }: { episode: Episode }) {
  if (!episode.validation_report) {
    return (
      <div className="text-center py-12 text-gray-500">
        Validation not yet started or artifact not available.
      </div>
    );
  }

  const report = episode.validation_report;

  return (
    <div className="space-y-6">
      {/* Overall Status */}
      <div
        className={`p-4 rounded-lg ${
          report.passed
            ? "bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800"
            : "bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800"
        }`}
      >
        <div className="flex items-center space-x-3">
          <div
            className={`text-2xl ${
              report.passed ? "text-green-600" : "text-red-600"
            }`}
          >
            {report.passed ? "✓" : "✗"}
          </div>
          <div>
            <div
              className={`font-medium ${
                report.passed
                  ? "text-green-700 dark:text-green-300"
                  : "text-red-700 dark:text-red-300"
              }`}
            >
              Validation {report.passed ? "Passed" : "Failed"}
            </div>
            <div className="text-sm text-gray-500">
              {report.step_results.filter((s: any) => s.passed).length} of{" "}
              {report.step_results.length} steps passed
            </div>
          </div>
        </div>
      </div>

      {/* Step Results */}
      <div>
        <h3 className="text-sm font-medium text-gray-500 mb-3">Validation Steps</h3>
        <div className="space-y-3">
          {report.step_results.map((step: any, index: number) => (
            <div
              key={index}
              className={`border rounded-lg p-4 ${
                step.passed
                  ? "border-green-200 dark:border-green-800 bg-green-50/50 dark:bg-green-900/10"
                  : "border-red-200 dark:border-red-800 bg-red-50/50 dark:bg-red-900/10"
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center space-x-2">
                  <span
                    className={`text-lg ${
                      step.passed ? "text-green-600" : "text-red-600"
                    }`}
                  >
                    {step.passed ? "✓" : "✗"}
                  </span>
                  <span className="font-medium text-gray-800 dark:text-gray-200">
                    Step {index + 1}: {step.step_name}
                  </span>
                </div>
                {step.duration_ms && (
                  <span className="text-xs text-gray-500">
                    {step.duration_ms}ms
                  </span>
                )}
              </div>
              {step.message && (
                <p className="text-sm text-gray-600 dark:text-gray-400 ml-7">
                  {step.message}
                </p>
              )}
              {step.details && (
                <pre className="text-xs text-gray-500 mt-2 ml-7 whitespace-pre-wrap overflow-x-auto">
                  {typeof step.details === "string"
                    ? step.details
                    : JSON.stringify(step.details, null, 2)}
                </pre>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function AttemptsTab({ episode }: { episode: Episode }) {
  const [expandedAttempt, setExpandedAttempt] = useState<number | null>(null);

  if (!episode.solver_attempts || episode.solver_attempts.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500">
        No solver attempts yet.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {episode.solver_attempts.map((attempt, index) => (
        <div
          key={attempt.attempt_id}
          className={`border rounded-lg ${
            attempt.solved
              ? "border-green-200 dark:border-green-800"
              : "border-gray-200 dark:border-gray-700"
          }`}
        >
          <button
            onClick={() =>
              setExpandedAttempt(expandedAttempt === index ? null : index)
            }
            className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-700/30"
          >
            <div className="flex items-center space-x-3">
              <span
                className={`text-lg ${
                  attempt.solved ? "text-green-600" : "text-red-600"
                }`}
              >
                {attempt.solved ? "✓" : "✗"}
              </span>
              <span className="font-medium">Attempt {index + 1}</span>
              {attempt.tests_passed !== undefined && (
                <span className="text-sm text-gray-500">
                  ({attempt.tests_passed}/{attempt.tests_total} tests passed)
                </span>
              )}
            </div>
            <div className="flex items-center space-x-4">
              {attempt.reward !== undefined && (
                <span
                  className={`font-mono text-sm ${
                    attempt.reward > 0
                      ? "text-green-600"
                      : attempt.reward < 0
                      ? "text-red-600"
                      : "text-gray-500"
                  }`}
                >
                  {attempt.reward > 0 ? "+" : ""}
                  {attempt.reward.toFixed(2)}
                </span>
              )}
              <svg
                className={`w-5 h-5 text-gray-400 transition-transform ${
                  expandedAttempt === index ? "rotate-180" : ""
                }`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 9l-7 7-7-7"
                />
              </svg>
            </div>
          </button>

          {expandedAttempt === index && (
            <div className="px-4 pb-4 border-t border-gray-100 dark:border-gray-700">
              <div className="mt-4 space-y-4">
                {/* Patch */}
                {attempt.patch && (
                  <div>
                    <h4 className="text-sm font-medium text-gray-500 mb-2">
                      Submitted Patch
                    </h4>
                    <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto text-sm">
                      {attempt.patch}
                    </pre>
                  </div>
                )}

                {/* Test Output */}
                {attempt.test_output && (
                  <div>
                    <h4 className="text-sm font-medium text-gray-500 mb-2">
                      Test Output
                    </h4>
                    <pre className="bg-gray-100 dark:bg-gray-700 p-4 rounded-lg overflow-x-auto text-sm text-gray-700 dark:text-gray-300">
                      {attempt.test_output}
                    </pre>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function PipelineStep({
  label,
  completed,
  active,
  success,
}: {
  label: string;
  completed?: boolean;
  active?: boolean;
  success?: boolean;
}) {
  return (
    <div className="flex flex-col items-center">
      <div
        className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-medium ${
          active
            ? "bg-blue-100 text-blue-600 ring-2 ring-blue-400"
            : completed
            ? success === false
              ? "bg-red-100 text-red-600"
              : "bg-green-100 text-green-600"
            : "bg-gray-100 text-gray-400"
        }`}
      >
        {completed ? (success === false ? "✗" : "✓") : active ? "•" : "○"}
      </div>
      <span
        className={`mt-2 text-xs ${
          active
            ? "text-blue-600 font-medium"
            : completed
            ? "text-gray-700 dark:text-gray-300"
            : "text-gray-400"
        }`}
      >
        {label}
      </span>
    </div>
  );
}

function PipelineConnector({ completed }: { completed?: boolean }) {
  return (
    <div
      className={`flex-1 h-0.5 mx-2 ${
        completed ? "bg-green-300" : "bg-gray-200"
      }`}
    />
  );
}

function StatBox({
  label,
  value,
  success,
}: {
  label: string;
  value: string;
  success?: boolean;
}) {
  return (
    <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
      <div className="text-xs text-gray-500 uppercase tracking-wide">{label}</div>
      <div
        className={`text-xl font-semibold mt-1 ${
          success === true
            ? "text-green-600"
            : success === false
            ? "text-red-600"
            : "text-gray-800 dark:text-gray-200"
        }`}
      >
        {value}
      </div>
    </div>
  );
}
