/**
 * Auth service – token storage + login/register/logout.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import { BASE_URL } from "./api";

const TOKEN_KEY = "skywalker_token";
const USER_KEY = "skywalker_user";

export async function register({ email, password, name, ftp_override }) {
  const res = await fetch(`${BASE_URL}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, name, ftp_override }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Registrierung fehlgeschlagen.");
  await AsyncStorage.setItem(TOKEN_KEY, data.access_token);
  await AsyncStorage.setItem(USER_KEY, JSON.stringify(data));
  return data;
}

export async function login({ email, password }) {
  const res = await fetch(`${BASE_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Login fehlgeschlagen.");
  await AsyncStorage.setItem(TOKEN_KEY, data.access_token);
  await AsyncStorage.setItem(USER_KEY, JSON.stringify(data));
  return data;
}

export async function logout() {
  await AsyncStorage.removeItem(TOKEN_KEY);
  await AsyncStorage.removeItem(USER_KEY);
}

export async function getToken() {
  return AsyncStorage.getItem(TOKEN_KEY);
}

export async function getUser() {
  const raw = await AsyncStorage.getItem(USER_KEY);
  return raw ? JSON.parse(raw) : null;
}

export async function isLoggedIn() {
  const token = await getToken();
  return !!token;
}
