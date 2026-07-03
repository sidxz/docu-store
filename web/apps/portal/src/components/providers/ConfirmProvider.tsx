"use client";

import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

export interface ConfirmOptions {
  title: string;
  description?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Render the confirm action in the destructive (red) style. */
  destructive?: boolean;
}

type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmFn | null>(null);

/**
 * Mounts a single shared AlertDialog and exposes an imperative, promise-based
 * `confirm()` via {@link useConfirm} — a framework-native drop-in for
 * `window.confirm`. One dialog, one style, used by every destructive action so
 * confirmations stay consistent instead of each component rolling its own.
 */
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  const resolver = useRef<((value: boolean) => void) | null>(null);

  const confirm = useCallback<ConfirmFn>((opts) => {
    setOptions(opts);
    setOpen(true);
    return new Promise<boolean>((resolve) => {
      resolver.current = resolve;
    });
  }, []);

  // Settle the pending promise exactly once, then close. Cancel / Escape /
  // overlay all route through onOpenChange(false); the action button settles
  // true first (Radix composes our onClick before its own close handler).
  const settle = useCallback((value: boolean) => {
    resolver.current?.(value);
    resolver.current = null;
    setOpen(false);
  }, []);

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <AlertDialog open={open} onOpenChange={(next) => !next && settle(false)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{options?.title}</AlertDialogTitle>
            {options?.description ? (
              <AlertDialogDescription>{options.description}</AlertDialogDescription>
            ) : null}
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{options?.cancelLabel ?? "Cancel"}</AlertDialogCancel>
            <AlertDialogAction
              variant={options?.destructive ? "destructive" : "default"}
              onClick={() => settle(true)}
            >
              {options?.confirmLabel ?? "Confirm"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </ConfirmContext.Provider>
  );
}

/** Imperative confirmation dialog. `await confirm({...})` → true if confirmed. */
export function useConfirm(): ConfirmFn {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error("useConfirm must be used within ConfirmProvider");
  return ctx;
}
