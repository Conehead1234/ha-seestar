# Upstream maintenance

This checkout carries local Home Assistant packaging, persistent interoperability
key support, an exact driver pin, and default-on log redaction. Updates therefore
need to preserve local commits while reviewing two independent upstreams.

## Sources and ownership

| Component | Upstream | How it is updated |
|---|---|---|
| Home Assistant add-on and MQTT bridge | `https://github.com/jaxzin/ha-seestar` | Merge reviewed `main` changes into the local branch. |
| Bundled driver | `https://github.com/smart-underworld/seestar_alp` | Change the immutable `SEESTAR_ALP_REF` in `seestar/Dockerfile` only after review and testing. Never track `main` automatically. |
| Lovelace card | `https://github.com/jaxzin/seestar-lovelace-card` | Let HACS update it. Keep its `/hacsfiles/...` module in Home Assistant's YAML resource list. |

The add-on and driver are intentionally separate update streams. A new add-on
commit does not imply that the driver pin should move, and a newer driver `main`
commit is not necessarily a released or compatible version.

The last reviewed driver release baseline is `v3.2.2`; the current immutable pin
contains a later authentication fix. A newly published tag or a change to that
baseline should trigger review, not an automatic pin change.

## Routine check

From the repository root on Windows:

```powershell
pwsh -File tools/check-upstreams.ps1
```

Windows PowerShell also works:

```powershell
powershell -ExecutionPolicy Bypass -File tools/check-upstreams.ps1
```

The script is read-only with respect to the working tree. It fetches the add-on
upstream ref, compares the current branch with upstream `main`, reads the pinned
driver SHA from `seestar/Dockerfile`, and compares it with the driver repository's
HEAD and latest semantic-version tag. Use `-NoFetch` for an offline/local-only
report or `-Json` for automation.

Run it monthly, before rebuilding the local add-on, after a telescope firmware
update, and whenever HACS reports a Seestar card update.

## Personal fork and remote layout

As of 2026-10-10 the local branch is backed up in the personal fork and this
checkout uses the conventional remote layout:

- `origin`: `https://github.com/Conehead1234/ha-seestar.git`
- `upstream`: `https://github.com/jaxzin/ha-seestar.git`

When repairing an older checkout that still has the public repository as
`origin`, configure the same layout with:

```powershell
git remote rename origin upstream
git remote add origin https://github.com/Conehead1234/ha-seestar.git
git fetch --prune upstream
git push -u origin codex/interop-pem-local
```

`origin` is Matt's recoverable copy and `upstream` is the public project. Do not
force-push the local deployment branch unless its history was deliberately
rewritten and the consequences have been reviewed.

## Updating the add-on/bridge upstream

1. Run the checker and make sure unrelated work is committed or stashed.
2. Work on a temporary update branch so the known-good local build remains easy
   to restore:

   ```powershell
   git switch codex/interop-pem-local
   git switch -c maintenance/upstream-YYYYMMDD
   git fetch --prune upstream main
   git merge --no-ff upstream/main
   ```

   Until the fork/remotes are configured, substitute `origin/main` for
   `upstream/main`.
3. Resolve conflicts without dropping the local PEM mount/validation, exact
   driver pin, local add-on identity, LF enforcement, or log-redaction hook.
4. Review changes to `seestar/config.yaml`, `seestar/Dockerfile`, s6 services,
   MQTT entity IDs, control payloads, and card-facing entity names.
5. Run the bridge tests and syntax checks documented in `CONTRIBUTING.md`.
6. Increment the local add-on version, stage the source in
   `/addons/seestar-pem`, rebuild, and start it.
7. Verify authentication, `S30pro Connected`, fresh MQTT states, redaction,
   camera behaviour, and both safety switches defaulting off. Exercise movement
   and power controls only as a deliberate final test.
8. Merge the tested maintenance branch into `codex/interop-pem-local`, then push
   it to the personal fork.

## Updating the bundled driver pin

Do not replace `SEESTAR_ALP_REF` just because driver `main` moved. Prefer a
released tag; otherwise choose a reviewed immutable commit. Before changing it:

1. Compare the current pin with the candidate on GitHub and confirm the candidate
   descends from the current authentication-fix commit.
2. Review authentication/COMMAND-channel changes, `config.toml` schema changes,
   logging of device responses, API endpoint/payload changes, dependencies, and
   licence files.
3. Change only the immutable SHA in `seestar/Dockerfile`; update the known-caveat
   note in `seestar/DOCS.md`, `CHANGELOG.md`, and third-party notices when needed.
4. Rebuild from scratch and repeat the live checks above. Confirm that sensitive
   data remains redacted at `INFO` before retaining any diagnostic log.

Rollback is deterministic: restore the previous SHA and local version, rebuild,
and restart the local add-on. Never include the interoperability PEM in a commit,
image, diagnostic archive, or support bundle.

## Lovelace card updates

The card remains HACS-owned. After a card update, confirm this YAML-managed
resource still exists in the Home Assistant configuration:

```yaml
- {url: /hacsfiles/seestar-lovelace-card/seestar-card.js, type: module}
```

Reload Lovelace resources (or restart Core when other configuration also changed)
and hard-refresh browsers/mobile app caches. The local scope prefix remains
`s30pro` unless the configured scope name is intentionally changed.
