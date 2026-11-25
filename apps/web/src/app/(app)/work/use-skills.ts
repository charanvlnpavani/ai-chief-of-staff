import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api";
import { qk } from "@/lib/queries";

export function useSkills() {
  return useQuery({
    queryKey: [...qk.professional, "skills"],
    queryFn: () => unwrap(api.GET("/api/v1/professional/skills")),
  });
}
