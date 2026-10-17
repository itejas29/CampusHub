import { expect, type Page } from "@playwright/test";

/** Every seeded demo account shares this password (README → Demo accounts). */
export const DEMO_PASSWORD = "Campus@123";

export const ACCOUNTS = {
  cssiCoordinator: "sneha.iyer@campushub.example.com",
  summerMentor: "meera.krishnan@campushub.example.com",
} as const;

/** Sign in through the real form, the way a person does. */
export async function signIn(page: Page, email: string, password = DEMO_PASSWORD) {
  await page.goto("/login");
  await page.getByLabel("University email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

/** Call the API as the signed-in user, to check what the screen claims. */
export async function apiGet<T>(page: Page, path: string): Promise<T> {
  const token = await page.evaluate(() => localStorage.getItem("campushub.access"));
  const response = await page.request.get(`/api/v1${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok(), `GET ${path} → ${response.status()}`).toBeTruthy();
  return (await response.json()) as T;
}
