import axios from "axios";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const api = axios.create({ baseURL: API_URL });

export const getToken = () =>
  typeof window === "undefined" ? null : localStorage.getItem("nf_token");

export const withToken = (url: string) => {
  const t = getToken();
  return t ? `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(t)}` : url;
};

api.interceptors.request.use((cfg) => {
  const t = getToken();
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401 && typeof window !== "undefined" && !location.pathname.startsWith("/login")) {
      localStorage.removeItem("nf_token");
      location.href = "/login";
    }
    return Promise.reject(err);
  }
);