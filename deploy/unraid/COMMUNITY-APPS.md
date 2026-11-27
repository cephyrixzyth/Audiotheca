# Audiotheca in Unraid Community Applications

The Community Applications (CA) template lives in the shared templates repo, next to Oneirodex:

- Repo: https://github.com/cephyrixzyth/unraid-templates (already listed in CA as "Cephyrix Zyth's Repository")
- Template: `audiotheca/audiotheca.xml`
- Icon: `audiotheca/icon.png`
- Raw template URL: https://raw.githubusercontent.com/cephyrixzyth/unraid-templates/main/audiotheca/audiotheca.xml

Because that repo is already in CA, a template merged to its `main` branch is picked up on CA's next feed refresh. No new submission is needed.

## Requirements

- **The image must be public.** CA users pull anonymously. Package settings: https://github.com/users/cephyrixzyth/packages/container/package/audiotheca → Change visibility → Public.
  Check: `docker logout ghcr.io; docker pull ghcr.io/cephyrixzyth/audiotheca:latest`.
- The template uses `ghcr.io/cephyrixzyth/audiotheca:latest`. `.github/workflows/docker-publish.yml` moves `latest` on every `v*` tag, so releases reach CA users through Unraid's normal update check with no template change.

## Changing the template

Edit `audiotheca/audiotheca.xml` in the templates repo through a PR. `my-audiotheca.xml` in this folder stays as the self-build template (local image `audiotheca/unraid:latest`).

Reference: https://ca.unraid.net/submit/help
