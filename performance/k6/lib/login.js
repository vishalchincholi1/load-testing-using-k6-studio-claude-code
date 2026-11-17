import http from "k6/http";
import { fail } from "k6";

// CHANGE FOR YOUR PROJECT: login endpoint, body fields and the token field in the response.
// If LOGIN_PATH is empty in the env file, no login happens (public API).
export function login() {
  const path = __ENV.LOGIN_PATH || "";
  if (!path) return "";

  const res = http.post(
    `${__ENV.BASE_URL}${path}`,
    JSON.stringify({ email: __ENV.EMAIL, password: __ENV.PASSWORD }),
    { headers: { "Content-Type": "application/json" }, tags: { name: "login" } }
  );
  if (res.status < 200 || res.status >= 300) {
    fail(`Login failed (status=${res.status}). Check EMAIL / PASSWORD / LOGIN_PATH in the env file.`);
  }
  const field = __ENV.TOKEN_FIELD || "access_token";
  const token = res.json(field);
  if (!token) fail(`Login passed but no "${field}" in the response.`);
  return token;
}
