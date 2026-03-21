import { NextResponse } from "next/server";
import { matchSlotsByReason } from "@/lib/conversation";

export async function POST(req: Request) {
  const body = await req.json();

  const slots = matchSlotsByReason(body.reason || "");

  return NextResponse.json({
    summary: body,
    slots,
  });
}