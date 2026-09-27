# Future Homes Tech App Roadmap

The App is organized as a deployment manager. Each release will add managed
content while preserving backups and making repeat runs idempotent.

## Version 0.1

- Protect API key
- Device offline webhook
- `rest_command.unifi_device_offline`

## Planned Modules

### Dashboards

- Deploy Future Homes Tech Lovelace YAML dashboards.
- Register dashboard navigation in `configuration.yaml`.
- Preserve homeowner-specific dashboard settings.

### Automations

- Deploy managed automation files into the Future Homes Tech automation
  directory.
- Keep managed automations separate from homeowner-created automations.

### Scenes

- Deploy managed scene definitions.
- Support room and whole-home scene collections.

### Blueprints

- Install Future Homes Tech automation and script blueprints.
- Track blueprint versions during App updates.

### Light Groups

- Generate and deploy managed light groups. Completed in 0.2.20.
- Preserve site-specific entity assignments.

### Service Connections

- Add additional Future Homes Tech and third-party service endpoints.
- Keep credentials in Home Assistant secrets or App configuration.

## Design Rules

- Create a one-time backup before changing an existing user file.
- Keep all generated output deterministic and safe to run repeatedly.
- Never log API keys or other credentials.
- Prefer dedicated managed files over rewriting user-owned YAML.
- Validate configuration before asking Home Assistant to reload it.
