export default async function ArtifactDetailPage({
  params,
}: {
  params: Promise<{ workspace: string; id: string }>;
}) {
  const { id } = await params;

  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold text-gray-900">
        Artifact Detail
      </h1>
      <p className="mt-2 text-sm text-gray-500">
        ID: <span className="font-mono">{id}</span>
      </p>
      <p className="mt-4 text-gray-500">
        Artifact metadata, workflow status, and page list will appear here.
      </p>
    </div>
  );
}
