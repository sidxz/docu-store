export default function AuthErrorPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm rounded-xl border border-gray-200 bg-white p-8 text-center shadow-sm">
        <i className="pi pi-exclamation-triangle mb-4 text-4xl text-red-500" />
        <h1 className="text-xl font-semibold text-gray-900">
          Authentication Error
        </h1>
        <p className="mt-2 text-sm text-gray-500">
          Something went wrong during sign-in. Please try again.
        </p>
      </div>
    </div>
  );
}
