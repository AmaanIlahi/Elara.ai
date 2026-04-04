"use client";

import { useEffect, useState } from "react";
import { SlotOption } from "@/lib/types";

type Props = {
  slots: SlotOption[];
  onSelect: (value: string) => void;
};

export default function SlotCardsMessage({ slots, onSelect }: Props) {
  const [visible, setVisible] = useState<boolean[]>(slots.map(() => false));
  const [selected, setSelected] = useState<string | null>(null);

  // Stagger card entrance
  useEffect(() => {
    slots.forEach((_, i) => {
      setTimeout(() => {
        setVisible((prev) => {
          const next = [...prev];
          next[i] = true;
          return next;
        });
      }, i * 80);
    });
  }, [slots]);

  const handleSelect = (slot: SlotOption) => {
    if (selected) return;
    setSelected(slot.value);
    onSelect(slot.value);
  };

  return (
    <div className="mt-2 flex flex-col gap-2">
      {slots.map((slot, i) => {
        const [dayPart, timePart] = slot.label.split(" · ");
        const isSelected = selected === slot.value;
        const isDimmed = selected !== null && !isSelected;

        return (
          <button
            key={slot.id}
            onClick={() => handleSelect(slot)}
            disabled={selected !== null}
            style={{
              opacity: visible[i] ? 1 : 0,
              transform: visible[i] ? "translateY(0)" : "translateY(8px)",
              transition: `opacity 0.25s ease ${i * 80}ms, transform 0.25s ease ${i * 80}ms`,
            }}
            className={[
              "flex items-center justify-between rounded-2xl border px-4 py-3 text-left text-sm shadow-sm",
              "transition-all duration-200",
              isSelected
                ? "border-blue-400 bg-blue-50 shadow-md shadow-blue-100"
                : isDimmed
                ? "border-white/30 bg-white/40 opacity-40 cursor-not-allowed"
                : "border-white/40 bg-white/70 backdrop-blur-md hover:border-blue-300 hover:bg-blue-50/60 hover:-translate-y-[1px] hover:shadow-md active:scale-[0.98] cursor-pointer",
            ].join(" ")}
          >
            <div className="flex flex-col gap-0.5">
              <span className={`font-semibold ${isSelected ? "text-blue-700" : "text-slate-800"}`}>
                {dayPart}
              </span>
              <span className={`text-xs ${isSelected ? "text-blue-500" : "text-slate-500"}`}>
                {timePart}
              </span>
            </div>

            <div className="flex items-center gap-2">
              <span className={`text-xs font-medium ${isSelected ? "text-blue-600" : "text-slate-400"}`}>
                Slot {slot.value}
              </span>
              {isSelected && (
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-500 text-white text-[10px] font-bold">
                  ✓
                </span>
              )}
            </div>
          </button>
        );
      })}
    </div>
  );
}
