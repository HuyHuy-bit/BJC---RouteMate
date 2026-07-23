/**
 * FastAPI returns errors in two different shapes, and code across this
 * app was inconsistently assuming only one of them:
 *
 *   - Business logic errors (HTTPException):  { detail: "some message" }
 *   - Pydantic validation errors (422):       { detail: [ { type, loc,
 *     msg, input, ... }, ... ] }  <- an ARRAY of objects, not a string
 *
 * Reading `err.response.data.detail` directly and handing it straight to
 * a toast or a <Field error=...> assumes the first shape. On a
 * validation failure it silently hands React an array of plain objects
 * to render as text, which throws "Objects are not valid as a React
 * child" — the exact failure mode that made a form look broken instead
 * of showing the person what to fix.
 */

interface PydanticValidationError {
  type?: string;
  loc?: (string | number)[];
  msg?: string;
}

const FIELD_LABELS: Record<string, string> = {
  full_name: "Họ và tên",
  phone: "Số điện thoại",
  password: "Mật khẩu",
  pickup_address: "Địa chỉ đón",
  dropoff_address: "Địa chỉ trả",
  requested_pickup_at: "Ngày giờ đón",
  plate_number: "Biển số xe",
  seat_capacity: "Số chỗ",
};

function describeField(loc: (string | number)[] = []): string {
  const field = String(loc[loc.length - 1] ?? "");
  return FIELD_LABELS[field] ?? field;
}

export function getErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as any)?.response?.data?.detail;

  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const messages = (detail as PydanticValidationError[])
      .map((e) => {
        const field = describeField(e.loc);
        return field ? `${field}: ${e.msg}` : e.msg;
      })
      .filter(Boolean);
    if (messages.length > 0) return messages.join(" · ");
  }

  return fallback;
}
