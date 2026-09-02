"use client";

import { use } from "react";
import { LiteratureLayout } from "@/components/literature/LiteratureLayout";

export default function LiteraturePage({
  params,
}: {
  params: Promise<{ workspace: string }>;
}) {
  const { workspace } = use(params);

  return (
    <div className="-m-6 h-[calc(100%+3rem)]">
      <LiteratureLayout workspace={workspace} />
    </div>
  );
}
