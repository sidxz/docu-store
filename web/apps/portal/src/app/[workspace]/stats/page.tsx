import { redirect } from "next/navigation";

export default async function StatsRedirect({
  params,
}: {
  params: Promise<{ workspace: string }>;
}) {
  const { workspace } = await params;
  redirect(`/${workspace}/settings/stats`);
}
