import { cn } from "@/lib/utils";

interface StatsCardProps {
  title: string;
  value: string | number;
  icon?: string;
  color?: "default" | "green" | "blue" | "yellow" | "red";
  subtitle?: string;
}

const colorClasses = {
  default: "bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700",
  green: "bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800",
  blue: "bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800",
  yellow: "bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800",
  red: "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800",
};

const valueClasses = {
  default: "text-gray-900 dark:text-gray-100",
  green: "text-green-700 dark:text-green-300",
  blue: "text-blue-700 dark:text-blue-300",
  yellow: "text-yellow-700 dark:text-yellow-300",
  red: "text-red-700 dark:text-red-300",
};

export function StatsCard({
  title,
  value,
  icon,
  color = "default",
  subtitle,
}: StatsCardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border p-6 shadow-sm",
        colorClasses[color]
      )}
    >
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
            {title}
          </p>
          <p className={cn("mt-2 text-3xl font-bold", valueClasses[color])}>
            {value}
          </p>
          {subtitle && (
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              {subtitle}
            </p>
          )}
        </div>
        {icon && (
          <div className="text-3xl opacity-80">{icon}</div>
        )}
      </div>
    </div>
  );
}
