# Pinned so the same App version always builds on the same base.
FROM ghcr.io/home-assistant/base:3.24-2026.08.0

ARG BUILD_VERSION
ARG BUILD_ARCH

LABEL \
    io.hass.name="Future Homes Tech App" \
    io.hass.description="Deploy and manage Future Homes Tech Home Assistant content" \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="app" \
    io.hass.arch="${BUILD_ARCH}"

RUN apk add --no-cache python3 tzdata

COPY configure.py /usr/local/bin/future-homes-tech-configure
COPY generate_light_groups.py /usr/local/bin/future-homes-tech-generate-light-groups
COPY migrate_climate.py /usr/local/bin/future-homes-tech-migrate-climate
COPY server.py /usr/local/bin/future-homes-tech-server
COPY fht_access.py /usr/local/bin/fht_access.py
COPY fht_maintenance.py /usr/local/bin/fht_maintenance.py
COPY fht_catalog.py /usr/local/bin/fht_catalog.py
COPY fht_site.py /usr/local/bin/future-homes-tech-site
COPY fht_site.py /usr/local/bin/fht_site.py
COPY site_profile.json /usr/local/bin/site_profile.json
COPY fht_history.py /usr/local/bin/fht_history.py
COPY fht_beta.py /usr/local/bin/future-homes-tech-beta
COPY fht_beta.py /usr/local/bin/fht_beta.py
COPY fht_transfer.py /usr/local/bin/future-homes-tech-transfer
COPY run.sh /run.sh
COPY web /opt/future-homes-tech/web

RUN chmod a+x \
    /usr/local/bin/future-homes-tech-configure \
    /usr/local/bin/future-homes-tech-generate-light-groups \
    /usr/local/bin/future-homes-tech-migrate-climate \
    /usr/local/bin/future-homes-tech-server \
    /usr/local/bin/future-homes-tech-beta \
    /usr/local/bin/future-homes-tech-site \
    /usr/local/bin/future-homes-tech-transfer \
    /run.sh

CMD ["/run.sh"]
