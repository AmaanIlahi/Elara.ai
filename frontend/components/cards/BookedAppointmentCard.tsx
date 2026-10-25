"use client";

import { useState } from "react";
import { BookingCardData } from "@/lib/types";
import { downloadCalendarFile } from "@/lib/api";

type Props = {
  booking: BookingCardData;
};

export default function BookedAppointmentCard({ booking }: Props) {
  const [downloading, setDownloading] = useState(false);
  const [calendarError, setCalendarError] = useState(false);

  const handleAddToCalendar = async () => {
    if (!booking.session_id || downloading) return;
    setDownloading(true);
    setCalendarError(false);
    try {
      await downloadCalendarFile(booking.session_id);
    } catch {
      // Most likely the backend restarted and no longer holds this booking.
      setCalendarError(true);
    } finally {
      setDownloading(false);
    }
  };

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

      {booking.session_id ? (
        <div className="mt-4">
          <button
            type="button"
            onClick={handleAddToCalendar}
            disabled={downloading}
            className="rounded-full border border-green-300 bg-white px-4 py-2 text-xs font-medium text-green-800 transition hover:bg-green-100 disabled:opacity-60"
          >
            {downloading ? "Preparing…" : "Add to calendar"}
          </button>
          {calendarError ? (
            <p role="alert" className="mt-2 text-xs text-red-600">
              Sorry, I couldn&apos;t create the calendar file. Please try again in a moment.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
