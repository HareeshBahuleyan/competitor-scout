type SetupStepperProps = {
  currentStep: 1 | 2 | 3;
};

const steps = ["Details", "Sources", "First scan"] as const;

export function SetupStepper({ currentStep }: SetupStepperProps) {
  return (
    <ol aria-label="Setup progress" className="grid gap-2 sm:grid-cols-3">
      {steps.map((label, index) => {
        const step = (index + 1) as 1 | 2 | 3;
        const isCurrent = step === currentStep;
        const isComplete = step < currentStep;
        return (
          <li
            aria-current={isCurrent ? "step" : undefined}
            className={`rounded-xl border px-4 py-3 text-sm font-semibold ${
              isCurrent
                ? "border-slate-950 bg-slate-950 text-white"
                : isComplete
                  ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                  : "border-slate-200 bg-white text-slate-500"
            }`}
            key={label}
          >
            {step}. {label}
          </li>
        );
      })}
    </ol>
  );
}
