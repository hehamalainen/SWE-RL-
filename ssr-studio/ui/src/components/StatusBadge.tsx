import { cn } from "@/lib/utils";

interface StatusBadgeProps {
  status: string;
  size?: "sm" | "md" | "lg";
}

const statusConfig: Record<string, { color: string; label: string }> = {
  pending: { color: "bg-gray-100 text-gray-800", label: "Pending" },
  injecting: { color: "bg-yellow-100 text-yellow-800", label: "Injecting" },
  validating: { color: "bg-blue-100 text-blue-800", label: "Validating" },
  solving: { color: "bg-purple-100 text-purple-800", label: "Solving" },
  evaluating: { color: "bg-indigo-100 text-indigo-800", label: "Evaluating" },
  complete: { color: "bg-green-100 text-green-800", label: "Complete" },
  failed: { color: "bg-red-100 text-red-800", label: "Failed" },
  cancelled: { color: "bg-gray-100 text-gray-800", label: "Cancelled" },
};

export function StatusBadge({ status, size = "md" }: StatusBadgeProps) {
  const config = statusConfig[status] || {
    color: "bg-gray-100 text-gray-800",
    label: status,
  };

  const sizeClasses = {
    sm: "px-2 py-0.5 text-xs",
    md: "px-2.5 py-0.5 text-sm",
    lg: "px-3 py-1 text-base",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full font-medium",
        config.color,
        sizeClasses[size]
      )}
    >
      {config.label}
    </span>
  );
}
