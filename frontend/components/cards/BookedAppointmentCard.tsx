import { BookingCardData } from "@/lib/types";

type Props = {
  booking: BookingCardData;
};

export default function BookedAppointmentCard({ booking }: Props) {
  return (
    <div className="mt-3 rounded-2xl border border-green-200 bg-green-50 p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-green-800">
          Appointment Confirmed
        </h3>
        <span className="rounded-full bg-green-100 px-2 py-1 text-xs font-medium text-green-700">
          Booked
        </span>
      </div>

      <div className="space-y-2 text-sm text-slate-700">
        <div>
          <span className="font-medium">Doctor:</span> {booking.provider_name}
        </div>
        <div>
          <span className="font-medium">Specialty:</span> {booking.specialty}
        </div>
        <div>
          <span className="font-medium">Concern:</span> {booking.body_part}
        </div>
        <div>
          <span className="font-medium">Date:</span> {booking.booked_slot.date}
        </div>
        <div>
          <span className="font-medium">Time:</span> {booking.booked_slot.time}
        </div>
      </div>
    </div>
  );
}