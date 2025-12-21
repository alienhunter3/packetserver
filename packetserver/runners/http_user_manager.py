#!/usr/bin/env python3
"""
PacketServer HTTP User Management CLI

Supports local FileStorage or ZEO databases via --db.

Examples:
  python runners/http_user_manager.py --db /path/to/Data.fs add W1AW secret
  python runners/http_user_manager.py --db zeo.host.com:8100 list
"""

import argparse
import sys
import time
from getpass import getpass

import ZODB.FileStorage
import ZODB.DB
import transaction
from persistent.mapping import PersistentMapping

# Import our HTTP package internals
from packetserver.http.auth import HttpUser, ph  # ph = PasswordHasher
from packetserver.http.database import HTTP_USERS_KEY


def open_database(db_arg: str) -> ZODB.DB.DB:
    """
    Open a ZODB database from either a local FileStorage path or ZEO address.
    """
    if ":" in db_arg and db_arg.count(":") == 1 and "." in db_arg.split(":")[0]:
        import ZEO
        host, port_str = db_arg.split(":")
        try:
            port = int(port_str)
        except ValueError:
            raise ValueError(f"Invalid port in ZEO address: {db_arg}")
        storage = ZEO.client_storage(host, port)
        return ZODB.DB(storage)
    else:
        # Local FileStorage path
        storage = ZODB.FileStorage.FileStorage(db_arg)
        return ZODB.DB(storage)


def get_or_create_http_users(root):
    if HTTP_USERS_KEY not in root:
        root[HTTP_USERS_KEY] = PersistentMapping()
    return root[HTTP_USERS_KEY]


def confirm(prompt: str) -> bool:
    return input(f"{prompt} (y/N): ").strip().lower() == "y"


def main():
    parser = argparse.ArgumentParser(description="Manage PacketServer HTTP API users")
    parser.add_argument("--db", required=True, help="DB path (local /path/to/Data.fs) or ZEO (host:port)")
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

    args = parser.parse_args()

    # Open the database
    db = open_database(args.db)
    connection = db.open()
    root = connection.root()

    try:
        users_mapping = get_or_create_http_users(root)

        upper_callsign = lambda c: c.upper()

        if args.command == "add":
            callsign = upper_callsign(args.callsign)
            if callsign in users_mapping:
                print(f"Error: HTTP user {callsign} already exists")
                sys.exit(1)

            password = args.password or getpass("Password: ")
            if not password:
                print("Error: No password provided")
                sys.exit(1)

            # Create the HTTP-specific user
            http_user = HttpUser(args.callsign, password)
            users_mapping[callsign] = http_user

            # Sync: create corresponding regular BBS user using proper write_new for UUID/uniqueness
            from packetserver.server.users import User

            main_users = root.setdefault('users', PersistentMapping())
            if callsign not in main_users:
                User.write_new(main_users, args.callsign)
                print(f"  → Also created regular BBS user {callsign} (with UUID)")
            else:
                print(f"  → Regular BBS user {callsign} already exists")

            transaction.commit()
            print(f"Created HTTP user {callsign}")

        elif args.command == "delete":
            callsign = upper_callsign(args.callsign)
            if callsign not in users_mapping:
                print(f"Error: User {callsign} not found")
                sys.exit(1)
            if not confirm(f"Delete HTTP user {callsign}?"):
                sys.exit(0)
            del users_mapping[callsign]
            transaction.commit()
            print(f"Deleted HTTP user {callsign}")

        elif args.command == "set-password":
            callsign = upper_callsign(args.callsign)
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
            transaction.commit()
            print(f"Password updated for {callsign}")

        elif args.command == "enable":
            callsign = upper_callsign(args.callsign)
            user = users_mapping.get(callsign)
            if not user:
                print(f"Error: User {callsign} not found")
                sys.exit(1)
            user.enabled = True
            user._p_changed = True
            transaction.commit()
            print(f"HTTP access enabled for {callsign}")

        elif args.command == "disable":
            callsign = upper_callsign(args.callsign)
            user = users_mapping.get(callsign)
            if not user:
                print(f"Error: User {callsign} not found")
                sys.exit(1)
            user.enabled = False
            user._p_changed = True
            transaction.commit()
            print(f"HTTP access disabled for {callsign}")

        elif args.command == "rf-enable":
            callsign = upper_callsign(args.callsign)
            user = users_mapping.get(callsign)
            if not user:
                print(f"Error: User {callsign} not found")
                sys.exit(1)
            try:
                user.rf_enabled = True
                transaction.commit()
                print(f"RF gateway enabled for {callsign}")
            except ValueError as e:
                print(f"Error: {e}")
                sys.exit(1)

        elif args.command == "rf-disable":
            callsign = upper_callsign(args.callsign)
            user = users_mapping.get(callsign)
            if not user:
                print(f"Error: User {callsign} not found")
                sys.exit(1)
            user.rf_enabled = False
            transaction.commit()
            print(f"RF gateway disabled for {callsign}")

        elif args.command == "list":
            if not users_mapping:
                print("No HTTP users configured")
            else:
                print(f"{'Callsign':<12} {'Enabled':<8} {'RF Enabled':<11} {'Created':<20} Last Login")
                print("-" * 70)
                for user in sorted(users_mapping.values(), key=lambda u: u.username):
                    created = time.strftime("%Y-%m-%d %H:%M", time.localtime(user.created_at))
                    last = (time.strftime("%Y-%m-%d %H:%M", time.localtime(user.last_login))
                            if user.last_login else "-")
                    print(f"{user.username:<12} {str(user.enabled):<8} {str(user.rf_enabled):<11} {created:<20} {last}")

    finally:
        connection.close()
        db.close()


if __name__ == "__main__":
    main()