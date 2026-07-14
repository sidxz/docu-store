import { redirect } from "next/navigation";

export default async function StatusRedirect({
  params,
}: {
  params: Promise<{ workspace: string }>;
}) {
  const { workspace } = await params;
  redirect(`/${workspace}/settings/status`);
}
