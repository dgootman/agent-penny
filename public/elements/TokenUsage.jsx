import { Card } from "@/components/ui/card";

function toNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function formatNumber(value) {
  return Math.round(value).toLocaleString();
}

function formatPercent(value) {
  if (value > 0 && value < 0.1) return "<0.1%";
  return `${value.toFixed(value >= 10 ? 0 : 1)}%`;
}

export default function TokenUsage() {
  const totalTokens = toNumber(props?.total_tokens);
  const contextWindow = toNumber(props?.context_window);

  if (totalTokens === null || contextWindow === null || contextWindow <= 0) {
    return null;
  }

  const percent =
    contextWindow > 0 ? clamp((totalTokens / contextWindow) * 100, 0, 100) : 0;
  const size = 16;
  const stroke = 2;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (percent / 100) * circumference;

  return (
    <Card className="inline-flex items-center gap-2 px-2 py-1">
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="-rotate-90 text-primary"
        style={{
          width: `${size}px`,
          height: `${size}px`,
          maxWidth: `${size}px`,
          maxHeight: `${size}px`,
        }}
        role="img"
        aria-label={`${formatNumber(totalTokens)} of ${formatNumber(contextWindow)} tokens`}
      >
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          className="text-muted/25"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>

      <div className="min-w-0 whitespace-nowrap text-xs tabular-nums">
        <span className="font-semibold leading-none">
          {formatPercent(percent)}
        </span>
        <span className="text-muted-foreground">
          {" "}
          · {formatNumber(totalTokens)} / {formatNumber(contextWindow)} tokens
        </span>
      </div>
    </Card>
  );
}
