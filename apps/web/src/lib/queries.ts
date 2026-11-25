import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api";

/** Query keys in one place, so mutations invalidate exactly what they change. */
export const qk = {
  me: ["me"] as const,
  dashboard: ["dashboard"] as const,
  tasks: ["tasks"] as const,
  taskLists: ["task-lists"] as const,
  habits: ["habits"] as const,
  habitExceptions: ["habit-exceptions"] as const,
  goals: ["goals"] as const,
  professional: ["professional"] as const,
  ai: ["ai"] as const,
  settings: ["settings"] as const,
};

export function useMe() {
  return useQuery({
    queryKey: qk.me,
    queryFn: () => unwrap(api.GET("/api/v1/users/me")),
    staleTime: 60_000,
  });
}
