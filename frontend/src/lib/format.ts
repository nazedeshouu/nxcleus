export const usd = (n: number) =>
  n >= 1 ? `$${n.toFixed(2)}` : `$${n.toFixed(n < 0.1 ? 3 : 2)}`;

export const compact = (n: number) => {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return `${n}`;
};

export const pct = (n: number) => `${Math.round(n * 100)}%`;

export const seconds = (s: number) => (s >= 60 ? `${(s / 60).toFixed(1)}m` : `${s}s`);
