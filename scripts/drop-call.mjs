import { readFileSync } from "node:fs";
import { randomBytes } from "node:crypto";

const source = process.argv[2];
const id = randomBytes(3).toString("hex");
const date = new Date().toISOString().slice(0, 10);
const path = `transcripts/${date}-${id}.md`;
const query = "mutation($i: PushNotesInput!) { pushNotes(input: $i) { __typename ... on ErrorPayload { message } } }";
const variables = { i: { updates: [{ path, content: readFileSync(source, "utf8") }] } };

const response = await fetch("http://trip2g:8380/graphql", {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-API-Key": process.env.VAULT_API_KEY },
  body: JSON.stringify({ query, variables }),
});
const answer = await response.json();
if (answer.data?.pushNotes?.__typename !== "PushNotesPayload") {
  console.error(JSON.stringify(answer));
  process.exit(1);
}
console.log(`dropped ${path}: call id ${id}`);
