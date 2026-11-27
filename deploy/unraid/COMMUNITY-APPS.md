# Publishing Audiotheca to Unraid Community Applications

Community Applications (CA) lists apps from a **public GitHub repository** that has an OSI license and a `ca_profile.xml` in its root, plus one XML template per app. Audiotheca itself is not open-source licensed, so the CA submission uses a small separate repository that holds only the template:

```
cephyrixzyth/unraid-templates
  README.md
  LICENSE            MIT, covers the template files only
  .gitignore
  icon.png           256x256, served raw from this repo
  ca_profile.xml     maintainer profile (required, non-empty <Profile>)
  templates/
    audiotheca.xml   the Docker template CA installs from
```

The ready-to-push contents live in [`ca-repo/`](ca-repo/). The template, profile and icon URLs already point at `https://raw.githubusercontent.com/cephyrixzyth/unraid-templates/main/...`; if you use another repo name, update `TemplateURL`, both `Icon` elements, and `ca_profile.xml`.

## One-time steps

1. **Make the image public.** CA users pull anonymously, and the GHCR package is private by default.
   Open https://github.com/users/cephyrixzyth/packages/container/package/audiotheca → **Package settings** → **Danger Zone → Change visibility → Public**.
   Check from any machine: `docker logout ghcr.io; docker pull ghcr.io/cephyrixzyth/audiotheca:latest`.
2. **Create the templates repo.** Create a new **public** repo `cephyrixzyth/unraid-templates` (https://github.com/new), then push the folder:
   ```bash
   cp -r deploy/unraid/ca-repo /tmp/unraid-templates && cd /tmp/unraid-templates
   git init -b main && git add . && git commit -m "Add Audiotheca Unraid template"
   git remote add origin https://github.com/cephyrixzyth/unraid-templates.git
   git push -u origin main
   ```
3. **Test the template on your Unraid server** before submitting:
   ```bash
   wget -O /boot/config/plugins/dockerMan/templates-user/my-Audiotheca.xml \
     https://raw.githubusercontent.com/cephyrixzyth/unraid-templates/main/templates/audiotheca.xml
   ```
   Then **Docker → Add Container → Template: Audiotheca**, set Library, API token and proxy secret, **Apply**, and open the WebUI.
4. **Submit.** Go to https://ca.unraid.net/submit/new, sign in with your Unraid account, enter `https://github.com/cephyrixzyth/unraid-templates`, run the scan, fix anything it flags, and submit.
5. **Optional: support thread.** CA does not require one, but most apps have a thread in https://forums.unraid.net/forum/47-docker-containers/. If you create one, put its URL in `<Support>` in the template and add `<Forum>` to `ca_profile.xml`.

## Keeping it current

- The template uses `ghcr.io/cephyrixzyth/audiotheca:latest`. `.github/workflows/docker-publish.yml` moves `latest` on every `v*` tag, so a release updates CA users through Unraid's normal "update ready" check. No template change is needed per release.
- Edit `deploy/unraid/ca-repo/` here first, then copy the change to the templates repo. CA re-reads the templates repo periodically.
- `my-audiotheca.xml` stays as the self-build template (local image `audiotheca/unraid:latest`).

Reference: https://ca.unraid.net/submit/help (repository layout, `ca_profile.xml`, XML field reference).
