# Pushing and pulling with metaseed-hub

Metaseed runs on one machine for one person; [metaseed-hub](https://github.com/sorenwacker/metaseed-hub) is the shared, deployed service a group works in. Both hold profiles (specifications) and datasets. This guide covers moving them between the two from the metaseed UI: a dataset or a profile built locally goes to the hub with *Push*, and one on the hub comes down with *Pull*. Nothing is merged automatically and nothing is overwritten without being chosen.

## One-time setup

The hub actions are hidden until the adapter is enabled and pointed at a hub.

1. On the hub, create a personal access token under **Access tokens** on your profile. The token is shown once; it acts as you, so everything pushed lands in your account and your tenant.
2. In metaseed, open **Settings → Plugins**, enable **Metaseed Hub**, and set:
   - **URL** — the hub, e.g. `https://hub.example.org` (required).
   - **Access token** — the token from step 1 (`msh_...`, required).
3. Press **Check connection**. A working connection shows which hub account and tenant the token acts as; a failure names the cause (unreachable host, refused token).

The token is stored in `settings.json` in your data directory, like the SEEK API key.

## Datasets

### Push

On the datasets overview every dataset has **Push to hub**. Pushing creates a hub dataset of the same name, profile and version in your tenant, holding the same entities. If the hub already has a dataset of that name:

- identical content: nothing is sent, and the page says so;
- different content: the page shows what differs (entity counts per type, the entities that would be added, changed or removed) and offers **Replace on hub**. Nothing changes until that is pressed.

A push needs the dataset's profile to exist on the hub: a built-in profile always does, a user-local profile has to be pushed first (below). The hub refuses a dataset it cannot load under its profile (HTTP 422), and the page shows the hub's message.

### Pull

**Pull from hub** on the datasets overview lists your hub datasets (name, profile, version, entity count, last change). Pulling one saves it locally under the same name. If a local dataset of that name exists:

- identical content: nothing is written;
- different content: the pulled copy is saved as `<name>-hub` beside the local one, and the page says so. Merging is a manual step on your side.

### Provenance

Each pushed or pulled dataset records where it came from and when in its own metadata: the hub URL, the hub account, the direction and the time. The datasets overview shows this on the dataset's card.

## Profiles

### Push

On the profile explorer, **Push / pull profiles** (in the sidebar) lists your user-local profiles (those under your data directory, not the built-in ones), each with **Push as draft** and **Publish**. A push lands in *your* account as a **private draft** — only you see it, and pushing a revised profile updates it. **Publish** (asked for explicitly, with a confirmation) makes it a **published specification** visible to every user of the hub, so their datasets can be built against it; the hub applies its version-bump gate, so a name and version already published are not replaced — bump the version locally and publish again. A profile you published shows **Unpublish**, which withdraws it to a private draft (the hub refuses while datasets are built on it). The push reports the content hash the hub stored, which matches the local profile's.

A profile the hub's own metaseed version cannot read is refused with HTTP 422 naming the field it did not expect — a template-bound profile (one carrying `seek_attribute_type` or `seek_controlled_vocab`) pushed to a hub running an older metaseed does exactly this. The hub has to be running a metaseed release that knows those fields; the message names which field, so the cause is not a guess.

### Pull

The same panel lists what the hub holds — your drafts and every published specification, each marked — with **Pull** on those not here. Pulling one saves it under your data directory as `<name>/<version>/profile.yaml`. A profile at that name and version already present locally is not replaced: the page shows whether the two are identical or differ, and a differing one has to be removed or renamed locally before it can be pulled.

## What the hub exposes for this

The hub's REST API (`/api`, bearer token) carries the exchange:

| Call | Used for |
|------|----------|
| `GET /api/me` | Connection check: the account and tenant the token acts as |
| `GET /api/datasets`, `GET /api/datasets/{id}` | Pull list and pull |
| `POST /api/datasets`, `PATCH /api/datasets/{id}` | Push (create, replace) |
| `GET /api/specs`, `GET /api/specs/{name}/{version}` | Pull list and pull |
| `POST /api/specs` | Push as a draft; `publish: true` publishes (refused when the version exists) |
| `POST /api/specs/{id}/unpublish` | Withdraw a published profile to a draft |

Everything else — comparison, the `-hub` suffix, provenance — happens in metaseed. Automatic two-way synchronisation (detecting changes on both sides and proposing the direction) is not part of this; push and pull are explicit.
