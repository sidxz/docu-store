/**
 * Login page stub — placeholder for OAuth provider buttons.
 * Will be implemented in Phase 6 with Better Auth or Auth.js.
 */
export default function LoginPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm rounded-xl border border-gray-200 bg-white p-8 shadow-sm">
        <h1 className="text-center text-2xl font-semibold text-gray-900">
          DAIKON DocuStore
        </h1>
        <p className="mt-2 text-center text-sm text-gray-500">
          Sign in to continue
        </p>
        <div className="mt-8 space-y-3">
          <button
            disabled
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-4 py-2.5 text-sm text-gray-400"
          >
            <i className="pi pi-microsoft" />
            Continue with Entra ID
          </button>
          <button
            disabled
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-4 py-2.5 text-sm text-gray-400"
          >
            <i className="pi pi-google" />
            Continue with Google
          </button>
          <button
            disabled
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-4 py-2.5 text-sm text-gray-400"
          >
            <i className="pi pi-github" />
            Continue with GitHub
          </button>
        </div>
        <p className="mt-6 text-center text-xs text-gray-400">
          Auth providers will be configured in Phase 6
        </p>
      </div>
    </div>
  );
}
