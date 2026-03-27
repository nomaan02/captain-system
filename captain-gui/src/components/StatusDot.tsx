interface Props {
  color: string;
  pulse?: boolean;
  label?: string;
}

export function StatusDot({ color, pulse, label }: Props) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="relative flex h-2.5 w-2.5">
        {pulse && (
          <span className={`absolute inline-flex h-full w-full animate-ping rounded-full ${color} opacity-75`} />
        )}
        <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${color}`} />
      </span>
      {label && <span className="text-xs">{label}</span>}
    </span>
  );
}
