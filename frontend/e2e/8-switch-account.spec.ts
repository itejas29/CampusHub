import { expect, test } from "@playwright/test";
import { ACCOUNTS, signIn } from "./helpers";

// Signing out and in as someone else starts them on their own dashboard,
// not on the page the last person had open (which they cannot access).
test("the next person to sign in does not land on the last person's page", async ({ page }) => {
  await signIn(page, ACCOUNTS.cssiCoordinator);
  await page.goto("/internships/mentor-assignment");
  await expect(page.getByRole("heading", { name: "Mentor allocation" })).toBeVisible();

  // Signed out from right here, on a page a student cannot open.
  await page.getByRole("button", { name: "Sign out" }).first().click();
  await expect(page).toHaveURL(/\/login$/);

  await signIn(page, "riya.chauhan.031@campushub.example.com");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByText(/do not have access/i)).toHaveCount(0);
});
