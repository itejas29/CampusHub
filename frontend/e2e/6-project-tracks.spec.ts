import { expect, test } from "@playwright/test";
import { signIn } from "./helpers";

// Semester VIII: the student picks a track, and the track decides the form.
test("a final-year student registers for the in-house Major Project track", async ({ page }) => {
  await signIn(page, "pooja.shah.081@campushub.example.com");
  await page.goto("/internships");
  const card = page.locator("section").filter({ has: page.getByRole("heading", { name: /Major Project \/ Industry Internship/ }) });
  await card.getByRole("button", { name: "Fill in my details" }).click();
  const form = page.getByRole("dialog", { name: /Register for Major Project/ });

  // Nothing to submit until a track is chosen; the industry track asks for a host.
  await expect(form.getByRole("button", { name: "Register" })).toBeDisabled();
  await form.getByRole("radio", { name: /Industry Internship/ }).check();
  await expect(form.getByLabel("Host organisation")).toBeVisible();
  await form.getByRole("radio", { name: /Major Project \(in-house\)/ }).check();
  await expect(form.getByLabel("Host organisation")).toHaveCount(0);
  await expect(form.getByText("Offer Letter")).toHaveCount(0);

  await form.getByRole("button", { name: "Register" }).click();
  await expect(page.getByText("You are enrolled.")).toBeVisible();
  const record = page.locator("section").filter({ has: page.getByRole("heading", { name: "My internships" }) });
  await expect(record.getByText("Major Project (in-house)")).toBeVisible();
  await expect(record.getByRole("heading", { name: /Major Project \/ Industry Internship/ })).toBeVisible();
});
