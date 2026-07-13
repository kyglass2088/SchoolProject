import { NextRequest, NextResponse } from "next/server";

export function rejectUnauthorizedGateway(request: NextRequest): NextResponse | null {
  const configured = process.env.GATEWAY_API_KEY;
  const provided = request.headers.get("x-gateway-key");
  if (!configured || !provided || provided !== configured) {
    return NextResponse.json({ error: "unauthorized_gateway" }, { status: 401 });
  }
  return null;
}

