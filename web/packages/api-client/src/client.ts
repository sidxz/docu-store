import createClient from "openapi-fetch";
import type { paths } from "./schema";

const baseUrl =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");

export const apiClient = createClient<paths>({
  baseUrl,
});
