/* Pure, testable rules for SmartPloy's local-only browser companion. */
export const SCHEMA = "smartploy.browser_handoff.v1";

export class PacketError extends Error {}

function text(value, maximum = 10000) {
  if (typeof value !== "string" || value.length > maximum ||
      /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(value)) {
    throw new PacketError("The application packet contains invalid text");
  }
  return value;
}

function pathIsSameJob(current, target) {
  const prefix = target.pathname.replace(/\/+$/, "");
  return current.pathname === prefix ||
    current.pathname === prefix + "/" ||
    current.pathname.startsWith(prefix + "/");
}

export function validatePacket(input, activeTabUrl, now = Date.now()) {
  let packet;
  try {
    if (typeof input === "string" && input.length > 40000) {
      throw new PacketError("The application packet is too large");
    }
    packet = typeof input === "string" ? JSON.parse(input) : input;
  } catch (error) {
    if (error instanceof PacketError) throw error;
    throw new PacketError("Paste a valid SmartPloy application packet");
  }
  if (!packet || typeof packet !== "object" || packet.schema !== SCHEMA) {
    throw new PacketError("This is not a supported SmartPloy application packet");
  }
  if (!Number.isInteger(packet.revision) || packet.revision < 1 ||
      !/^kit-[a-f0-9]{30}$/.test(packet.workspace_id) ||
      !/^[a-f0-9]{64}$/.test(packet.document_sha256)) {
    throw new PacketError("Application packet revision or document identity is invalid");
  }
  const issued = Date.parse(packet.issued_at);
  const expires = Date.parse(packet.expires_at);
  if (!Number.isFinite(issued) || !Number.isFinite(expires) ||
      issued > now + 120000 || expires <= now ||
      expires - issued <= 0 || expires - issued > 900000) {
    throw new PacketError("The application packet has expired or has an invalid time window");
  }
  let target;
  let current;
  try {
    target = new URL(packet.application_url);
    current = new URL(activeTabUrl);
  } catch {
    throw new PacketError("The packet or browser tab has an invalid URL");
  }
  if (target.protocol !== "https:" || current.protocol !== "https:" ||
      target.username || target.password || target.port !== "" ||
      current.origin !== target.origin || !pathIsSameJob(current, target)) {
    throw new PacketError("Open the exact employer job/application page linked from SmartPloy");
  }
  const f = packet.fields;
  if (!f || typeof f !== "object") {
    throw new PacketError("The packet does not contain reviewed application details");
  }
  const fields = {
    full_name: text(f.full_name, 160),
    first_name: text(f.first_name, 160),
    last_name: text(f.last_name, 160),
    email: text(f.email, 254),
    phone: text(f.phone, 40),
    location: text(f.location, 160),
    linkedin: text(f.linkedin, 350),
    github: text(f.github, 350),
    cover_letter: text(f.cover_letter, 10000)
  };
  if (!fields.full_name.trim() ||
      !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(fields.email)) {
    throw new PacketError("This packet needs a verified name and email address");
  }
  if (!packet.privacy || packet.privacy.approved_contact_only !== true ||
      packet.privacy.original_cv_included !== false ||
      packet.privacy.employer_submit_allowed_without_new_approval !== false) {
    throw new PacketError("The packet does not meet SmartPloy's privacy boundaries");
  }
  return {
    schema: SCHEMA,
    workspace_id: packet.workspace_id,
    application_url: target.href,
    company: text(packet.company, 150),
    role_title: text(packet.role_title, 150),
    revision: packet.revision,
    document_sha256: packet.document_sha256,
    expires_at: packet.expires_at,
    fields
  };
}

function tidy(raw) {
  return String(raw || "").toLowerCase()
    .replace(/[()_.:*/\-]+/g, " ")
    .replace(/\s+/g, " ").trim();
}

export function identifyField(row) {
  const kind = tidy(row.type);
  if (row.disabled || row.readonly || !row.visible ||
      ["file", "hidden", "password", "checkbox", "radio", "submit", "button", "reset"].includes(kind)) {
    return null;
  }
  if (!["text", "email", "tel", "url", "search", "textarea"].includes(kind)) return null;
  const auto = tidy(row.autocomplete);
  if (auto === "given name") return "first_name";
  if (auto === "family name") return "last_name";
  if (auto === "email") return "email";
  if (auto === "tel") return "phone";
  if (auto === "name") return "full_name";
  if (auto === "address level2") return "location";

  const label = tidy(row.label || row.placeholder);
  const attr = tidy(row.name || row.id);
  const both = [label, attr].filter(Boolean).join(" ");
  if (/(company|employer|organization|organisation|referral|referee|recommender)/.test(both)) return null;

  const matches = [
    ["first_name", /^(first name|given name|etunimi|förnamn)$/],
    ["last_name", /^(last name|surname|family name|sukunimi|efternamn)$/],
    ["email", /^(email|e mail|email address|sähköposti|sähköpostiosoite|e post)$/],
    ["phone", /^(phone|phone number|telephone|mobile|puhelin|puhelinnumero|telefon)$/],
    ["linkedin", /^(linkedin|linkedin url|linkedin profile|linkedin profile url)$/],
    ["github", /^(github|github url|github profile|github profile url)$/],
    ["full_name", /^(full name|your name|applicant name|koko nimi|nimi|namn)$/],
    ["location", /^(current location|location|city|sijainti|paikkakunta|ort)$/],
    ["cover_letter", /^(cover letter|cover letter text|motivation|motivation letter|motivation message|saatekirje|personligt brev)$/],
    ["additional_information", /^(additional information|additional comments|lisätiedot|övrig information)$/],
  ];
  for (const [field, rx] of matches) {
    if (rx.test(label) || rx.test(attr)) return field;
  }
  return null;
}

export function planFields(elements, packet) {
  const fields = packet.fields;
  if (!Array.isArray(elements) || elements.length > 250) {
    throw new PacketError("Unable to inspect employer form fields safely");
  }
  const named = elements.map((row) => ({...row, key: identifyField(row)}));
  const hasCoverLetterField = named.some((row) => row.key === "cover_letter");
  const planned = [];
  const unresolvedRequired = [];
  const skippedUploads = [];
  for (const row of named) {
    const label = text(String(row.label || row.name || row.id || "Unlabelled field"), 150);
    if (row.type === "file") {
      skippedUploads.push(label);
      if (row.required && !row.hasValue) unresolvedRequired.push(label + " (file upload)");
      continue;
    }
    let key = row.key;
    if (key === "additional_information") {
      key = hasCoverLetterField ? null : "cover_letter";
    }
    if (key && typeof fields[key] === "string" &&
        fields[key].trim() && !row.hasValue && !row.disabled && !row.readonly &&
        (!row.maxLength || row.maxLength < 0 || fields[key].length <= row.maxLength)) {
      planned.push({
        index: row.index,
        key,
        value: fields[key],
        label,
        expected_id: row.id || "",
        expected_name: row.name || "",
        expected_type: row.type || "text",
      });
    } else if (row.required && !row.hasValue) {
      unresolvedRequired.push(label);
    }
  }
  return {
    actions: planned,
    unresolvedRequired,
    skippedUploads,
    requiresSiteReview: true,
    autoSubmitAllowed: false
  };
}
