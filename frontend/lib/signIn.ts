/**
 * Opens the provider sign-in page in the system browser (OAuth providers block embedded windows).
 */
export async function openSignInUrl(url: string): Promise<boolean> {
  if (typeof url !== "string" || !/^https?:\/\//i.test(url)) {
    throw new Error("Sign-in URL was missing or invalid. Try again.");
  }
  if (typeof window !== "undefined" && window.kinexis?.openExternalUrl) {
    const opened = await window.kinexis.openExternalUrl(url);
    if (opened === false) {
      throw new Error("Could not open the system browser for sign-in.");
    }
    return true;
  }
  if (typeof window !== "undefined" && window.kinexis?.openAuthWindow) {
    return window.kinexis.openAuthWindow(url);
  }
  const win = window.open(url, "_blank", "noopener,noreferrer");
  if (!win) {
    throw new Error("Popup blocked — allow popups for Kinexis and try again.");
  }
  return true;
}
