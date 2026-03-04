export default async function PageViewerPage({
  params,
}: {
  params: Promise<{ workspace: string; id: string; pageId: string }>;
}) {
  const { id, pageId } = await params;

  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold text-gray-900">Page Viewer</h1>
      <p className="mt-2 text-sm text-gray-500">
        Artifact: <span className="font-mono">{id}</span> / Page:{" "}
        <span className="font-mono">{pageId}</span>
      </p>
      <p className="mt-4 text-gray-500">
        PDF viewer, extracted text, and compound mentions will appear here.
      </p>
    </div>
  );
}
