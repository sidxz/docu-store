export default async function DashboardPage({
  params,
}: {
  params: Promise<{ workspace: string }>;
}) {
  const { workspace } = await params;

  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold text-gray-900">Dashboard</h1>
      <p className="mt-2 text-sm text-gray-500">
        Workspace: <span className="font-mono">{workspace}</span>
      </p>
      <p className="mt-4 text-gray-500">
        Overview and quick stats will appear here.
      </p>
    </div>
  );
}
