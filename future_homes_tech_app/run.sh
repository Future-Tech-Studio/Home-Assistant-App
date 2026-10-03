#!/usr/bin/with-contenv bashio

set -euo pipefail

# Settings transfer: a local install exports its saved settings on each start;
# a new repository install imports them once. See docs/SETTINGS_TRANSFER.md.
if [[ "${FHT_BETA_APPLIED:-0}" != "1" ]]; then
    app_repository="$(bashio::addon.repository 2>/dev/null || true)"
    if [[ "${app_repository}" == "local" ]]; then
        if transfer_count="$(bashio::addon.options | future-homes-tech-transfer export)"; then
            if [[ "${transfer_count}" == "-1" ]]; then
                bashio::log.info "A repository install already has these settings; not exporting them again."
            else
                bashio::log.info "Exported ${transfer_count} saved settings items for a repository install."
            fi
        else
            bashio::log.warning "Unable to export saved settings for a repository install."
        fi
    else
        set +e
        transfer_options="$(future-homes-tech-transfer import)"
        transfer_status=$?
        set -e
        if [[ "${transfer_status}" == "0" ]]; then
            bashio::log.info "Imported saved settings from the local install."
            if [[ "${transfer_options}" != "{}" ]] \
                && bashio::api.supervisor POST /addons/self/options "{\"options\": ${transfer_options}}" >/dev/null; then
                bashio::log.info "Imported App configuration; restarting the App to apply it."
                bashio::addon.restart
                exit 0
            fi
            bashio::log.warning "App configuration was not imported; re-enter it under Configuration."
        elif [[ "${transfer_status}" != "3" ]]; then
            bashio::log.warning "Saved settings were not imported: ${transfer_options}"
        fi
    fi
fi

# Beta channel: when Beta mode is on and a newer Beta build was downloaded,
# copy it over this Stable build and continue from the Beta copy of this script.
if [[ -z "${FHT_STABLE_VERSION:-}" ]]; then
    export FHT_STABLE_VERSION
    FHT_STABLE_VERSION="$(bashio::addon.version)"
fi
export FHT_RUNNING_VERSION="${FHT_RUNNING_VERSION:-${FHT_STABLE_VERSION}}"
if [[ "${FHT_BETA_APPLIED:-0}" != "1" ]] && bashio::config.true 'beta_mode'; then
    set +e
    beta_version="$(future-homes-tech-beta apply "${FHT_STABLE_VERSION}")"
    beta_status=$?
    set -e
    if [[ "${beta_status}" == "0" ]]; then
        bashio::log.warning "Starting Beta build ${beta_version} over Stable ${FHT_STABLE_VERSION}."
        export FHT_BETA_APPLIED=1
        export FHT_RUNNING_VERSION="${beta_version}"
        # Source instead of exec: with-contenv clears the environment, which
        # would drop FHT_BETA_APPLIED and apply the Beta build again forever.
        # shellcheck source=/dev/null
        source /run.sh
        exit $?
    elif [[ "${beta_status}" == "2" ]]; then
        bashio::log.warning "Beta build did not start after repeated attempts; starting Stable ${FHT_STABLE_VERSION}. Install a newer Beta build to try again."
    elif [[ "${beta_status}" != "3" ]]; then
        bashio::log.warning "Beta build could not be applied; starting Stable ${FHT_STABLE_VERSION}."
    fi
fi

options="$(bashio::addon.options)"
if bashio::jq.exists "${options}" ".device_offline_webhook"; then
    bashio::log.info "Removing legacy Device Offline Webhook option..."
    bashio::addon.option "device_offline_webhook"
fi

bashio::log.info "Applying Future Homes Tech configuration..."

export PROTECT_API_KEY
PROTECT_API_KEY="$(bashio::config 'protect_api_key')"

export PROTECT_VERIFY_SSL
if bashio::config.true 'protect_verify_ssl'; then
    PROTECT_VERIFY_SSL=1
else
    PROTECT_VERIFY_SSL=0
    bashio::log.warning \
        "Protect TLS certificate verification is disabled. Configure a trusted certificate before enabling it."
fi

export PROTECT_CA_CERTIFICATE
PROTECT_CA_CERTIFICATE="$(bashio::config 'protect_ca_certificate')"

# Future Tech Portal: an optional token and URL. The App copies the token into
# secrets.yaml on start; it is never printed.
export FUTURE_TECH_TOKEN
FUTURE_TECH_TOKEN="$(bashio::config 'future_tech_token' 2>/dev/null || true)"
if [[ "${FUTURE_TECH_TOKEN}" == "null" ]]; then
    FUTURE_TECH_TOKEN=""
fi
export FUTURE_TECH_URL
FUTURE_TECH_URL="$(bashio::config 'future_tech_url' 2>/dev/null || true)"
if [[ "${FUTURE_TECH_URL}" == "null" ]]; then
    FUTURE_TECH_URL=""
fi

export ENTRY_DELAY_WEBHOOK_ID
ENTRY_DELAY_WEBHOOK_ID="$(bashio::config 'entry_delay_webhook_id')"

export ENTRY_DELAY_SECONDS
export DEVICE_ALARM_WEBHOOK
DEVICE_ALARM_WEBHOOK="$(bashio::config 'device_alarm_webhook')"
if [[ -z "${DEVICE_ALARM_WEBHOOK}" ]]; then
    # A blank option means this home's Protect DeviceAlarm address from the
    # site profile (/data/site_profile.json over the shipped defaults).
    DEVICE_ALARM_WEBHOOK="$(future-homes-tech-site protect-webhook device_alarm 2>/dev/null || true)"
fi
ENTRY_DELAY_SECONDS="$(bashio::config 'entry_delay_seconds')"

export BEDROOM_ARMED_AWAY_WEBHOOK
BEDROOM_ARMED_AWAY_WEBHOOK="$(bashio::config 'armed_away_interior_door_webhook')"
if [[ -z "${BEDROOM_ARMED_AWAY_WEBHOOK}" ]] && bashio::jq.exists "${options}" ".bedroom_armed_away_webhook"; then
    BEDROOM_ARMED_AWAY_WEBHOOK="$(bashio::jq "${options}" ".bedroom_armed_away_webhook")"
fi

export BEDROOM_ARMED_STAY_KIDS_WEBHOOK
BEDROOM_ARMED_STAY_KIDS_WEBHOOK="$(bashio::config 'armed_stay_kids_interior_door_webhook')"
if [[ -z "${BEDROOM_ARMED_STAY_KIDS_WEBHOOK}" ]] && bashio::jq.exists "${options}" ".bedroom_armed_stay_kids_webhook"; then
    BEDROOM_ARMED_STAY_KIDS_WEBHOOK="$(bashio::jq "${options}" ".bedroom_armed_stay_kids_webhook")"
fi

export FHT_GITHUB_TOKEN
FHT_GITHUB_TOKEN="$(bashio::config 'github_token' 2>/dev/null || true)"
if [[ "${FHT_GITHUB_TOKEN}" == "null" ]]; then
    FHT_GITHUB_TOKEN=""
fi

export FHT_BETA_MODE
if bashio::config.true 'beta_mode'; then
    FHT_BETA_MODE=1
    bashio::log.warning "Beta mode is enabled. In-development features are active on this installation."
else
    FHT_BETA_MODE=0
fi

export FHT_CLIMATE_PACKAGE_BACKUP_PATH
FHT_CLIMATE_PACKAGE_BACKUP_PATH="/data/future_homes_tech_climate_base.yaml"

if ! future-homes-tech-configure; then
    bashio::log.fatal "Unable to configure Home Assistant."
    exit 1
fi

bashio::log.info "Configuration complete."
bashio::log.info "Restart Home Assistant or run Quick reload to apply changes."

if climate_migration="$(future-homes-tech-migrate-climate)"; then
    if [[ "${climate_migration}" == "migrated" || "${climate_migration}" == "updated" || "${climate_migration}" == "restored" ]]; then
        bashio::log.info "Migrated legacy Climate configuration into the App-managed package."
        bashio::log.info "Restart Home Assistant once to load the managed Climate package."
    fi
else
    bashio::log.warning "Climate migration was not completed; legacy Climate configuration remains unchanged."
fi

export LIGHT_GROUPS_CHANGED=0
if generation_result="$(future-homes-tech-generate-light-groups)"; then
    generation_state="${generation_result%% *}"
    generation_count="${generation_result##* }"
    if [[ "${generation_state}" == "changed" ]]; then
        export LIGHT_GROUPS_CHANGED=1
    fi
    bashio::log.info \
        "Generated ${generation_count} Future Homes Tech light groups."
else
    bashio::log.warning \
        "Unable to generate Future Homes Tech light groups."
fi

bashio::log.info "Starting Future Homes Tech App interface..."
exec future-homes-tech-server
