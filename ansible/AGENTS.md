# Installing the calls stack on a server — instructions for an agent

You install this repository's stack (trip2g, fleet, Hermes in Telegram,
Caddy) on a bare Ubuntu 24.04 server with `ansible/site.yml`, check it works,
and hand the result to the person who asked. Run every command from the
`ansible/` directory of this repository unless a step says otherwise.

Never print the Telegram bot token, the contents of `/opt/call-dashboard/.env`,
or a sign-in link into a chat or a log the person shares. The files that hold
them are mode 0600 on purpose.

## 1. Inputs

Get every value before you start. Ask the person for what you cannot find.

| Input | Variable | How to get it |
|---|---|---|
| Server address and root ssh access | `inventory.ini` | From the person: an IP, the user (root, or a user with passwordless sudo) and the ssh key. Check with `ssh root@<ip> true`. |
| Domain | `calls_domain` | A name whose DNS A record points at the server's IP. Check with `dig +short <domain>`: it must print exactly that IP. With no domain, `<ip with dashes>.sslip.io` (for 1.2.3.4: `1-2-3-4.sslip.io`) resolves to the IP by itself. `calls_domain` is the same string as the host name in `inventory.ini`. |
| Owner email | `calls_owner_email` | From the person: a real address. It names the owner account and is the contact Caddy gives the certificate authority (Let's Encrypt, or ZeroSSL when Caddy falls back to it). The playbook refuses `example.com`, `example.org`, `example.net` and other placeholder domains before it touches the server. |
| Telegram bot token | `telegram_bot_token` | The person creates a bot with @BotFather (`/newbot`) and gives you the token. One bot per stack: a token already polled elsewhere makes the bot silent here. |
| Telegram owner id | `telegram_owner_id` | The person's numeric Telegram id, for example from @userinfobot. Only this id can talk to the bot. |
| Models (optional) | `hermes_model`, `role_model` | Default `gpt-6-sol`. Any Codex model the person's ChatGPT plan offers. |
| Email relay (optional) | `smtp_host`, `smtp_port`, `smtp_user`, `smtp_pass`, `mail_from` | Only if the person wants email sign-in codes. Resend: `smtp.resend.com`, `587`, `resend`, the API key, a sender on a domain verified in Resend. Other providers: https://trip2g.com/en/user/smtp |

What you ask the person, and where it goes in `vars.yml`:

| Ask the person for | `vars.yml` name |
|---|---|
| the domain | `calls_domain` |
| their email | `calls_owner_email` |
| the bot token from @BotFather | `telegram_bot_token` |
| their numeric Telegram id | `telegram_owner_id` |

Requirements on your side: Ansible 2.15.1 or newer (`ansible --version`),
`rsync`, `ssh`. Ports 22, 80 and 443 (tcp and udp) must be open in any cloud
firewall in front of the server.

## 2. Install the roles

```sh
ansible-galaxy install -r requirements.yml
```

Expected: `geerlingguy.docker (8.0.0)` installed or already installed, and the
three collections installed or already present. Nothing failed.

## 3. Write the inventory and the variables

```sh
cp inventory.example.ini inventory.ini
cp vars.example.yml vars.yml
chmod 600 vars.yml inventory.ini
```

`inventory.ini`, one host in group `calls`. The host name is the domain,
exactly the string you put in `calls_domain`; `ansible_host` is the IP:

```ini
[calls]
calls.example.com ansible_host=203.0.113.10 ansible_user=root ansible_ssh_private_key_file=~/.ssh/id_ed25519
```

`ansible_ssh_private_key_file` is the key the person gave you; drop it when
your default key already gets in. `vars.yml`: the inputs from section 1. Both
files are gitignored; never commit them.

When the key and the server's host key should stay out of your own ssh setup
(a key handed to you for this job, a server you have never reached), keep both
in a working directory and point ssh at them in the same host line:

```ini
calls.example.com ansible_host=203.0.113.10 ansible_user=root ansible_ssh_private_key_file=/path/to/work/id_ed25519 ansible_ssh_common_args="-o UserKnownHostsFile=/path/to/work/known_hosts -o IdentitiesOnly=yes"
```

and record the server's host key there once the person confirms the server is
the one they just created:

```sh
ssh-keyscan -t ed25519 203.0.113.10 > /path/to/work/known_hosts
```

Check:

```sh
ansible calls -m ping
```

Expected: `"ping": "pong"`. On `Host key verification failed`, ssh does not
know the server's host key yet: record it in the working `known_hosts` as
above. Appending it to your own `~/.ssh/known_hosts` instead changes the
operator's ssh configuration; do that only if the person says so. A server
that was rebuilt has a new host key, so an old entry fails the same way.

## 4. Run the playbook

```sh
ansible-playbook site.yml
```

It takes up to about 15 minutes on a fresh 2-vCPU server, and some tasks are
silent for minutes. Run it with a long command timeout (20 minutes or more)
or in the background with its output in a file, and wait for the recap
rather than reading a quiet stretch as a hang. Expected: the recap shows
`failed=0`, and the last task, `What is left for you`, prints the run summary.

What it does: unattended upgrades on; ufw allows only 22, 80, 443/tcp and
443/udp; Docker from the `geerlingguy.docker` role; the stack in
`/opt/call-dashboard` with generated secrets in `.env` (0600, kept on later
runs); API keys for the stack and for the person's agent; the onboarding
vault; the checks below.

## 5. Check

The playbook already checked these and stops if one fails:

- https answers with a valid certificate (`checks.https_status` is 200 or 401);
- fleet registered one webhook per role in `vault/roles/` (`checks.fleet_webhooks` is 3).

Read the summary:

```sh
ssh root@<ip> cat /opt/call-dashboard/run-summary.json
```

```json
{
  "url": "https://calls.example.com",
  "owner_email": "<calls_owner_email>",
  "sign_in": {
    "on_server": "ssh root@calls.example.com 'cd /opt/call-dashboard && docker compose exec -T trip2g /trip2g login-link'",
    "from_telegram": "Write to @your_bot: «дай ссылку для входа». The bot answers with a «Войти» button.",
    "link_lifetime_minutes": 5
  },
  "telegram_bot": "@your_bot",
  "telegram_owner_id": "123456789",
  "codex_logged_in": false,
  "codex_login": "ssh -t root@calls.example.com 'cd /opt/call-dashboard && docker compose run --rm --no-deps --user 10000:10000 --entrypoint hermes hermes auth add openai-codex'",
  "files": { "run_summary": "...", "agent_access": "...", "onboarding_vault": "...", "secrets": "..." },
  "checks": { "https_status": 401, "fleet_webhooks": 3 }
}
```

Then check the containers:

```sh
ssh root@<ip> 'cd /opt/call-dashboard && docker compose ps -a'
```

Expected: `trip2g` running and healthy; `caddy`, `fleet`, `codex-bridge` and
`hermes` running; `seed`, `vault-seed` and `notify-job` exited with code 0.

And that Hermes sees its tools:

```sh
ssh root@<ip> 'cd /opt/call-dashboard && docker compose exec -T -u 10000:10000 hermes hermes mcp test secondbrain'
```

Expected: `Connected` and `Tools discovered: 8`, `signin_link` among them.

A second `ansible-playbook site.yml` must end with `failed=0` and
`changed=0`. Compose does start the one-shot `seed`, `vault-seed` and
`notify-job` again: they find their work done and exit (`vault-seed` runs one
sync), and the playbook does not count that as a change.

## 6. Known failures

| Symptom | Cause | What to do |
|---|---|---|
| `The owner email is a real address` fails | `calls_owner_email` is a placeholder or not an address | Ask the person for their real email, fix `vars.yml`, run the playbook again. Nothing on the server changed yet. |
| `https answers with a valid certificate` fails after 30 retries | The A record does not point at the server, or 80/443 are closed in a cloud firewall | `dig +short <domain>` must print the server's IP; open 80 and 443; then `ssh root@<ip> 'cd /opt/call-dashboard && docker compose logs caddy'` and run the playbook again. |
| Caddy logs `rateLimited` | Let's Encrypt allows 5 certificates per exact domain per week | Wait for the window the log names, or use another domain. Do not loop the playbook. Caddy may fall back to ZeroSSL on its own, which takes a few minutes of retries. |
| `The Telegram bot's name` fails with 401 | Wrong `telegram_bot_token` | Ask for the token again, fix `vars.yml`, run the playbook again. |
| `trip2g is up` times out | trip2g 0.12.0 sometimes crashes on its very first boot | Run the playbook again; `restart: unless-stopped` has usually brought it back. If not: `docker compose logs trip2g`. |
| `The whole stack is up` fails because `vault-seed` exited 1 | Its sync could not reach trip2g | `docker compose logs vault-seed`; run the playbook again, which runs it again. |
| `fleet registered a webhook for every role` fails | fleet could not reach trip2g on loopback | `docker compose logs fleet`, then `docker compose up -d --force-recreate trip2g fleet` and run the playbook again. |
| Hermes logs `Conflict: terminated by other getUpdates request` | Another process polls the same bot token | The person stops the other process, or makes a new bot. |
| The bot does not answer at all | Codex is not logged in yet (`codex_logged_in: false`) | Expected. The Codex login is a hand-off step: only the person can do it, in their browser with their ChatGPT account, and you cannot do it for them. Hand it over as item 3 of section 7. |
| A sign-in link says it is invalid | It was used once already, or 5 minutes passed | Mint a new one; links are one-time. |

Any other failure: report the failing task's name and its error output to the
person as they are. Do not edit the role to get past a failure.

## 7. Hand back to the person

Tell the person, in their language:

1. **The address:** `url` from the summary.
2. **How to sign in.** There is no password. Either:
   - you run `sign_in.on_server` from the summary when they are ready, and
     give them the link it prints; it works once, within 5 minutes; or
   - once Codex is logged in, they write to the bot «дай ссылку для входа»
     and press the «Войти» button it sends.
   Email codes work only with the optional relay; Google or GitHub sign-in is
   set up in the admin panel: https://trip2g.com/en/user/oauth
3. **The Codex login, which only they can do.** They run `codex_login` from
   the summary in their own terminal (it needs `-t`), open the URL it prints,
   sign in with their ChatGPT account and enter the code. Until then the bot
   does not answer and calls are not reviewed. Never copy a Codex `auth.json`
   to the server.
4. **The Telegram bot:** `telegram_bot` from the summary. Only their id
   (`telegram_owner_id`) can talk to it. New calls are announced there.
5. **Their files**, which they fetch themselves:
   `scp root@<ip>:/opt/call-dashboard/onboarding.zip .` (their vault, with the
   sync script and its own key) and
   `scp root@<ip>:/opt/call-dashboard/agent-access.md .` (an API key and the
   MCP and sync commands for their own AI agent).

Do not paste the contents of `agent-access.md`, `.env` or a sign-in link into
a shared channel.
