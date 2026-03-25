interface UmamiTracker {
  track(event_name: string, data?: Record<string, string | number>): void;
  identify(unique_id: string): void;
  identify(unique_id: string, data: Record<string, string | number>): void;
  identify(data: Record<string, string | number>): void;
}

interface Window {
  umami?: UmamiTracker;
}
