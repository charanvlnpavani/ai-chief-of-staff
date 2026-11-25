"use client";

import { Suspense } from "react";

import { ChiefOfStaff } from "./chief-of-staff";

export default function ChiefPage() {
  return (
    <Suspense fallback={null}>
      <ChiefOfStaff />
    </Suspense>
  );
}
