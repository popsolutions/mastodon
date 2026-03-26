#!/usr/bin/env python3
"""TurnKey Mastodon - First Boot Configuration (inithook)

Collects configuration from the user at first boot and provisions the
Mastodon instance completely, based on the official documentation:
https://docs.joinmastodon.org/admin/config/

User inputs (via TKL dialog):
  - FQDN (LOCAL_DOMAIN)
  - Admin email
  - Admin password          (generate or manual via dialog_wrapper)
  - PostgreSQL username      (default: mastodon)
  - PostgreSQL password      (generate or manual via dialog_wrapper)

Auto-generated (no user input needed):
  - SECRET_KEY_BASE                             (bundle exec rails secret)
  - OTP_SECRET                                  (bundle exec rails secret)
  - VAPID_PRIVATE_KEY + VAPID_PUBLIC_KEY        (rake mastodon:webpush:generate_vapid_key)
  - ACTIVE_RECORD_ENCRYPTION_DETERMINISTIC_KEY  (bin/rails db:encryption:init)
  - ACTIVE_RECORD_ENCRYPTION_KEY_DERIVATION_SALT
  - ACTIVE_RECORD_ENCRYPTION_PRIMARY_KEY

SMTP is configured separately via TKL confconsole (postfix relay).
"""

import os
import sys
import subprocess

INITHOOKS_PATH = "/usr/lib/inithooks"
sys.path.insert(0, os.path.join(INITHOOKS_PATH, "bin"))

from libinithooks.dialog_wrapper import Dialog

MASTODON_USER = "mastodon"
MASTODON_HOME = "/home/mastodon"
MASTODON_LIVE = os.path.join(MASTODON_HOME, "live")
ENV_FILE = os.path.join(MASTODON_LIVE, ".env.production")

RBENV_BIN = os.path.join(MASTODON_HOME, ".rbenv/bin")
RBENV_SHIMS = os.path.join(MASTODON_HOME, ".rbenv/shims")


# -- Shell helpers -------------------------------------------------------

def run_as_mastodon(cmd, env_extra=None):
    """Run a shell command as the mastodon user with rbenv loaded."""
    parts = [
        'export PATH="{}:{}:$PATH"'.format(RBENV_BIN, RBENV_SHIMS),
        'eval "$(rbenv init -)"',
        'cd {}'.format(MASTODON_LIVE),
    ]
    if env_extra:
        for k, v in env_extra.items():
            parts.append('export {}="{}"'.format(k, v))
    parts.append(cmd)
    shell_cmd = " ; ".join(parts)
    full_cmd = ["su", "-", MASTODON_USER, "-c", shell_cmd]
    return subprocess.run(full_cmd, capture_output=True, text=True)


def run_cmd(cmd, check=False):
    """Run a system command."""
    return subprocess.run(cmd, shell=True, check=check,
                          capture_output=True, text=True)


def ensure_services_running():
    """Ensure PostgreSQL and Redis are running."""
    for svc in ["postgresql", "redis-server"]:
        run_cmd("systemctl start {}".format(svc))


# -- Secret generation (per official Mastodon docs) ----------------------

def generate_rails_secret():
    """Generate a secret using 'bundle exec rails secret'."""
    result = run_as_mastodon(
        "RAILS_ENV=production bundle exec rails secret"
    )
    secret = result.stdout.strip()
    if not secret or result.returncode != 0:
        raise RuntimeError("rails secret failed: {}".format(result.stderr))
    return secret


def generate_vapid_keys():
    """Generate VAPID keys for Web Push notifications.

    Official command: bundle exec rake mastodon:webpush:generate_vapid_key
    Returns dict with VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY.
    """
    result = run_as_mastodon(
        "RAILS_ENV=production bundle exec rake mastodon:webpush:generate_vapid_key"
    )
    if result.returncode != 0:
        raise RuntimeError("VAPID generation failed: {}".format(result.stderr))
    keys = {}
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if "=" in line and line.startswith("VAPID_"):
            key, val = line.split("=", 1)
            keys[key.strip()] = val.strip()
    if "VAPID_PRIVATE_KEY" not in keys or "VAPID_PUBLIC_KEY" not in keys:
        raise RuntimeError("Unexpected VAPID output: {}".format(result.stdout))
    return keys


def generate_encryption_keys():
    """Generate Active Record encryption keys via Ruby SecureRandom.

    The official 'bin/rails db:encryption:init' fails on appliances
    where db:schema:load already ran during build. We generate the
    keys directly using Ruby SecureRandom (same entropy source Rails
    uses internally).

    Returns dict with the three ACTIVE_RECORD_ENCRYPTION_* keys.
    """
    keys = {}
    for key_name in [
        "ACTIVE_RECORD_ENCRYPTION_PRIMARY_KEY",
        "ACTIVE_RECORD_ENCRYPTION_DETERMINISTIC_KEY",
        "ACTIVE_RECORD_ENCRYPTION_KEY_DERIVATION_SALT",
    ]:
        result = run_as_mastodon(
            "ruby -e \"require 'securerandom'; puts SecureRandom.alphanumeric(32)\""
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise RuntimeError(
                "Failed to generate {}: {}".format(key_name, result.stderr)
            )
        keys[key_name] = result.stdout.strip()
    return keys


# -- PostgreSQL ----------------------------------------------------------

def set_db_password(db_user, db_password):
    """Set the PostgreSQL password for the given user."""
    escaped = db_password.replace("'", "''")
    sql = "ALTER USER {} WITH PASSWORD '{}';".format(db_user, escaped)
    result = subprocess.run(
        ["su", "-", "postgres", "-c", 'psql -c "{}"'.format(sql)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("Failed to set DB password: {}".format(result.stderr))


# -- .env.production -----------------------------------------------------

ENV_TEMPLATE = """\
# Mastodon configuration
# Generated by TurnKey Linux firstboot inithook
# Reference: https://docs.joinmastodon.org/admin/config/

# Federation
# ----------
# This identifies your server and cannot be changed safely later
# ----------
LOCAL_DOMAIN={domain}

# Redis
# -----
REDIS_HOST=127.0.0.1
REDIS_PORT=6379

# PostgreSQL
# ----------
DB_HOST=/var/run/postgresql
DB_USER={db_user}
DB_NAME=mastodon_production
DB_PASS={db_password}
DB_PORT=5432

# Secrets
# -------
# Generated with: bundle exec rails secret
# -------
SECRET_KEY_BASE={SECRET_KEY_BASE}
OTP_SECRET={OTP_SECRET}

# Encryption secrets
# ------------------
# Generated with: bin/rails db:encryption:init
# Do NOT change these secrets once in use
# ------------------
ACTIVE_RECORD_ENCRYPTION_DETERMINISTIC_KEY={ACTIVE_RECORD_ENCRYPTION_DETERMINISTIC_KEY}
ACTIVE_RECORD_ENCRYPTION_KEY_DERIVATION_SALT={ACTIVE_RECORD_ENCRYPTION_KEY_DERIVATION_SALT}
ACTIVE_RECORD_ENCRYPTION_PRIMARY_KEY={ACTIVE_RECORD_ENCRYPTION_PRIMARY_KEY}

# Web Push
# --------
# Generated with: bundle exec rake mastodon:webpush:generate_vapid_key
# --------
VAPID_PRIVATE_KEY={VAPID_PRIVATE_KEY}
VAPID_PUBLIC_KEY={VAPID_PUBLIC_KEY}

# Sending mail
# ------------
# TurnKey: SMTP relay configured via confconsole (Advanced > Mail Relay)
# ------------
SMTP_SERVER=localhost
SMTP_PORT=25
SMTP_FROM_ADDRESS=notifications@{domain}
SMTP_DELIVERY_METHOD=smtp
SMTP_AUTH_METHOD=none
SMTP_OPENSSL_VERIFY_MODE=none
SMTP_ENABLE_STARTTLS=never

# Performance
# -----------
MALLOC_ARENA_MAX=2
MASTODON_USE_LIBVIPS=true

# IP and session retention
# -----------------------
IP_RETENTION_PERIOD=31556952
SESSION_RETENTION_PERIOD=31556952
"""


def write_env_production(config, secrets):
    """Write .env.production per official docs."""
    values = {}
    values.update(config)
    values.update(secrets)
    content = ENV_TEMPLATE.format(**values)

    with open(ENV_FILE, "w") as f:
        f.write(content)
    run_cmd("chown {}:{} {}".format(MASTODON_USER, MASTODON_USER, ENV_FILE))
    run_cmd("chmod 600 {}".format(ENV_FILE))


# -- Admin account -------------------------------------------------------

def create_admin_account(email, password):
    """Create the Mastodon admin account."""
    username = email.split("@")[0]

    result = run_as_mastodon(
        "RAILS_ENV=production bin/tootctl accounts create "
        "{} --email {} --confirmed --role Owner".format(username, email),
        env_extra={"RAILS_ENV": "production"},
    )
    if result.returncode != 0:
        run_as_mastodon(
            "RAILS_ENV=production bin/tootctl accounts modify "
            "{} --email {} --confirm --role Owner".format(username, email),
            env_extra={"RAILS_ENV": "production"},
        )

    # Set password via Rails runner
    escaped = password.replace("'", "\\'")
    rails_cmd = (
        'RAILS_ENV=production bin/rails runner "'
        "account = Account.find_local('{}'); "
        "user = account.user; "
        "user.password = '{}'; "
        "user.password_confirmation = '{}'; "
        'user.save!"'.format(username, escaped, escaped)
    )
    result = run_as_mastodon(rails_cmd, env_extra={"RAILS_ENV": "production"})
    return result.returncode == 0, username


# -- Main ----------------------------------------------------------------

def main():
    ensure_services_running()

    d = Dialog("TurnKey GNU/Linux - First boot configuration")

    config = {}

    # 1. FQDN
    config["domain"] = d.get_input(
        "Mastodon Domain (FQDN)",
        "Enter the fully qualified domain name for your Mastodon instance.\n\n"
        "WARNING: This CANNOT be changed after federation begins!\n\n"
        "Example: social.example.com",
        "social.example.com",
    )

    # 2. Admin email
    config["admin_email"] = d.get_email(
        "Mastodon Admin Email",
        "Enter the email address for the Mastodon admin account.",
        "admin@{}".format(config["domain"]),
    )

    # 3. Admin password (generate or manual - handled by dialog_wrapper)
    config["admin_password"] = d.get_password(
        "Mastodon Admin Password",
        "Set the password for the Mastodon admin account.",
        pass_req=8,
    )

    # 4. PostgreSQL username
    config["db_user"] = d.get_input(
        "PostgreSQL Username",
        "Database username for Mastodon.\n"
        "Leave the default unless you have a reason to change it.",
        "mastodon",
    )

    # 5. PostgreSQL password (generate or manual)
    config["db_password"] = d.get_password(
        "PostgreSQL Password ({})".format(config["db_user"]),
        "Set the database password for user '{}'.".format(config["db_user"]),
        pass_req=12,
    )

    # 6. Generate ALL secrets
    d.infobox("Generating secrets... this may take a moment.")

    try:
        secrets = {}
        secrets["SECRET_KEY_BASE"] = generate_rails_secret()
        secrets["OTP_SECRET"] = generate_rails_secret()
        secrets.update(generate_vapid_keys())
        secrets.update(generate_encryption_keys())
    except RuntimeError as e:
        d.error("Failed to generate secrets:\n\n{}".format(e))
        sys.exit(1)

    # 7. Set PostgreSQL password
    d.infobox("Configuring PostgreSQL...")
    try:
        set_db_password(config["db_user"], config["db_password"])
    except RuntimeError as e:
        d.error("Failed to set database password:\n\n{}".format(e))
        sys.exit(1)

    # 8. Write .env.production
    d.infobox("Writing configuration...")
    write_env_production(config, secrets)

    # 9. Database migrations
    d.infobox("Running database migrations...")
    result = run_as_mastodon(
        "RAILS_ENV=production bundle exec rails db:migrate",
        env_extra={"RAILS_ENV": "production"},
    )
    if result.returncode != 0:
        d.msgbox(
            "Migration Warning",
            "Warnings (may be normal on first boot):\n\n"
            "{}".format(result.stderr[:500]),
        )

    # 10. Create admin account
    d.infobox("Creating admin account...")
    ok, username = create_admin_account(
        config["admin_email"], config["admin_password"]
    )
    if not ok:
        d.msgbox(
            "Admin Warning",
            "Could not set admin password automatically.\n\n"
            "Reset manually:\n"
            "  su - mastodon -c 'cd ~/live && RAILS_ENV=production"
            " bin/tootctl accounts modify {} --reset-password'".format(username),
        )

    # 11. Start services
    d.infobox("Starting Mastodon services...")
    for svc in ["mastodon-web", "mastodon-sidekiq", "mastodon-streaming"]:
        run_cmd("systemctl restart {}".format(svc))

    # 12. Done
    d.msgbox(
        "Setup Complete",
        "Your Mastodon instance is ready!\n\n"
        "  Domain:   https://{domain}\n"
        "  Admin:    {email}\n"
        "  Handle:   @{user}@{domain}\n"
        "  Webmin:   https://{domain}:12321\n\n"
        "Configure mail relay: confconsole > Advanced > Mail Relay\n\n"
        "Config: {env}\n"
        "BACK UP this file - secrets cannot be regenerated.".format(
            domain=config["domain"],
            email=config["admin_email"],
            user=username,
            env=ENV_FILE,
        ),
    )


if __name__ == "__main__":
    main()
