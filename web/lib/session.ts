import { cookies } from "next/headers";

const SESSION_COOKIE = "kabaman_session";
const ME_URL = "http://127.0.0.1:4174/api/me";

export type EmployeeIdentity = {
  id: number;
  email: string;
  name: string;
};

function employeeFromBody(body: unknown): EmployeeIdentity | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }
  const record = body as Record<string, unknown>;
  if (record.role !== "employee") {
    return null;
  }
  const employee = record.employee;
  if (typeof employee !== "object" || employee === null) {
    return null;
  }
  const person = employee as Record<string, unknown>;
  if (
    typeof person.id !== "number" ||
    !Number.isInteger(person.id) ||
    typeof person.email !== "string" ||
    typeof person.name !== "string"
  ) {
    return null;
  }
  return {
    id: person.id,
    email: person.email,
    name: person.name,
  };
}

export async function readEmployeeFromCookie(
  cookieValue: string | undefined,
  fetcher: typeof fetch = fetch,
): Promise<EmployeeIdentity | null> {
  if (!cookieValue) {
    return null;
  }
  try {
    const response = await fetcher(ME_URL, {
      method: "GET",
      headers: { cookie: `${SESSION_COOKIE}=${cookieValue}` },
      cache: "no-store",
    });
    if (!response.ok) {
      return null;
    }
    return employeeFromBody(await response.json());
  } catch {
    return null;
  }
}

export async function readEmployeeSession(): Promise<EmployeeIdentity | null> {
  const jar = await cookies();
  return readEmployeeFromCookie(jar.get(SESSION_COOKIE)?.value);
}
