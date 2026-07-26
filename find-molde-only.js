/**
 * find-molde-only.js
 *
 * Finner hovedenheter registrert i Molde kommune (kommunenr 1506) som
 * IKKE har underenheter (avdelinger) registrert i andre kommuner, og som
 * selv ikke er en underenhet av noe utenfor Molde.
 *
 * Dette er en gratis, offentlig proxy for "lokal bedrift, ikke del av en
 * kjede/konsern med avdelinger andre steder" — basert på Brønnøysund-
 * registerets Enhetsregisteret API.
 *
 * OBS: Dette fanger IKKE opp eierskap via aksjeselskap-konsern der
 * morselskapet ikke har egne underenheter i Molde (f.eks. et lite AS i
 * Molde som er 100% eid av et holdingselskap i Oslo, men uten registrerte
 * "underenheter"). Den typen konserntilknytning ligger ikke i denne APIen
 * i det hele tatt (verken gratis eller betalt via Brreg) — det er data
 * Proff/Purehelp selger separat. Dette scriptet løser altså "er bedriften
 * en lokal enkeltstående virksomhet uten avdelinger andre steder", ikke
 * "er bedriften eid av noe utenfor Molde".
 *
 * Kjør med: node find-molde-only.js
 * Krever Node.js 18+ (innebygget fetch).
 */

const KOMMUNENUMMER = "1506"; // Molde (etter sammenslåing 2020)
const BASE = "https://data.brreg.no/enhetsregisteret/api";
const PAGE_SIZE = 100; // Brreg sin API tillater opp til 10000, men vi holder oss høflige
const DELAY_MS = 150; // liten pause mellom kall for å ikke hamre APIet

// Sett til null for å ta med alle organisasjonsformer, eller en liste for å filtrere.
// Vanlige B2B-relevante former: AS, ASA, ENK, DA, ANS
const ORGFORM_FILTER = ["AS", "ASA", "ENK", "DA", "ANS"];

function sleep(ms) {
  return new Promise((res) => setTimeout(res, ms));
}

async function fetchJson(url) {
  const res = await fetch(url, {
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`Feil ved henting av ${url}: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

// Henter alle hovedenheter med forretningsadresse i Molde
async function fetchAllMoldeUnits() {
  let page = 0;
  let all = [];
  while (true) {
    const url = `${BASE}/enheter?kommunenummer=${KOMMUNENUMMER}&size=${PAGE_SIZE}&page=${page}`;
    const data = await fetchJson(url);
    const units = data._embedded?.enheter ?? [];
    all = all.concat(units);

    const totalPages = data.page?.totalPages ?? 1;
    page++;
    if (page >= totalPages || units.length === 0) break;
    await sleep(DELAY_MS);
  }
  return all;
}

// Henter underenheter for en gitt hovedenhet (org.nr)
async function fetchUnderenheter(orgnr) {
  const url = `${BASE}/underenheter?overordnetEnhet=${orgnr}&size=100`;
  const data = await fetchJson(url);
  return data._embedded?.underenheter ?? [];
}

async function main() {
  console.log(`Henter hovedenheter i kommune ${KOMMUNENUMMER} (Molde)...`);
  const units = await fetchAllMoldeUnits();
  console.log(`Fant ${units.length} enheter totalt før filtrering.`);

  const results = [];
  let checked = 0;

  for (const unit of units) {
    checked++;
    if (checked % 25 === 0) {
      console.log(`  ...sjekket ${checked}/${units.length}`);
    }

    // Hopp over enheter som selv er underenheter (avdelinger av noe annet)
    if (unit.overordnetEnhet) continue;

    // Filtrer på organisasjonsform hvis satt
    if (ORGFORM_FILTER && !ORGFORM_FILTER.includes(unit.organisasjonsform?.kode)) {
      continue;
    }

    // Hopp over slettede / avviklede / konkurs
    if (unit.slettedato || unit.konkurs || unit.underAvvikling) continue;

    let underenheter = [];
    try {
      underenheter = await fetchUnderenheter(unit.organisasjonsnummer);
    } catch (e) {
      console.warn(`  Kunne ikke hente underenheter for ${unit.navn}: ${e.message}`);
    }
    await sleep(DELAY_MS);

    const eksterneUnderenheter = underenheter.filter(
      (u) => u.beliggenhetsadresse?.kommunenummer !== KOMMUNENUMMER
    );

    if (eksterneUnderenheter.length === 0) {
      results.push({
        orgnr: unit.organisasjonsnummer,
        navn: unit.navn,
        orgform: unit.organisasjonsform?.kode ?? "",
        ansatte: unit.antallAnsatte ?? "",
        naeringskode: unit.naeringskode1?.beskrivelse ?? "",
        adresse: (unit.forretningsadresse?.adresse || []).join(" "),
        postnr: unit.forretningsadresse?.postnummer ?? "",
        poststed: unit.forretningsadresse?.poststed ?? "",
        telefon: unit.telefon ?? "",
        hjemmeside: unit.hjemmeside ?? "",
        antallUnderenheter: underenheter.length,
      });
    }
  }

  console.log(`\nFant ${results.length} bedrifter i Molde uten avdelinger utenfor Molde.\n`);

  // Skriv til CSV
  const fs = require("fs");
  const header = [
    "orgnr",
    "navn",
    "orgform",
    "ansatte",
    "naeringskode",
    "adresse",
    "postnr",
    "poststed",
    "telefon",
    "hjemmeside",
    "antallUnderenheter",
  ];
  const csvRows = [header.join(",")];
  for (const r of results) {
    csvRows.push(
      header
        .map((h) => `"${String(r[h] ?? "").replace(/"/g, '""')}"`)
        .join(",")
    );
  }
  fs.writeFileSync("molde-bedrifter.csv", csvRows.join("\n"), "utf-8");
  console.log("Skrevet til molde-bedrifter.csv");
}

main().catch((e) => {
  console.error("Noe gikk feil:", e);
  process.exit(1);
});
