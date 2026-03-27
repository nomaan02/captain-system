interface Props {
  label: string;
  className?: string;
}

export function Badge({ label, className = "bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-300" }: Props) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${className}`}>
      {label}
    </span>
  );
}
