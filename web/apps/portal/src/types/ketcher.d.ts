/**
 * Ambient type declarations for Ketcher packages.
 *
 * Both ketcher-react and ketcher-standalone ship .d.ts files, but their
 * package.json `exports` maps omit the `types` condition. TypeScript with
 * moduleResolution: "bundler" uses the exports map and can't find the types.
 *
 * These declarations bridge the gap until the packages fix their exports.
 */

declare module "ketcher-react" {
  import type { Ketcher } from "ketcher-core";
  import type { ComponentType } from "react";

  export interface EditorProps {
    staticResourcesUrl?: string;
    structServiceProvider: unknown;
    onInit?: (ketcher: Ketcher) => void;
    errorHandler?: (message: string) => void;
  }

  export const Editor: ComponentType<EditorProps>;
}

declare module "ketcher-standalone" {
  export class StandaloneStructServiceProvider {
    constructor();
  }
}

declare module "ketcher-react/dist/index.css" {
  const content: string;
  export default content;
}
