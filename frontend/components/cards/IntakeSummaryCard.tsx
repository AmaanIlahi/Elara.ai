import { IntakeSummary } from "@/lib/types";

type Props = {
  summary: IntakeSummary;
};

export default function IntakeSummaryCard({ summary }: Props) {
  return (
    <div className="glass mt-3 rounded-2xl p-4">
      <h3 className="text-sm font-semibold text-slate-900">Patient summary</h3>

      <div className="mt-3 grid gap-2 text-sm text-slate-700">
        <p>
          <span className="font-medium text-slate-900">Name:</span>{" "}
          {summary.firstName} {summary.lastName}
        </p>
        <p>
          <span className="font-medium text-slate-900">DOB:</span> {summary.dob}
        </p>
        <p>
          <span className="font-medium text-slate-900">Phone:</span>{" "}
          {summary.phone}
        </p>
        <p>
          <span className="font-medium text-slate-900">Email:</span>{" "}
          {summary.email}
        </p>
        <p>
          <span className="font-medium text-slate-900">Reason:</span>{" "}
          {summary.reason}
        </p>
      </div>
    </div>
  );
}