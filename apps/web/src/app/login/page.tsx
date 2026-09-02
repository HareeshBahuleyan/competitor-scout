export default function LoginPage() {
  return (
    <main className="grid min-h-screen place-items-center bg-[radial-gradient(circle_at_50%_0%,#fff_0%,#f7f5f1_52%)] p-6">
      <section className="w-full max-w-[420px] rounded-[var(--radius-panel)] border border-slate-200 bg-[#fffefa] p-8 shadow-[0_24px_70px_rgba(48,40,32,0.08)] sm:p-10">
        <div aria-hidden="true" className="brand-mark mb-7">
          <svg fill="none" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="7.5" stroke="currentColor" strokeWidth="1.8" />
            <circle cx="12" cy="12" fill="currentColor" r="2.25" />
            <path
              d="M12 2.5V5M21.5 12H19M12 19v2.5M5 12H2.5"
              stroke="currentColor"
              strokeLinecap="round"
              strokeWidth="1.8"
            />
          </svg>
        </div>
        <p className="eyebrow">Competitor Scout</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-[-0.035em]">Know what changed.</h1>
        <p className="mt-3 leading-7 text-slate-600">
          Calm, evidence-backed market intelligence for your team.
        </p>
        <a
          className="mt-8 flex min-h-11 items-center justify-center gap-2 rounded-xl bg-[#d34d50] px-4 py-3 font-semibold text-white shadow-[0_6px_18px_rgba(185,62,66,0.2)] transition hover:bg-[#b93e42]"
          href="/auth/google/login"
        >
          Continue with Google
        </a>
      </section>
    </main>
  );
}
