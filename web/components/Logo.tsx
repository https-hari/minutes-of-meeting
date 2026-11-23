/** A page of minutes with one line highlighted. */
export function Logo({ className = "h-6 w-6" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <rect x="3.5" y="2.5" width="17" height="19" rx="3" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <rect x="6.5" y="10" width="11" height="3.2" rx="1" fill="var(--color-mark)" />
      <path d="M7 7h10M7 11.6h10M7 16h6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
