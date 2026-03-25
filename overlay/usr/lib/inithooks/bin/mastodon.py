#!/usr/bin/env python3
"""TurnKey Mastodon firstboot configuration"""

import subprocess
import os
import sys
import re
import argparse

MASTODON_LIVE = "/home/mastodon/live"
ENV_FILE = os.path.join(MASTODON_LIVE, ".env.production")
MASTODON_USER = "mastodon"


def run_as_mastodon(cmd):
    r = subprocess.run(
        ["su", "-s", "/bin/bash", "-", MASTODON_USER, "-c",
         f"cd {MASTODON_LIVE} && {cmd}"],
        capture_output=True, text=True
    )
    return r


def generate_secret():
    r = run_as_mastodon("RAILS_ENV=production bundle exec rails secret")
    return r.stdout.strip()


def generate_key():
    r = subprocess.run(
        ["openssl", "rand", "-base64", "24"],
        capture_output=True, text=True
    )
    return r.stdout.strip()


def update_env(key, value):
    with open(ENV_FILE, "r") as f:
        content = f.read()
    pattern = f"^{re.escape(key)}=.*$"
    replacement = f"{key}={value}"
    content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    with open(ENV_FILE, "w") as f:
        f.write(content)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--pass", dest="password", required=True)
    args = parser.parse_args()

    domain = args.domain
    email = args.email
    password = args.password

    print("Generating secrets...")

    # Generate Rails secrets
    secret_key = generate_secret()
    otp_secret = generate_secret()
    update_env("SECRET_KEY_BASE", secret_key)
    update_env("OTP_SECRET", otp_secret)

    # Generate Active Record encryption keys (openssl, not Rails)
    update_env("ACTIVE_RECORD_ENCRYPTION_DETERMINISTIC_KEY", generate_key())
    update_env("ACTIVE_RECORD_ENCRYPTION_KEY_DERIVATION_SALT", generate_key())
    update_env("ACTIVE_RECORD_ENCRYPTION_PRIMARY_KEY", generate_key())

    # Set domain
    update_env("LOCAL_DOMAIN", domain)

    # Create admin account
    r = run_as_mastodon(
        f"RAILS_ENV=production bin/tootctl accounts create admin "
        f"--email={email} --confirmed --role=Owner"
    )
    print(r.stdout)
    if r.returncode != 0:
        print(f"Warning: {r.stderr}", file=sys.stderr)

    # Set admin password
    run_as_mastodon(
        f'RAILS_ENV=production bin/rails runner "'
        f"a = Account.find_local(\\\"admin\\\"); "
        f"u = a.user; "
        f"u.password = \\\"{password}\\\"; "
        f"u.password_confirmation = \\\"{password}\\\"; "
        f'u.save!"'
    )

    print(f"Mastodon configured for {domain}")
    print(f"Admin: {email}")


if __name__ == "__main__":
    main()
