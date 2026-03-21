import { AppointmentSlot } from "@/lib/types";

type Props = {
  slots: AppointmentSlot[];
  onSelectSlot: (slot: AppointmentSlot) => void;
};

export default function AppointmentOptionsCard({
  slots,
  onSelectSlot,
}: Props) {
  return (
    <div className="mt-3 space-y-3">
      {slots.map((slot) => (
        <button
          key={slot.id}
          onClick={() => onSelectSlot(slot)}
          className="glass block w-full cursor-pointer rounded-2xl p-4 text-left transition-all duration-200 ease-out hover:-translate-y-[2px] hover:border-blue-200 hover:bg-blue-50/70 hover:shadow-[0_8px_30px_rgba(37,99,235,0.14)] active:scale-[0.99]"
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="font-semibold text-slate-900">{slot.doctorName}</h3>
              <p className="mt-1 text-sm text-slate-600">{slot.specialty}</p>
            </div>

            <span className="rounded-full bg-blue-100 px-3 py-1 text-xs font-medium text-blue-700">
              Available
            </span>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3 text-sm text-slate-700">
            <div className="rounded-xl bg-white/50 px-3 py-2 backdrop-blur-sm">
              <p className="text-xs uppercase tracking-wide text-slate-500">
                Date
              </p>
              <p className="mt-1 font-medium text-slate-900">{slot.date}</p>
            </div>

            <div className="rounded-xl bg-white/50 px-3 py-2 backdrop-blur-sm">
              <p className="text-xs uppercase tracking-wide text-slate-500">
                Time
              </p>
              <p className="mt-1 font-medium text-slate-900">{slot.time}</p>
            </div>
          </div>
        </button>
      ))}
    </div>
  );
}