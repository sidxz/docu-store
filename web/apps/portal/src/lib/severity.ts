/** PrimeReact severity → shadcn Badge variant (used during and after migration). */
export const severityToVariant = {
  success: "success",
  info: "info",
  warning: "warning",
  danger: "destructive",
  secondary: "secondary",
} as const;
export type PrimeSeverity = keyof typeof severityToVariant;
