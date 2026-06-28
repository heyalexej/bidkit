#!/usr/bin/env bun
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";

console.time("finance-smoke");

const opts = parseArgs(process.argv.slice(2));
const raw = readJson(opts.credentials);
const creds = raw.credentials ?? raw;
const signingKey = readJson(opts.signingKey ?? defaultSigningKeyPath());
if (!signingKey?.jwe || !(signingKey.privateKeyPem || signingKey.privateKey)) {
  throw new Error("Missing signing key fields: jwe and privateKey/privateKeyPem");
}

const requireFromNodeProject = createRequire(path.join(opts.nodeProject, "package.json"));
const ebayApiModule = await import(requireFromNodeProject.resolve("ebay-api"));
const eBayApi = ebayApiModule.default;
const { Locale, MarketplaceId, SiteId } = ebayApiModule;

const marketplace = opts.marketplace;
const scopes = normalizeScopes(creds.granted_scopes ?? creds.scopes ?? []);
const client = new eBayApi({
  appId: creds.app_id ?? creds.client_id,
  certId: creds.cert_id ?? creds.client_secret,
  sandbox: false,
  marketplaceId: MarketplaceId[marketplace] ?? marketplace,
  siteId: siteIdFor(marketplace, SiteId),
  acceptLanguage: localeFor(marketplace, Locale),
  contentLanguage: localeFor(marketplace, Locale),
  scope: scopes,
  signature: {
    jwe: signingKey.jwe,
    privateKey: signingKey.privateKeyPem ?? signingKey.privateKey,
    cipher: signingKey.cipher ?? "sha256",
  },
});

client.OAuth2.setCredentials({
  refresh_token: creds.refresh_token,
  access_token: "",
  expires_in: 0,
  token_type: "User Access Token",
});
await client.OAuth2.refreshToken();

const rows = [];
await addFundsSummary(rows, client);
await addPayouts(rows, client, opts.limit);
await addTransactions(rows, client, opts.limit);
await addTransactionSummaries(rows, client);

console.table(rows);
console.timeEnd("finance-smoke");

if (opts.strict && rows.some((row) => row.status === "ERR")) {
  process.exitCode = 1;
}

function parseArgs(argv) {
  const args = {
    credentials: "/tmp/toktok.json",
    marketplace: "EBAY_DE",
    nodeProject: "/Users/buzz/.pi/agent/skills/ebay-cli-next",
    signingKey: null,
    limit: 3,
    strict: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--credentials") args.credentials = argv[++i];
    else if (arg === "--marketplace") args.marketplace = argv[++i];
    else if (arg === "--node-project") args.nodeProject = argv[++i];
    else if (arg === "--signing-key") args.signingKey = argv[++i];
    else if (arg === "--limit") args.limit = Number(argv[++i]);
    else if (arg === "--strict") args.strict = true;
    else throw new Error(`Unknown argument: ${arg}`);
  }
  return args;
}

function readJson(file) {
  if (!file || !fs.existsSync(file)) throw new Error(`Missing JSON file: ${file}`);
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function defaultSigningKeyPath() {
  const xdg = process.env.XDG_CONFIG_HOME || path.join(os.homedir(), ".config");
  const primary = path.join(xdg, "ebay-cli", "signing-key.json");
  if (fs.existsSync(primary)) return primary;
  return path.join(os.homedir(), ".ebay-cli", "signing-key.json");
}

function normalizeScopes(scopes) {
  return typeof scopes === "string" ? scopes.split(/\s+/).filter(Boolean) : scopes;
}

function siteIdFor(marketplace, SiteId) {
  const values = {
    EBAY_AU: SiteId.EBAY_AU,
    EBAY_DE: SiteId.EBAY_DE,
    EBAY_ES: SiteId.EBAY_ES,
    EBAY_FR: SiteId.EBAY_FR,
    EBAY_GB: SiteId.EBAY_GB,
    EBAY_IT: SiteId.EBAY_IT,
    EBAY_US: SiteId.EBAY_US,
  };
  return values[marketplace] ?? SiteId.EBAY_DE;
}

function localeFor(marketplace, Locale) {
  const values = {
    EBAY_AU: Locale.en_AU,
    EBAY_DE: Locale.de_DE,
    EBAY_ES: Locale.es_ES,
    EBAY_FR: Locale.fr_FR,
    EBAY_GB: Locale.en_GB,
    EBAY_IT: Locale.it_IT,
    EBAY_US: Locale.en_US,
  };
  return values[marketplace] ?? Locale.de_DE;
}

function money(amount) {
  return {
    value: amount?.value ?? null,
    currency: amount?.currency ?? null,
  };
}

async function addFundsSummary(rows, client) {
  try {
    const summary = await client.sell.finances.sign.getSellerFundsSummary();
    rows.push({
      check: "sellerFundsSummary",
      status: "OK",
      available: money(summary?.availableFunds).value,
      processing: money(summary?.processingFunds).value,
      onHold: money(summary?.fundsOnHold).value,
      total: money(summary?.totalFunds).value,
      currency: money(summary?.totalFunds).currency,
    });
  } catch (error) {
    rows.push({ check: "sellerFundsSummary", status: "ERR", message: errorMessage(error) });
  }
}

async function addPayouts(rows, client, limit) {
  try {
    const payouts = await client.sell.finances.sign.getPayouts({ limit });
    rows.push({
      check: "payouts",
      status: "OK",
      count: payouts?.payouts?.length ?? 0,
      total: payouts?.total ?? null,
      firstStatus: payouts?.payouts?.[0]?.payoutStatus ?? null,
      firstCurrency: payouts?.payouts?.[0]?.amount?.currency ?? null,
    });
  } catch (error) {
    rows.push({ check: "payouts", status: "ERR", message: errorMessage(error) });
  }
}

async function addTransactions(rows, client, limit) {
  try {
    const transactions = await client.sell.finances.sign.getTransactions({ limit });
    rows.push({
      check: "transactions",
      status: "OK",
      count: transactions?.transactions?.length ?? 0,
      total: transactions?.total ?? null,
      types: unique((transactions?.transactions ?? []).map((item) => item.transactionType)),
      firstDate: transactions?.transactions?.[0]?.transactionDate ?? null,
      firstCurrency: transactions?.transactions?.[0]?.amount?.currency ?? null,
    });
  } catch (error) {
    rows.push({ check: "transactions", status: "ERR", message: errorMessage(error) });
  }
}

async function addTransactionSummaries(rows, client) {
  const filters = [
    "transactionStatus:{PAYOUT}",
    "transactionStatus:{FUNDS_AVAILABLE_FOR_PAYOUT}",
    "transactionStatus:{FUNDS_PROCESSING}",
    "transactionStatus:{FUNDS_ON_HOLD}",
  ];
  for (const filter of filters) {
    try {
      const summary = await client.sell.finances.sign.getTransactionSummary({ filter });
      rows.push({
        check: "transactionSummary",
        status: "OK",
        filter,
        creditCount: summary?.creditCount ?? null,
        debitCount: summary?.debitCount ?? null,
        creditAmount: summary?.creditAmount?.value ?? null,
        debitAmount: summary?.debitAmount?.value ?? null,
        currency: summary?.creditAmount?.currency ?? summary?.debitAmount?.currency ?? null,
        holdCount: summary?.onHoldCount ?? null,
        holdAmount: summary?.onHoldAmount?.value ?? null,
      });
    } catch (error) {
      rows.push({ check: "transactionSummary", status: "ERR", filter, message: errorMessage(error) });
    }
  }
}

function unique(values) {
  return [...new Set(values.filter(Boolean))].join(",");
}

function errorMessage(error) {
  return String(error?.message ?? error).slice(0, 220);
}
