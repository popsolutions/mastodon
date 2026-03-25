Mastodon - Decentralized Social Network
========================================

`Mastodon`_ is a free, open-source, decentralized social network server
based on ActivityPub. Users can create their own server instances and
participate in the Fediverse.

This appliance includes all the standard features in `TurnKey Core`_,
and on top of that:

- Mastodon v4.5.8 installed from upstream source.
- Ruby 3.4.7 via rbenv with jemalloc (TurnKey common ruby vertical).
- Node.js 20 LTS (TurnKey common nodejs vertical).
- PostgreSQL database backend.
- Redis for caching and Sidekiq background jobs.
- Nginx reverse proxy with WebSocket support for streaming API.
- Systemd services for web, sidekiq and streaming.
- Certbot for Let's Encrypt SSL certificates.
- Firstboot configuration: domain, admin email, admin password.
- ``mastodon-upgrade`` helper script for safe in-place upgrades.
- ``tkl-upgrade-ruby`` for Ruby version management.
- IPv6-first by default.
- Postfix MTA (localhost) for outgoing notifications.

Credentials *(set at first boot)*:

- Webmin, SSH: username **root**
- Mastodon admin: set at firstboot
- PostgreSQL: username **postgres** (local peer auth)

.. _Mastodon: https://joinmastodon.org/
.. _TurnKey Core: https://www.turnkeylinux.org/core
