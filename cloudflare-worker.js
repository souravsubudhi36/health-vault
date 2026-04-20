/**
 * Cloudflare Worker — Health Relay
 *
 * Receives POST requests from iOS Shortcuts, validates the bearer token,
 * base64-encodes the payload (to survive GitHub API string handling),
 * and fires a repository_dispatch event to GitHub Actions.
 *
 * Environment variables to set in the Cloudflare dashboard:
 *   SECRET_TOKEN  — a strong password you choose (used in iOS Shortcuts too)
 *   GITHUB_TOKEN  — GitHub Fine-grained PAT with Contents: Read & Write on your repo
 *   GITHUB_REPO   — e.g.  "souravsubudhi/health-vault"
 */

export default {
  async fetch(request, env) {
    // Only accept POST
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    // Validate bearer token
    const auth = request.headers.get("Authorization") || "";
    if (auth !== `Bearer ${env.SECRET_TOKEN}`) {
      return new Response("Unauthorized", { status: 401 });
    }

    // Parse body
    let body;
    try {
      body = await request.json();
    } catch {
      return new Response("Invalid JSON body", { status: 400 });
    }

    const { data_type, content } = body;
    if (!data_type || !content) {
      return new Response("Missing data_type or content", { status: 400 });
    }

    // Base64-encode to preserve newlines through the GitHub API
    const encoded = btoa(unescape(encodeURIComponent(content)));

    // Build a unique filename: timestamp + random suffix + data type
    const timestamp = Date.now();
    const runId = Math.random().toString(36).substring(2, 9);
    const filename = `${timestamp}_${runId}_${data_type}.txt`;

    // Trigger GitHub Actions via repository_dispatch
    const ghResponse = await fetch(
      `https://api.github.com/repos/${env.GITHUB_REPO}/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github.v3+json",
          "Content-Type": "application/json",
          "User-Agent": "health-relay-cloudflare-worker",
        },
        body: JSON.stringify({
          event_type: "health-sync",
          client_payload: {
            filename,
            data_type,
            data: encoded,
          },
        }),
      }
    );

    if (!ghResponse.ok) {
      const err = await ghResponse.text();
      console.error("GitHub dispatch failed:", err);
      return new Response(`GitHub error: ${ghResponse.status}`, { status: 502 });
    }

    return new Response(
      JSON.stringify({ ok: true, filename }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  },
};
