export default function LoginPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 p-8">
      <div>
        <p className="text-sm font-medium text-slate-500">Competitor Scout</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">Know what changed.</h1>
        <p className="mt-3 text-slate-600">Google sign-up is limited to ten users.</p>
      </div>
      <a
        className="rounded-lg bg-slate-950 px-4 py-3 text-center font-medium text-white transition-colors hover:bg-slate-800"
        href="/auth/google/login"
      >
        Continue with Google
      </a>
    </main>
  );
}
