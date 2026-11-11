# GeoIP attribution

IP-to-country resolution uses **DB-IP Lite** (`dbip-country-lite-<YYYY-MM>.csv.gz`),
downloaded at image build time (see `Dockerfile`, `ARG GEOIP_DB_VERSION`).

- Data: IP geolocation by [DB-IP](https://db-ip.com)
- License: [Creative Commons Attribution 4.0 International (CC-BY 4.0)](https://creativecommons.org/licenses/by/4.0/)
- Source: https://db-ip.com/db/download/ip-to-country-lite

Attribution required by CC-BY 4.0 is satisfied by this notice shipped inside
the image at `/app/data/geoip/NOTICE.md` next to the database file.
