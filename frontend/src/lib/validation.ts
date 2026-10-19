// The checks the server makes (backend/app/schemas/fields.py), run in the
// form so a mistake shows before submitting. The server still decides: these
// only spare a round trip, and the messages match the server's.
//
// Each returns the problem to show, or undefined when the value is fine. An
// empty value is fine here — whether a field is required is the form's call.

const collapse = (value: string) => value.replace(/\s+/g, " ").trim();

export function phoneError(value: string): string | undefined {
  const raw = value.trim();
  if (!raw) return undefined;
  if (!/^[+()\d\s.-]{1,25}$/.test(raw)) {
    return "Enter a phone number using digits only (spaces, - and + are fine).";
  }
  let digits = raw.replace(/\D/g, "");
  if (raw.startsWith("+") && !digits.startsWith("91")) {
    return digits.length >= 8 && digits.length <= 15
      ? undefined
      : "An international number has 8 to 15 digits after the +.";
  }
  if (digits.startsWith("91") && digits.length === 12) digits = digits.slice(2);
  if (digits.length === 10 && "6789".includes(digits[0])) {
    return new Set(digits).size === 1 ? "That is not a real phone number." : undefined;
  }
  // Mobile written with the trunk 0, or a landline with its STD code.
  if (digits.length === 11 && digits[0] === "0" && digits[1] !== "0" && new Set(digits.slice(1)).size > 1) {
    return undefined;
  }
  return "Enter a 10-digit mobile number (starting 6–9), a landline with its STD code, "
    + "or an international number starting with +.";
}

export function personNameError(value: string): string | undefined {
  const name = collapse(value);
  if (!name) return undefined;
  if (name.length > 100) return "Keep the name to 100 characters.";
  // Vowel signs of Indic scripts are marks, not letters; they belong to their letter.
  const bare = name.normalize("NFC").replace(/\p{M}/gu, "");
  const shaped = /^\p{L}+(?:[ .'-]\p{L}*)*\.?$/u.test(bare);
  const hasWord = bare.split(" ").some((part) => part.replace(/[.'-]/g, "").length >= 2);
  return shaped && hasWord
    ? undefined
    : "Enter a real name — letters only, at least one word of two letters (e.g. “Asha Patel” or “Dr. R. K. Shah”).";
}

export function urlError(value: string): string | undefined {
  const link = value.trim();
  if (!link) return undefined;
  if (link.length > 500) return "Keep the link to 500 characters.";
  return /^https?:\/\/[A-Za-z0-9.-]+\.[A-Za-z]{2,}(:\d{2,5})?(\/[^\s<>"]*)?$/.test(link)
    ? undefined
    : "Enter a web address starting with https://";
}

export function pincodeError(value: string): string | undefined {
  const pin = value.trim();
  if (!pin) return undefined;
  return /^[1-9]\d{5}$/.test(pin) ? undefined : "Enter a 6-digit PIN code.";
}

export function emailError(value: string): string | undefined {
  const email = value.trim();
  if (!email) return undefined;
  return /^[^\s@<>]+@[^\s@<>]+\.[A-Za-z]{2,}$/.test(email) ? undefined : "Enter an email address like name@example.com.";
}

export function placeError(value: string): string | undefined {
  const place = collapse(value);
  if (!place) return undefined;
  return /^\p{L}[\p{L}\p{M} .'()&-]*$/u.test(place) && !/\d/.test(place)
    ? undefined
    : "Use letters only for a place name.";
}

export function textError(value: string): string | undefined {
  return /[<>]/.test(value) ? "Remove the < and > characters." : undefined;
}

const COMMON_PASSWORDS = new Set([
  "password", "password1", "password123", "12345678", "123456789", "1234567890",
  "qwerty123", "campus@123", "campushub", "pdeu@123", "pdeu1234", "pdpu@123",
  "welcome@123", "admin@123", "abcd@1234", "iloveyou", "india@123",
]);

/** The server's password policy (services/accounts.check_password_policy). */
export function newPasswordError(
  password: string, person?: { email?: string; full_name?: string } | null,
): string | undefined {
  if (!password) return undefined;
  const missing = [
    password.length < 10 && "at least 10 characters",
    !(/[A-Za-z]/.test(password) && /\d/.test(password)) && "both letters and digits",
  ].filter(Boolean);
  if (missing.length) return `Use a password with ${missing.join(" and ")}.`;
  const lowered = password.toLowerCase();
  if (COMMON_PASSWORDS.has(lowered)) return "That password is too common — choose another.";
  const personal = [
    (person?.email ?? "").split("@")[0].toLowerCase(),
    ...(person?.full_name ?? "").split(/[\s.]+/).filter((p) => p.length >= 4).map((p) => p.toLowerCase()),
  ];
  if (personal.some((p) => p.length >= 4 && lowered.includes(p))) {
    return "Don't use your name or email in your password.";
  }
  return undefined;
}
