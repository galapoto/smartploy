/** Only an explicitly published, approved Chrome Web Store ID becomes a UI link.
 * The URL contains no applicant, credential, job or private packet data.
 */
const CHROME_EXTENSION_ID = /^[a-p]{32}$/;

export function chromeWebStoreUrlFromId(id: unknown): string | null {
  if (typeof id !== "string" || !CHROME_EXTENSION_ID.test(id)) return null;
  return "https://chromewebstore.google.com/detail/" + id;
}

// Deployment operator sets the ID only AFTER the approved listing is published.
export const chromeWebStoreLink = chromeWebStoreUrlFromId(
  import.meta.env.VITE_SMARTPLOY_CHROME_WEB_STORE_ID,
);
