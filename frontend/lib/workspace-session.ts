/** Selection metadata is private to the last verified account. Delivery guards stay account-scoped. */
export function clearWorkspaceSelection() {
  try {
    localStorage.removeItem("product_id"); localStorage.removeItem("run_id");
    localStorage.removeItem("signalx:account");
    for (const key of Object.keys(sessionStorage)) if (key.startsWith("signalx:run:")) sessionStorage.removeItem(key);
  } catch { /* Storage may be unavailable; callers also clear React state. */ }
}
export function verifyWorkspaceAccount(id: string) {
  try {
    const previous = localStorage.getItem("signalx:account");
    if (previous !== id) clearWorkspaceSelection();
    localStorage.setItem("signalx:account", id);
    return previous !== id;
  } catch { return true; }
}
