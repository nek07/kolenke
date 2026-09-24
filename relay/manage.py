"""Panel owner's commands.
    python -m relay.manage invite        — a one-time invite code for a friend
    python -m relay.manage users         — who is registered and whose agent was seen when
"""
import sys

from relay import store


def main(argv):
    store.init()
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "invite":
        print(store.new_invite())
    elif cmd == "users":
        for u in store.q("SELECT id, email, is_admin, created_at FROM users ORDER BY id"):
            seen = store.q("SELECT MAX(last_seen) s FROM agents WHERE user_id=?", (u["id"],))[0]["s"]
            print(f"{u['id']:>3}  {u['email']:<32} {'владелец' if u['is_admin'] else '':<9} агент: {seen or '—'}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
