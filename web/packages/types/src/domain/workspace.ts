/**
 * Workspace types — stubs for future multi-tenancy.
 * Will be designed in detail during Phase 6 (Auth + Multi-tenancy).
 */

export interface Workspace {
  id: string;
  slug: string;
  name: string;
}

export interface User {
  id: string;
  name: string;
  email: string;
  avatar_url: string | null;
}
