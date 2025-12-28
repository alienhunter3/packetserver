#!/usr/bin/env python3
"""
PacketServer HTTP User Management CLI

Supports local FileStorage or ZEO databases via --db.

Examples:
  python packetserver/runners/http_user_manager.py --db /path/to/Data.fs add W1AW secret
  python packetserver/runners/http_user_manager.py --db zeo.host.com:8100 list
"""

import argparse
import sys
import time
from getpass import getpass
import ax25
import os.path
import os

import ZODB.FileStorage
import ZODB.DB
import transaction
from persistent.mapping import PersistentMapping

os.environ['PS_APP_ZEO_FILE'] = "N/A"

# Import our HTTP package internals
from packetserver.http.auth import HttpUser, ph  # ph = PasswordHasher

# Define the key directly here (no separate database.py module needed)
HTTP_USERS_KEY = "httpUsers"


def open_database(db_arg: str) -> ZODB.DB:
    if ":" in db_arg:
        parts = db_arg.split(":")
        if len(parts) == 2 and parts[1].isdigit():
            import ZEO
            host = parts[0]
            port = int(parts[1])
            storage = ZEO.client((host, port))  # modern ZEO
            return ZODB.DB(storage)

    # Local
    storage = ZODB.FileStorage.FileStorage(db_arg)
    return ZODB.DB(storage)


def open_database_zeo_file(filename: str) -> ZODB.DB:
    if os.path.isfile(filename):
        return open_database(open(filename,'r').read().strip())
    else:
        raise FileNotFoundError("Must provide a filename to a zeo address.")


def get_or_create_http_users(root):
    if HTTP_USERS_KEY not in root:
        root[HTTP_USERS_KEY] = PersistentMapping()
        transaction.commit()  # safe during initial creation
    return root[HTTP_USERS_KEY]


def confirm(prompt: str) -> bool:
    return input(f"{prompt} (y/N): ").strip().lower() == "y"


def main():
    parser = argparse.ArgumentParser(description="Manage PacketServer HTTP API users")
    parser.add_argument("--db", required=False, help="DB path (local /path/to/Data.fs) or ZEO (host:port)")
    parser.add_argument("--zeo-file", required=False, help="zeo address file")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # add
    p_add = subparsers.add_parser("add", help="Create a new HTTP user")
    p_add.add_argument("callsign", help="Callsign (username)")
    p_add.add_argument("password", nargs="?", help="Password (if omitted, will prompt)")

    # delete
    p_del = subparsers.add_parser("delete", help="Delete an HTTP user")
    p_del.add_argument("callsign", help="Callsign to delete")

    # set-password
    p_pwd = subparsers.add_parser("set-password", help="Change password")
    p_pwd.add_argument("callsign", help="Callsign")
    p_pwd.add_argument("newpassword", nargs="?", help="New password (if omitted, will prompt)")

    # enable / disable
    p_enable = subparsers.add_parser("enable", help="Enable HTTP access")
    p_enable.add_argument("callsign", help="Callsign")
    p_disable = subparsers.add_parser("disable", help="Disable HTTP access")
    p_disable.add_argument("callsign", help="Callsign")

    # rf-enable / rf-disable
    p_rf_enable = subparsers.add_parser("rf-enable", help="Allow RF gateway (remove from blacklist)")
    p_rf_enable.add_argument("callsign", help="Callsign")
    p_rf_disable = subparsers.add_parser("rf-disable", help="Block RF gateway (add to blacklist)")
    p_rf_disable.add_argument("callsign", help="Callsign")

    # list
    subparsers.add_parser("list", help="List all HTTP users")

    # dump
    p_dump = subparsers.add_parser("dump", help="Dump JSON details of the BBS user (incl. UUID and hidden flag)")
    p_dump.add_argument("callsign", help="Callsign to dump")

    # sync missing
    p_sync = subparsers.add_parser("sync-missing", help="Add missing HttpUser objects for existing BBS users")
    p_sync.add_argument("--dry-run", action="store_true", help="Show what would be done without changes")
    p_sync.add_argument("--enable", action="store_true", help="Set http_enabled=True for new users (default False)")

    args = parser.parse_args()

    # Open the database
    if args.db:
        db = open_database(args.db)
    else:
        db = open_database_zeo_file(args.zeo_file)


    try:
        with db.transaction() as conn:
            root = conn.root()
            http_users_list = list(get_or_create_http_users(root).keys())

        upper_callsign = lambda c: c.upper()

        if args.command == "add":
            from packetserver.common.util import is_valid_ax25_callsign
            callsign = upper_callsign(args.callsign)
            if is_valid_ax25_callsign(callsign):
                base = ax25.Address(callsign).call.upper()
                if base != callsign:
                    print(f"Error: Trying to add valid callsign + ssid. Remove -<num> and add again.")
                    sys.exit(1)

            if callsign in http_users_list:
                print(f"Error: HTTP user {callsign} already exists")
                sys.exit(1)

            password = args.password or getpass("Password: ")
            if not password:
                print("Error: No password provided")
                sys.exit(1)

            # Create the HTTP-specific user
            with db.transaction() as conn:
                root = conn.root()
                http_user = HttpUser(args.callsign, password)
                users_mapping = get_or_create_http_users(conn.root())
                users_mapping[callsign] = http_user
                # Sync: create corresponding regular BBS user using proper write_new for UUID/uniqueness
                from packetserver.server.users import User

                main_users = root.setdefault('users', PersistentMapping())
                if callsign not in main_users:
                    new_user = User(args.callsign)
                    new_user.write_new(conn.root())
                    print(f"  → Also created regular BBS user {callsign}")
                else:
                    print(f"  → Regular BBS user {callsign} already exists")
                print(f"Created HTTP user {callsign}")

        elif args.command == "delete":
            callsign = upper_callsign(args.callsign)
            if callsign not in http_users_list:
                print(f"Error: User {callsign} not found")
                sys.exit(1)
            if not confirm(f"Delete HTTP user {callsign}?"):
                sys.exit(0)
            with db.transaction() as conn:
                root = conn.root()
                users_mapping = get_or_create_http_users(root)
                del users_mapping[callsign]
                print(f"Deleted HTTP user {callsign}")

        elif args.command == "set-password":
            callsign = upper_callsign(args.callsign)
            with db.transaction() as conn:
                root = conn.root()
                users_mapping = get_or_create_http_users(root)
                user = users_mapping.get(callsign)
                if not user:
                    print(f"Error: User {callsign} not found")
                    sys.exit(1)
                newpass = args.newpassword or getpass("New password: ")
                if not newpass:
                    print("Error: No password provided")
                    sys.exit(1)
                user.password_hash = ph.hash(newpass)
                user._p_changed = True
                print(f"Password updated for {callsign}")

        elif args.command == "enable":
            with db.transaction() as conn:
                root = conn.root()
                users_mapping = get_or_create_http_users(root)
                callsign = upper_callsign(args.callsign)
                user = users_mapping.get(callsign)
                if not user:
                    print(f"Error: User {callsign} not found")
                    sys.exit(1)
                user.http_enabled = True
                user._p_changed = True
                print(f"HTTP access enabled for {callsign}")

        elif args.command == "disable":
            callsign = upper_callsign(args.callsign)
            with db.transaction() as conn:
                root = conn.root()
                users_mapping = get_or_create_http_users(root)
                user = users_mapping.get(callsign)
                if not user:
                    print(f"Error: User {callsign} not found")
                    sys.exit(1)
                user.http_enabled = False
                user._p_changed = True
                print(f"HTTP access disabled for {callsign}")

        elif args.command == "rf-enable":
            callsign = upper_callsign(args.callsign)
            with db.transaction() as conn:
                root = conn.root()
                users_mapping = get_or_create_http_users(root)
                user = users_mapping.get(callsign)
                if not user:
                    print(f"Error: User {callsign} not found")
                    sys.exit(1)
            try:
                user.set_rf_enabled(db, True)
                print(f"RF gateway enabled for {callsign}")
            except ValueError as e:
                print(f"Error: {e}")
                sys.exit(1)

        elif args.command == "rf-disable":
            callsign = upper_callsign(args.callsign)
            with db.transaction() as conn:
                root = conn.root()
                users_mapping = get_or_create_http_users(root)
                user = users_mapping.get(callsign)
                if not user:
                    print(f"Error: User {callsign} not found")
                    sys.exit(1)
            user.set_rf_enabled(db, False)
            print(f"RF gateway disabled for {callsign}")

        elif args.command == "list":
            if not http_users_list:
                print("No HTTP users configured")
            else:
                with db.transaction() as conn:
                    root = conn.root()
                    users_mapping = get_or_create_http_users(root)
                    print(f"{'Callsign':<12} {'HTTP Enabled':<13} {'RF Enabled':<11} {'Created':<20} Last Login")
                    print("-" * 75)
                    for user in sorted(users_mapping.values(), key=lambda u: u.username):
                        created = time.strftime("%Y-%m-%d %H:%M", time.localtime(user.created_at))
                        last = (time.strftime("%Y-%m-%d %H:%M", time.localtime(user.last_login))
                                if user.last_login else "-")
                        rf_status = "True" if user.is_rf_enabled(conn) else "False"
                        print(f"{user.username:<12} {str(user.http_enabled):<13} {rf_status:<11} {created:<20} {last}")

        elif args.command == "dump":
            import json

            callsign = upper_callsign(args.callsign)
            with db.transaction() as conn:
                root = conn.root()
                users_mapping = get_or_create_http_users(root)
                http_user = users_mapping.get(callsign)
                if not http_user:
                    print(f"Error: No HTTP user {callsign} found")
                    sys.exit(1)

                main_users = root.get('users', {})
                bbs_user = main_users.get(callsign)
                if not bbs_user:
                    print(f"Error: No corresponding BBS user {callsign} found")
                    sys.exit(1)

                dump_data = {
                    "http_user": {
                        "username": http_user.username,
                        "http_enabled": http_user.http_enabled,
                        "rf_enabled": http_user.is_rf_enabled(conn),
                        "blacklisted": not http_user.is_rf_enabled(conn),  # explicit inverse
                        "created_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(http_user.created_at)),
                        "failed_attempts": http_user.failed_attempts,
                    },
                    "bbs_user": {
                        "username": bbs_user.username,
                        "uuid": str(bbs_user.uuid) if hasattr(bbs_user, 'uuid') and bbs_user.uuid else None,
                        "hidden": bbs_user.hidden,
                        "enabled": bbs_user.enabled,  # BBS enabled flag
                        "created_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(bbs_user.created_at.timestamp())) if hasattr(bbs_user.created_at, "timestamp") else str(bbs_user.created_at),
                        "last_seen": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(bbs_user.last_seen.timestamp())) if hasattr(bbs_user.last_seen, "timestamp") else str(bbs_user.last_seen),
                        "bio": bbs_user.bio.strip() or None,
                        "status": bbs_user.status.strip() or None,
                        "email": bbs_user.email.strip() if bbs_user.email != " " else None,
                        "location": bbs_user.location.strip() if bbs_user.location != " " else None,
                        "socials": bbs_user.socials,
                    }
                }

                print(json.dumps(dump_data, indent=4))

        elif args.command == "sync-missing":
            import secrets
            import string

            def generate_password(length=20):
                alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
                return ''.join(secrets.choice(alphabet) for _ in range(length))

            with db.transaction() as conn:
                root = conn.root()
                bbs_users = root.get('users', {})
                http_users = get_or_create_http_users(root)

                missing = [call for call in bbs_users if call not in http_users and call != "SYSTEM"]
                if not missing:
                    print("No missing HTTP users—all BBS users have HttpUser objects")
                else:
                    print(f"Found {len(missing)} BBS users without HTTP accounts:")
                    for call in sorted(missing):
                        print(f"  - {call}")

                    if args.dry_run:
                        print("\n--dry-run: No changes made")
                    else:
                        confirm_msg = f"Create {len(missing)} new HttpUser objects (http_enabled={'True' if args.enable else 'False'})?"
                        if not confirm(confirm_msg):
                            print("Aborted")
                        else:
                            created_count = 0
                            for call in missing:
                                password = generate_password()  # strong random, not printed
                                new_http = HttpUser(call, password)
                                new_http.http_enabled = args.enable
                                http_users[call] = new_http
                                created_count += 1

                            transaction.commit()
                            print(f"\nSync complete: {created_count} HTTP users added (passwords random & hidden)")
                            print("Use 'set-password <call>' to set a known password before enabling login")

    finally:
        db.close()


if __name__ == "__main__":
    main()