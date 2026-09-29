const fs = require("fs");
const crypto = require("crypto");

const ENV_PATH = "C:/Users/Liii/nexent/deploy/env/.env";
const SECRET_PATH = "C:/Users/Liii/nexent/deploy/env/.acceptance-admin.env";
const USER_ID = "eec5c828-6b53-406d-b1c2-d5df106bc87a";
const ADMIN_EMAIL = "seasight.acceptance@nexent.com";
const ADMIN_API = `http://localhost:8000/auth/v1/admin/users/${USER_ID}`;
const SIGNIN_API = "http://localhost:3000/api/user/signin";

function readEnv(path) {
  const raw = fs.readFileSync(path, "utf8");
  return (key) => {
    const m = raw.match(new RegExp(`^${key}=(.*)$`, "m"));
    if (!m) return "";
    return m[1].trim().replace(/^"|"$/g, "");
  };
}

function newPassword() {
  let pw = crypto
    .randomBytes(12)
    .toString("base64url")
    .replace(/[^A-Za-z0-9]/g, "")
    .slice(0, 14);
  if (!/[A-Z]/.test(pw)) pw += "A";
  if (!/[a-z]/.test(pw)) pw += "z";
  if (!/\d/.test(pw)) pw += "9";
  return pw;
}

async function trySignin(password) {
  const r = await fetch(SIGNIN_API, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: ADMIN_EMAIL, password }),
  });
  return r.ok;
}

async function main() {
  const get = readEnv(ENV_PATH);
  const serviceKey = get("SERVICE_ROLE_KEY");
  if (!serviceKey) throw new Error("SERVICE_ROLE_KEY missing");

  if (fs.existsSync(SECRET_PATH)) {
    const secret = fs.readFileSync(SECRET_PATH, "utf8");
    const m = secret.match(/^NEXENT_TENANT_PASSWORD=(.*)$/m);
    if (m && (await trySignin(m[1].trim()))) {
      console.log("EXISTING_SECRET_OK");
      return;
    }
  }

  const pw = newPassword();
  const r = await fetch(ADMIN_API, {
    method: "PUT",
    headers: {
      apikey: serviceKey,
      Authorization: `Bearer ${serviceKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ password: pw, email_confirm: true }),
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`admin update failed ${r.status} ${text.slice(0, 200)}`);
  }
  if (!(await trySignin(pw))) {
    throw new Error("tenant login failed after reset");
  }
  fs.writeFileSync(SECRET_PATH, `NEXENT_TENANT_PASSWORD=${pw}\n`, {
    mode: 0o600,
  });
  console.log("ADMIN_RESET_OK_SECRET_SAVED");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
