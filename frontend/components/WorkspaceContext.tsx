"use client";
import { createContext, useContext, type Dispatch, type SetStateAction } from "react";
import type { CurrentUser, Product } from "@/lib/api";
export type WorkspaceState = {
  demo: boolean; user: CurrentUser | null;
  products: Product[]; setProducts: Dispatch<SetStateAction<Product[]>>;
  selectedProductId: string; setSelectedProductId: Dispatch<SetStateAction<string>>;
  selectionLocked: boolean; setSelectionLocked: Dispatch<SetStateAction<boolean>>;
};
export const WorkspaceContext = createContext<WorkspaceState | null>(null);
export function useWorkspace() {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("Workspace context is required.");
  return value;
}
