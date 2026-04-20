import { neon } from "@neondatabase/serverless";
import { drizzle } from "drizzle-orm/neon-http";
import * as schema from "./schema";

const dbUrl = process.env.DATABASE_URL;
export const isMockDB = !dbUrl || dbUrl.includes("localhost") || dbUrl.includes("placeholder");

if (isMockDB) {
  console.log("🟡 DATABASE_URL not found. Running in ZERO-CONFIG (In-Memory) mode.");
}

const sql = neon(dbUrl || "postgresql://placeholder:placeholder@localhost/placeholder");
export const db = drizzle(sql, { schema });
