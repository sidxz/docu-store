import { redirect } from "next/navigation";

/**
 * Root page — redirects to the default workspace.
 * When auth is implemented, this will redirect based on the user's session.
 */
export default function RootPage() {
  redirect("/default");
}
